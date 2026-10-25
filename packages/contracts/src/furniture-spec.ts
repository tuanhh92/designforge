/**
 * FurnitureSpec — design INTENT. Produced by AI (Stage 2), edited by humans in Spec Review,
 * validated by the Rule Engine, consumed by the deterministic Parametric Generator (Stage 3).
 *
 * Rules for this file:
 *  - All lengths are integer millimetres (`Mm`).
 *  - Keep it small and human-editable. Anything derivable (part sizes, holes) belongs in PartGraph.
 *  - Every field the LLM fills must be expressible in a strict JSON Schema (no unions without a
 *    discriminator, no open-ended maps) so it can be used as a structured-output schema.
 */

export type Mm = number; // integer millimetres
export type Uuid = string;

export type FurnitureCategory =
  | "wardrobe" | "base_cabinet" | "wall_cabinet" | "tall_cabinet" | "kitchen_run" | "tv_unit"
  | "bookcase" | "sideboard" | "chest_of_drawers" | "desk" | "bed_frame" | "shoe_cabinet"
  | "vanity" | "other";

/** Reference to a catalog item. `code` is resolved against org catalog, then global catalog. */
export interface MaterialRef { code: string }
export interface HardwareRef { code: string }

export type JoineryStyle = "top_over_gables" | "gables_over_top";
export type Connector = "minifix_dowel" | "dowel_glue" | "confirmat" | "lamello_clamex";
export type BackStyle = "inset_groove" | "rebated" | "applied" | "full_thickness" | "none";
export type FrontStyle = "overlay_full" | "overlay_half" | "inset" | "sliding" | "none";

export interface Overall {
  width: Mm;
  height: Mm;
  depth: Mm;
}

export type Base =
  | { kind: "plinth"; height: Mm; setback: Mm; material: MaterialRef }
  | { kind: "legs"; height: Mm; leg: HardwareRef; kickboard: boolean }
  | { kind: "none" };

export interface Construction {
  carcass_material: MaterialRef;          // e.g. MFC 18 white
  carcass_thickness: Mm;                  // usually 18 (16/19 regionally)
  joinery: JoineryStyle;
  connector: Connector;
  back: { style: BackStyle; material: MaterialRef; thickness: Mm; groove_inset?: Mm };
  base: Base;
  top_overhang?: { front: Mm; left: Mm; right: Mm }; // worktop / sideboard tops
  scribe_allowance?: { left: Mm; right: Mm; top: Mm }; // fitted furniture against walls
}

export type HandleSpec =
  | { kind: "handle"; hardware: HardwareRef; position: "top" | "middle" | "bottom" | "auto" }
  | { kind: "push_to_open"; hardware: HardwareRef }
  | { kind: "gola_profile"; hardware: HardwareRef }
  | { kind: "integrated_groove"; depth: Mm }
  | { kind: "none" };

export interface Fronts {
  style: FrontStyle;
  material: MaterialRef;
  thickness: Mm;
  reveal: Mm;               // gap between fronts, typically 2–3
  handle: HandleSpec;
  hinge?: HardwareRef;      // default from rule pack
  /** style "sliding": one set of sliding doors across the whole width, on a double track. */
  sliding?: { leaves: 2 | 3; track: HardwareRef; overlap: Mm };
}

/** Contents of a section, listed BOTTOM → TOP. Heights may be "auto" to share remaining space. */
export type Compartment =
  | { kind: "shelves"; height: Mm | "auto"; adjustable_shelves: number; fixed_top_shelf?: boolean }
  | { kind: "hanging"; height: Mm | "auto"; rail: HardwareRef }
  | { kind: "drawers"; height: Mm | "auto"; count: number; slide: HardwareRef;
      internal?: boolean;                         // inside a door (wardrobe) vs exposed front
      front_heights?: Mm[] }                      // optional explicit split, else equal
  | { kind: "open"; height: Mm | "auto" }
  | { kind: "appliance"; height: Mm | "auto"; appliance: "oven" | "microwave" | "dishwasher" | "fridge" | "sink" };

export type DoorConfig =
  | { kind: "none" }
  | { kind: "hinged"; leaves: 1 | 2; hinge_side?: "left" | "right";   // hinge_side for leaves=1
      spans: [number, number] }                                         // compartment index range [from,to]
  | { kind: "sliding"; leaves: 2 | 3; track: HardwareRef; spans: [number, number] }
  | { kind: "lift_up"; mechanism: HardwareRef; spans: [number, number] };

export interface Section {
  width: Mm | "auto";            // inner clear width or "auto" to split remaining equally
  compartments: Compartment[];   // bottom → top
  doors: DoorConfig[];
}

export interface StyleInfo {
  tags: string[];                // ["scandinavian","handleless","minimal"]
  finish: string;                // "matte white", "oak veneer natural"
  colour_hex?: string;
}

export interface FurnitureSpec {
  schema_version: "1.0";
  category: FurnitureCategory;
  name: string;
  overall: Overall;
  construction: Construction;
  fronts: Fronts;
  sections: Section[];           // left → right, viewed from front
  style: StyleInfo;
  rule_pack: { id: Uuid; version: number };
  notes: string[];               // free text for things the schema cannot yet express (surfaced in UI)
}

/** Per-field provenance shown as confidence badges in Spec Review. Key = JSON pointer. */
export type FieldConfidence = Record<string, {
  value: number;                 // 0..1
  source: "user_anchor" | "user_edit" | "vision_measured" | "category_prior" | "rule_default";
  rationale?: string;
}>;

export interface SpecIssue {
  rule_code: string;
  severity: "info" | "warning" | "error";
  path: string;                  // JSON pointer
  message: string;
  suggestion?: JsonPatchOp[];
}

export type JsonPatchOp =
  | { op: "add" | "replace" | "test"; path: string; value: unknown }
  | { op: "remove"; path: string }
  | { op: "move" | "copy"; from: string; path: string };
