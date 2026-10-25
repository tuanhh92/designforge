# 04 — SketchUp MCP integration layer

## 1. Reality check first

| Fact | Consequence |
|---|---|
| SketchUp is a **desktop GUI application** (Windows/macOS). No Linux build, no official headless mode. | Needs dedicated Windows VMs with an auto-logged-in interactive session. Not a container in your normal cluster. |
| The Ruby API must be called on SketchUp's **main thread**. | The bridge extension polls a socket from a `UI.start_timer` callback, executes commands, replies. One command stream per SketchUp process. |
| Community SketchUp MCP servers (e.g. `mhyrr/sketchup-mcp`) are a Python MCP server + a Ruby extension speaking JSON over a local TCP socket, exposing a few primitives (create/transform/delete component, set material, export) plus `eval_ruby`. | Great starting point; **fork it**. Primitive-per-call is far too chatty for 150-part wardrobes (each call = a socket round-trip and an undo step). Add a **batch tool** that builds a whole PartGraph in one operation. Disable `eval_ruby` in production — it is arbitrary code execution. |
| Modal dialogs (welcome screen, update prompts, license nags, crash reporter, "save changes?") **block automation silently**. | Golden VM image with all of them disabled; watchdog kills and restarts SketchUp on heartbeat loss. |
| **Licensing**: SketchUp subscriptions are per named user; running SketchUp unattended as a back-end for a third-party SaaS may not be permitted by the EULA. | **Get written confirmation from Trimble before launch.** Architect so SketchUp can be replaced (see §6 — SketchUp C SDK writes `.skp` without the app). |

Hence the layering below: the platform depends on a `GeometryEngine` port; SketchUp-via-MCP is one adapter.

## 2. Layers

```
 worker-core / api                        Geometry node (Windows)
┌──────────────────────────────┐        ┌───────────────────────────────────────────────────────────┐
│ GeometryService              │        │ sketchup-agent                                            │
│  build(version) → enqueue job│ HTTPS  │  ClaimLoop ─► JobRunner                                   │
└──────────────┬───────────────┘ claim  │                 │                                         │
               ▼                 ─────► │                 ▼                                         │
      geometry_jobs (Postgres)          │  SketchUpMcpEngine  (implements GeometryEngine)           │
                                        │    ├─ PartGraphCompiler: PartGraph → [GeometryCommand]    │
                                        │    │    macros: create_carcass / create_cabinet expand     │
                                        │    │    into create_panel + create_group commands          │
                                        │    ├─ McpSketchUpClient (mcp SDK, stdio transport)        │
                                        │    │    call_tool("df_execute_batch", {commands})          │
                                        │    └─ ExportPlanner: skp/obj/stl/dxf/scenes → tool calls   │
                                        │                 │ stdio                                   │
                                        │                 ▼                                         │
                                        │  SketchUp MCP server (forked FastMCP)                     │
                                        │    tools: df_ping df_new_model df_execute_batch           │
                                        │           df_add_scenes df_export df_save df_model_stats  │
                                        │                 │ TCP 127.0.0.1:9876, NDJSON, token       │
                                        │                 ▼                                         │
                                        │  SketchUp.exe + designforge_bridge.rbz                    │
                                        │    timer-driven command loop on main thread               │
                                        │    one model.start_operation per batch (atomic, fast)     │
                                        └───────────────────────────────────────────────────────────┘
```

## 3. Interfaces

Code: [python/df_geometry/engine.py](../python/df_geometry/engine.py), [commands.py](../python/df_geometry/commands.py), [mcp_client.py](../python/df_geometry/mcp_client.py), [sketchup_engine.py](../python/df_geometry/sketchup_engine.py), Ruby: [extensions/sketchup-bridge](../extensions/sketchup-bridge/designforge_bridge/main.rb).

### 3.1 `GeometryEngine` (port)

```python
class GeometryEngine(Protocol):
    name: str
    def capabilities(self) -> EngineCapabilities            # exports supported, max parts, version
    async def health(self) -> EngineHealth
    async def build(self, graph: PartGraph, request: BuildRequest) -> BuildResult  # high-level, what the job uses
    def session(self) -> AsyncContextManager[ModelSession]  # low-level, for interactive/advanced use
```

### 3.2 `ModelSession` (fine-grained capability surface)

| Capability (requested) | Method | Bridge implementation |
|---|---|---|
| connect | `engine.session()` | spawn MCP server (stdio), `initialize`, `df_ping` handshake with version check |
| create components | `create_component(def_key, name, attrs)` / `place_instance(def_key, transform, tag)` | `ComponentDefinition` reused for identical parts (shelves) — smaller file, OpenCutList-friendly |
| create panels | `create_panel(PanelCmd)` | rectangle face → `pushpull(thickness)` inside a definition; attributes `designforge.*` |
| create carcasses | `create_carcass(CarcassMacro)` | **client-side macro** → panels + group (bridge stays small and dumb) |
| create cabinets | `create_cabinet(CabinetMacro)` | macro → carcass + fronts + hardware proxies + group |
| apply materials | `apply_material(target, MaterialCmd)` | `model.materials.add`, colour/texture, grain-aligned UV rotation |
| generate scenes | `add_scenes([SceneCmd])` | `model.pages.add`, camera, visible tags (`DF_Fronts`, `DF_Carcass`, `DF_Back`, `DF_Hardware`) |
| export SKP | `save_skp(path, version)` | `model.save(path)` |
| export OBJ | `export(path, "obj", opts)` | `model.export(path, options)` (OBJ exporter, Pro) |
| export DXF | `export(path, "dxf", opts)` | Pro 3D DWG/DXF exporter. *Manufacturing* DXFs are generated by `df_drawings`/`df_manufacturing` from the PartGraph, not by SketchUp. |
| export STL | `export(path, "stl", opts)` | STL exporter (bundled Trimble STL extension in current releases; verify per version). Fallback: `GltfEngine` writes STL from PartGraph boxes. |
| scene PNGs | `render_scene(scene, path, w, h)` | `view.write_image` |

### 3.3 Commands (wire format of `df_execute_batch`)

All coordinates in **mm** on the wire; the bridge converts with `.mm`. Commands are a flat, ordered list; the bridge executes them in one `start_operation('DesignForge build', true)`, commits or aborts atomically, and returns per-command results (`entity persistent_id`s) plus model stats.

```json
{"op":"ensure_material","code":"MFC18-W1000","name":"Egger W1000 Premium White","color":"#F4F4F1","texture_url":null,"grain_deg":0}
{"op":"ensure_tag","name":"DF_Fronts"}
{"op":"define_panel","def_key":"p:873x541x18:MFC18-W1000","name":"Shelf 873×541","length":873,"width":541,"thickness":18,
 "material":"MFC18-W1000","holes":[{"face":"top","x":10,"y":37,"d":5}],"attrs":{"role":"adjustable_shelf","cut_length":873,"cut_width":540,"edge_band":{"L1":"EB-W1000-1.0"}}}
{"op":"group","key":"carcass/section_1","name":"Section 1","parent":"carcass","tag":"DF_Carcass"}
{"op":"place","def_key":"p:873x541x18:MFC18-W1000","instance_key":"s1.c0.shelf1","parent":"carcass/section_1","transform":[...16],"tag":"DF_Carcass"}
```

### 3.4 Agent job lifecycle

1. `claim` → ticket with PartGraph + signed upload URLs + deadline.
2. `engine.health()`; if SketchUp unhealthy → supervisor restarts it (≤ 60 s) and job continues; else `fail(retryable)`.
3. `df_new_model` (fresh document; template with units = mm, our styles).
4. Compile → `df_execute_batch` (chunks of ≤ 400 commands to keep each socket message < ~2 MB; still one undo op per chunk).
5. `df_add_scenes`, then exports in order: `skp` → `png` scenes → `obj` → `stl` → `dxf`.
6. Verify: bridge returns model bounding box; agent compares with `graph.bbox` (± 1 mm) and part count. Mismatch ⇒ fail (bug, not retry).
7. Upload files to signed URLs, `complete` with sha256s.
8. Every 50 jobs or RSS > 3 GB → graceful SketchUp restart.

Heartbeats every 5 s; job hard timeout 5 min; a job killed twice ⇒ terminal failure and Sentry alert with the PartGraph attached (it's a reproducible input).

### 3.5 Security of the MCP surface

- MCP server is launched by the agent over **stdio** — never listens on a network port.
- Bridge TCP socket binds to `127.0.0.1` only, requires a per-boot random token in each message.
- Production build of the forked server **removes `eval_ruby`**. Debug builds keep it behind an env flag.
- Commands are validated by Pydantic on the Python side and by a whitelist of `op`s on the Ruby side; file paths restricted to a job temp dir.
- VM has egress only to the API and Storage domains.

## 4. Geometry farm operations

| Concern | Decision |
|---|---|
| Image | Packer-built Windows Server 2022 AMI: SketchUp Pro (pinned version), bridge `.rbz` installed, auto-logon user, SketchUp preferences pre-seeded (no welcome screen, no update check, no crash dialog), agent as a scheduled task "at logon" (needs the interactive desktop, so **not** a Windows service). |
| Scaling | MVP: 1 node always on. V1: ASG with min 1 / max N, scale on `count(geometry_jobs where status='queued')` published as a CloudWatch metric. Cold start of a Windows node is 3–6 min ⇒ keep a warm floor. |
| Versioning | Each node advertises `sketchup_version` + `bridge_version`; jobs record the producer; cache key includes bridge version. |
| Cost control | Geometry is triggered **only after Spec approval**, and cached by `graph_hash`. The glTF preview (Linux, ms) covers all pre-approval 3D needs. |
| Dev loop | Run SketchUp + bridge + agent on your own machine pointed at local API. Use the MCP Inspector against the forked server to debug tools interactively. |

## 5. `GltfEngine` — the always-available engine

Pure Python (trimesh), runs in worker-core on Linux. Builds boxes from the PartGraph, applies material colours, writes `.glb` (web viewer), `.stl`, `.obj`. Used for: Spec Review live preview, fallback deliverables when the farm is down, and as a geometry oracle in tests (compare bbox/volume with SketchUp output).

## 6. Exit strategy — `SkpSdkEngine` (V1/V2)

The SketchUp C API (SDK) can create and write `.skp` files **without the SketchUp application** (Windows/macOS). A small C++ CLI `skpwriter part_graph.json out.skp` gives: no GUI, no modal dialogs, many concurrent jobs per VM, seconds per model, and a very different licensing posture. Scenes/exports beyond `.skp` remain on the MCP engine or move to our own renderers.

Because everything goes through `GeometryEngine.build(graph, request)`, switching is a config flag per org/plan: `GEOMETRY_ENGINE=sketchup_mcp|skp_sdk|gltf`.

Recommendation: ship MVP with `SketchUpMcpEngine` (it is what designers trust and it validates the vision); start `skpwriter` as soon as you have paying users and the Trimble licensing answer.
