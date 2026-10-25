# Loader — registers the extension. Packaged with designforge_bridge/ into designforge_bridge.rbz.
require 'sketchup.rb'
require 'extensions.rb'

module DesignForge
  module Bridge
    EXTENSION = SketchupExtension.new('DesignForge Bridge', 'designforge_bridge/main')
    EXTENSION.version     = '0.3.0'
    EXTENSION.creator     = 'DesignForge'
    EXTENSION.description = 'Builds DesignForge PartGraphs inside SketchUp for the MCP geometry engine.'
    Sketchup.register_extension(EXTENSION, true)
  end
end
