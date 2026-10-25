/**
 * PartGraph — the manufacturable model. Generated deterministically from a FurnitureSpec.
 * Source of truth for SketchUp geometry, drawings, cut list, BOM and CNC.
 *
 * Coordinate system (matches SketchUp after unit conversion):
 *   X = width (left → right), Y = depth (front → back), Z = height (floor → up). Origin = front-left-floor.
 * Part-local frame: length along local X, width along local Y, thickness along local Z,
 *   origin at the part's min corner. `transform` maps part-local → assembly/world.
 */
import type { Mm, Uuid } from "./furniture-spec";

export type Grain = "none" | "length" | "width";
export type PartFace = "top" | "bottom" | "front" | "back" | "left" | "right";
/** Edge names in part-local terms: L1/L2 = the two long edges, W1/W2 = the two short edges. */
export type EdgeName = "L1" | "L2" | "W1" | "W2";

export type PartRole =
  | "gable" | "divider" | "top" | "bottom" | "fixed_shelf" | "adjustable_shelf" | "back"
  | "plinth_front" | "plinth_back" | "plinth_rail" | "rail_front" | "rail_back" | "stretcher"
  | "door" | "drawer_front" | "drawer_side" | "drawer_back" | "drawer_bottom" | "drawer_box"
  | "worktop" | "filler" | "scribe" | "kickboard";

/** 4×4 column-major affine matrix in mm. Only rotations by multiples of 90° in MVP. */
export type Transform = [
  number, number, number, number,
  number, number, number, number,
  number, number, number, number,
  number, number, number, number,
];

export type Operation =
  | { kind: "drill"; face: PartFace; x: Mm; y: Mm; diameter: Mm; depth: Mm | "through"; tool_hint?: string; source: string }
  | { kind: "groove"; face: PartFace; x1: Mm; y1: Mm; x2: Mm; y2: Mm; width: Mm; depth: Mm; source: string }
  | { kind: "rebate"; edge: EdgeName; face: PartFace; width: Mm; depth: Mm; source: string }
  | { kind: "pocket"; face: PartFace; polygon: [Mm, Mm][]; depth: Mm; source: string }
  | { kind: "cutout"; polygon: [Mm, Mm][]; source: string }          // through, e.g. sink, cable port
  | { kind: "edge_profile"; edge: EdgeName; profile: string; source: string };

export interface Part {
  key: string;                   // stable semantic key: "s2.drawer1.side_l" — survives regeneration
  role: PartRole;
  label: string;                 // "Drawer side L (S2-D1)"
  material_code: string;
  length: Mm;                    // finished size
  width: Mm;
  thickness: Mm;
  grain: Grain;
  edge_band: Partial<Record<EdgeName, string | null>>; // edge band material code per edge
  cut_length: Mm;                // finished − band thickness (− pre-mill) on banded edges
  cut_width: Mm;
  transform: Transform;
  assembly_path: string;         // "carcass/section_2/drawer_1"
  operations: Operation[];
  tags: string[];                // ["visible","front_face_outward"]
}

export interface HardwarePlacement {
  hardware_code: string;
  qty: number;
  attached_to: string[];         // part keys
  transform?: Transform;         // for 3D placement of hardware proxies
  params?: Record<string, unknown>;
}

export interface Joint {
  kind: "minifix_dowel" | "dowel_glue" | "confirmat" | "groove_fit" | "screw";
  parts: [string, string];
  positions: Mm[];               // along the joint line, from front
}

export interface AssemblyNode {
  path: string;                  // "carcass/section_2"
  label: string;
  children: string[];            // child assembly paths
  part_keys: string[];
}

export interface PartGraph {
  schema_version: "1.0";
  spec_hash: string;
  generator_version: string;     // "df_parametric@0.4.2"
  rule_pack: { id: Uuid; version: number };
  bbox: { width: Mm; height: Mm; depth: Mm };
  parts: Part[];
  hardware: HardwarePlacement[];
  joints: Joint[];
  assemblies: AssemblyNode[];
  graph_hash: string;            // sha256 of canonical JSON (sorted keys) excluding this field
}
