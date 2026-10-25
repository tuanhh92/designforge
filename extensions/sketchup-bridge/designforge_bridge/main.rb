# DesignForge Bridge — runs inside SketchUp.
#
# Protocol: newline-delimited JSON over TCP 127.0.0.1:<port>.
#   request  {"id": 1, "token": "...", "method": "execute_batch", "params": {...}}
#   response {"id": 1, "ok": true, ...} | {"id": 1, "ok": false, "error": "...", "retryable": false}
#
# Configuration: ~/.designforge/bridge.json  {"port": 9877, "token": "...", "job_root": "/abs/path"}
# (GUI apps on macOS do not see shell environment variables; DF_BRIDGE_* env vars still override.)
#
# The SketchUp Ruby API is single-threaded, so the socket is polled from a UI timer on the
# main thread instead of a background Thread. Every batch is one undoable operation.
# Builds go into their own document: the bridge never touches a model the user is working on.
require 'sketchup.rb'
require 'socket'
require 'json'
require 'fileutils'

module DesignForge
  module Bridge
    VERSION      = '0.3.0'.freeze
    DEFAULT_PORT = 9877 # 9876 is the community SketchUp MCP extension's port; both can run side by side
    CONFIG_PATH  = File.expand_path(ENV['DF_BRIDGE_CONFIG'] || '~/.designforge/bridge.json')
    DICT         = 'designforge'.freeze
    OPS          = %w[ensure_material ensure_tag define_panel define_proxy group place paint].freeze

    class BridgeError < StandardError
      attr_reader :retryable
      def initialize(msg, retryable = false)
        super(msg)
        @retryable = retryable
      end
    end

    @server  = nil
    @timer   = nil
    @config  = nil
    @clients = []
    @buffers = {}
    @model   = nil  # the document this bridge builds into
    @groups  = {}   # assembly path → Sketchup::Group
    @guards  = []   # construction points that keep groups alive between batches
    @defs    = {}   # def_key → ComponentDefinition
    @instances = {} # instance_key → ComponentInstance

    class << self
      attr_reader :config

      def load_config
        file = {}
        if File.file?(CONFIG_PATH)
          begin
            file = JSON.parse(File.read(CONFIG_PATH))
          rescue JSON::ParserError => e
            puts "[DesignForge] cannot parse #{CONFIG_PATH}: #{e.message}"
          end
        end
        {
          port: (ENV['DF_BRIDGE_PORT'] || file['port'] || DEFAULT_PORT).to_i,
          token: ENV['DF_BRIDGE_TOKEN'] || file['token'],
          job_root: File.expand_path(ENV['DF_JOB_ROOT'] || file['job_root'] || '~/DesignForge/jobs')
        }
      end

      # ── socket loop ───────────────────────────────────────────────────────
      def start
        return status if @server
        @config = load_config
        if @config[:token].nil? || @config[:token].empty?
          return puts("[DesignForge] bridge not started: no token in #{CONFIG_PATH}")
        end
        @server = TCPServer.new('127.0.0.1', @config[:port])
        @timer = UI.start_timer(0.05, true) { tick }
        puts "[DesignForge] bridge #{VERSION} listening on 127.0.0.1:#{@config[:port]} (jobs: #{@config[:job_root]})"
      rescue Errno::EADDRINUSE
        @server = nil
        puts "[DesignForge] port #{@config[:port]} is already in use; set another \"port\" in #{CONFIG_PATH}"
      end

      def stop
        UI.stop_timer(@timer) if @timer
        @clients.each { |c| c.close rescue nil }
        @server.close if @server
        @server = nil; @timer = nil; @clients = []; @buffers = {}
      end

      def status
        return "Not running. Check #{CONFIG_PATH} (needs a token), then use Reload." unless @server
        "Listening on 127.0.0.1:#{@config[:port]}\nJobs folder: #{@config[:job_root]}\nConfig: #{CONFIG_PATH}"
      end

      def tick
        accept
        @clients.dup.each { |sock| pump(sock) }
      rescue StandardError => e
        puts "[DesignForge] tick error: #{e.class}: #{e.message}"
      end

      def accept
        sock = @server.accept_nonblock
        @clients << sock
        @buffers[sock] = +''
      rescue IO::WaitReadable, Errno::EINTR
        nil
      end

      def pump(sock)
        @buffers[sock] << sock.read_nonblock(4 << 20)
        while (line = @buffers[sock].slice!(/\A[^\n]*\n/))
          sock.write(JSON.generate(handle(line)) + "\n")
        end
      rescue IO::WaitReadable
        nil
      rescue EOFError, IOError, SystemCallError
        @clients.delete(sock)
        @buffers.delete(sock)
        sock.close rescue nil
      end

      def handle(line)
        req = JSON.parse(line)
        raise BridgeError, 'bad token' unless req['token'] == @config[:token]
        result = dispatch(req['method'], req['params'] || {})
        { 'id' => req['id'], 'ok' => true }.merge(result)
      rescue BridgeError => e
        { 'id' => req && req['id'], 'ok' => false, 'error' => e.message, 'retryable' => e.retryable }
      rescue StandardError => e
        { 'id' => req && req['id'], 'ok' => false, 'error' => "#{e.class}: #{e.message}",
          'backtrace' => e.backtrace.first(5), 'retryable' => false }
      end

      def dispatch(method, params)
        case method
        when 'ping'          then { 'bridge_version' => VERSION, 'sketchup_version' => Sketchup.version }
        when 'new_model'     then new_model
        when 'execute_batch' then execute_batch(params['commands'])
        when 'add_scenes'    then add_scenes(params['scenes'])
        when 'export'        then export(params)
        when 'save'          then save(params['path'])
        when 'model_stats'   then model_stats
        else raise BridgeError, "unknown method #{method}"
        end
      end

      def model
        raise BridgeError, 'call new_model first' unless @model && @model.valid?
        @model
      end

      # ── model lifecycle ───────────────────────────────────────────────────
      # Each build goes into a document the bridge owns, never into the user's work:
      # - the bridge's previous document, if the user has not changed it since → reused;
      # - otherwise File > New (macOS opens a new window; on Windows it replaces the current
      #   document, so it is only done when that document has no unsaved changes, because a
      #   "Save changes?" dialog would block SketchUp).
      def new_model
        current = Sketchup.active_model
        ours = @model && @model.valid? && current == @model && !current.modified?
        unless ours
          if Sketchup.platform != :platform_osx && current && current.modified?
            raise BridgeError.new('SketchUp has a model with unsaved changes. Save it or open a new empty model, then retry.', true)
          end
          Sketchup.file_new
        end
        @model = Sketchup.active_model
        reset(@model) # also removes template content such as the scale figure
        {}
      end

      def reset(m)
        m.start_operation('DesignForge reset', true)
        m.entities.clear!
        m.pages.to_a.each { |p| m.pages.erase(p) }
        m.commit_operation
        m.definitions.purge_unused
        m.materials.purge_unused
        m.layers.purge_unused
        units = m.options['UnitsOptions']
        units['LengthUnit']      = 2 # millimetres
        units['LengthPrecision'] = 0
        @groups = {}; @guards = []; @defs = {}; @instances = {}
      end

      def execute_batch(commands)
        m = model
        m.start_operation('DesignForge build', true)
        created = 0
        commands.each do |c|
          raise BridgeError, "op not allowed: #{c['op']}" unless OPS.include?(c['op'])
          send("op_#{c['op']}", m, c)
          created += 1
        end
        m.commit_operation
        { 'created' => created }
      rescue StandardError
        m.abort_operation
        raise
      end

      # ── ops ───────────────────────────────────────────────────────────────
      def op_ensure_material(m, c)
        mat = m.materials[c['code']] || m.materials.add(c['code'])
        mat.color = Sketchup::Color.new(c['color'])
        mat.set_attribute(DICT, 'display_name', c['name'])
        if c['texture_path'] && File.file?(c['texture_path'])
          mat.texture = c['texture_path']
          w, h = c['texture_size_mm'] || [2800, 2070]
          mat.texture.size = [w.mm, h.mm]
        end
        mat.set_attribute(DICT, 'grain_deg', c['grain_deg'] || 0)
      end

      def op_ensure_tag(m, c)
        tag = m.layers[c['name']] || m.layers.add(c['name'])
        tag.visible = c.fetch('visible', true)
      end

      def op_define_panel(m, c)
        l, w, t = c['length'].mm, c['width'].mm, c['thickness'].mm
        defn = m.definitions.add(c['name'])
        face = defn.entities.add_face([0, 0, 0], [l, 0, 0], [l, w, 0], [0, w, 0])
        face.reverse! if face.normal.z < 0 # faces on z=0 are created facing down
        face.pushpull(t)
        (c['holes'] || []).each do |h|
          next unless %w[top bottom].include?(h['face']) # MVP: visual holes on main faces only
          z = h['face'] == 'top' ? t : 0
          defn.entities.add_circle(Geom::Point3d.new(h['x'].mm, h['y'].mm, z), Z_AXIS, (h['d'] / 2.0).mm, 16)
        end
        defn.set_attribute(DICT, 'def_key', c['def_key'])
        (c['attrs'] || {}).each do |k, v|
          defn.set_attribute(DICT, k, v.is_a?(Hash) || v.is_a?(Array) ? JSON.generate(v) : v)
        end
        defn.set_attribute(DICT, 'material', c['material'])
        @defs[c['def_key']] = defn
      end

      def op_define_proxy(m, c)
        x, y, z = c['size'].map(&:mm)
        defn = m.definitions.add(c['name'])
        face = defn.entities.add_face([0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0])
        face.reverse! if face.normal.z < 0
        face.pushpull(z)
        (c['attrs'] || {}).each { |k, v| defn.set_attribute(DICT, k, v.to_s) }
        @defs[c['def_key']] = defn
      end

      def op_group(m, c)
        parent = c['parent'] ? @groups.fetch(c['parent']).entities : m.entities
        g = parent.add_group
        @guards << g.entities.add_cpoint(ORIGIN) # SketchUp deletes empty groups on commit
        g.name = c['name']
        g.layer = m.layers[c['tag']] if c['tag']
        g.set_attribute(DICT, 'assembly_path', c['key'])
        @groups[c['key']] = g
      end

      def op_place(m, c)
        defn = @defs.fetch(c['def_key']) { raise BridgeError, "unknown def #{c['def_key']}" }
        parent = c['parent'] && @groups[c['parent']] ? @groups[c['parent']].entities : m.entities
        a = c['transform'].map(&:to_f)
        a[12], a[13], a[14] = a[12].mm, a[13].mm, a[14].mm # translation mm → inches
        inst = parent.add_instance(defn, Geom::Transformation.new(a))
        inst.name = c['instance_key']
        inst.material = m.materials[defn.get_attribute(DICT, 'material')]
        inst.layer = m.layers[c['tag']] if c['tag']
        inst.set_attribute(DICT, 'part_key', c['instance_key'])
        @instances[c['instance_key']] = inst
      end

      def op_paint(m, c)
        @instances.fetch(c['instance_key']).material = m.materials[c['material']]
      end

      # ── scenes & exports ──────────────────────────────────────────────────
      def remove_guards
        @guards.each { |cp| cp.erase! if cp.valid? }
        @guards = []
      end

      def add_scenes(scenes)
        m = model
        remove_guards
        bb = m.bounds
        c = bb.center
        r = bb.diagonal * 1.4
        presets = {
          'front' => [Geom::Point3d.new(c.x, c.y - r, c.z), c],
          'left'  => [Geom::Point3d.new(c.x - r, c.y, c.z), c],
          'top'   => [Geom::Point3d.new(c.x, c.y, c.z + r), c],
          'iso'   => [Geom::Point3d.new(c.x - r * 0.6, c.y - r * 0.8, c.z + r * 0.5), c]
        }
        scenes.each do |s|
          cam = s['camera']
          eye, target, up =
            if cam.is_a?(String) then [*presets.fetch(cam), cam == 'top' ? Y_AXIS : Z_AXIS]
            else [cam['eye'].map(&:mm), cam['target'].map(&:mm), cam['up']]
            end
          m.active_view.camera = Sketchup::Camera.new(eye, target, up)
          m.active_view.camera.perspective = !cam.is_a?(String) || cam == 'iso'
          m.layers.each { |l| l.visible = !(s['hidden_tags'] || []).include?(l.name) }
          m.rendering_options['DisplayColorByLayer'] = false
          page = m.pages.add(s['name'])
          page.use_camera = true
          page.use_hidden_layers = true
        end
        m.layers.each { |l| l.visible = true }
        { 'scenes' => m.pages.map(&:name) }
      end

      def safe_path(path)
        full = File.expand_path(path)
        FileUtils.mkdir_p(File.dirname(full))
        root = @config[:job_root]
        raise BridgeError, "path outside job root #{root}: #{full}" unless full.start_with?(root + File::SEPARATOR)
        full
      end

      def export(params)
        m = model
        path = safe_path(params['path'])
        case params['format']
        when 'png'
          page = m.pages[params['scene']] or raise BridgeError, "no scene #{params['scene']}"
          m.pages.selected_page = page
          opts = params['options'] || {}
          ok = m.active_view.write_image(filename: path, width: opts['width'] || 1920,
                                         height: opts['height'] || 1080, antialias: true, transparent: false)
        when 'obj', 'stl', 'dxf'
          ok = m.export(path, (params['options'] || {}).merge(show_summary: false))
        else
          raise BridgeError, "unsupported export #{params['format']}"
        end
        raise BridgeError.new("export #{params['format']} failed", true) unless ok && File.file?(path)
        { 'path' => path, 'bytes' => File.size(path) }
      end

      def save(path)
        remove_guards
        full = safe_path(path)
        raise BridgeError.new('save failed', true) unless model.save(full)
        { 'path' => full, 'bytes' => File.size(full) }
      end

      def model_stats
        m = model
        bb = m.bounds # width = X, height = Y, depth = Z in SketchUp terms
        count = ->(ents) { ents.sum { |e| e.is_a?(Sketchup::ComponentInstance) ? 1 : e.is_a?(Sketchup::Group) ? count.(e.entities) : 0 } }
        { 'bbox_mm' => [bb.width.to_mm.round, bb.height.to_mm.round, bb.depth.to_mm.round],
          'instance_count' => count.(m.entities),
          'definition_count' => m.definitions.count { |d| !d.group? } }
      end
    end

    unless file_loaded?(__FILE__)
      menu = UI.menu('Extensions').add_submenu('DesignForge Bridge')
      menu.add_item('Status') { UI.messagebox(status) }
      menu.add_item('Reload config and restart') { stop; start; UI.messagebox(status) }
      start
      file_loaded(__FILE__)
    end
  end
end
