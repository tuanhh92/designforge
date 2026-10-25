"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Info, Loader2, Pencil, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useI18n } from "@/components/i18n-provider";
import { api, ApiError, type Catalog, type Confidence, type FurnitureSpec, type SpecIssue, type SpecOut } from "@/lib/api";
import { categoryName, materialName as localMaterialName, tCode, type T } from "@/lib/i18n";

type DoorChoice = "none" | "1L" | "1R" | "2";
type Layout = "shelves" | "hanging_top" | "hanging";
type FrontType = "hinged" | "sliding2" | "sliding3" | "none";
type Section = FurnitureSpec["sections"][number];
const RAIL = { code: "RAIL-OVAL-30" };

function layoutOf(sec: Section): Layout {
  const kinds = sec.compartments.map((c) => c.kind);
  if (kinds[0] !== "hanging") return "shelves";
  return kinds.length > 1 ? "hanging_top" : "hanging";
}

function compartmentsFor(layout: Layout, shelves: number): Section["compartments"] {
  if (layout === "hanging") return [{ kind: "hanging", height: "auto", rail: RAIL }];
  if (layout === "hanging_top") {
    return [{ kind: "hanging", height: "auto", rail: RAIL }, { kind: "shelves", height: 400, adjustable_shelves: 0 }];
  }
  return [{ kind: "shelves", height: "auto", adjustable_shelves: shelves }];
}

function frontTypeOf(spec: FurnitureSpec): FrontType {
  if (spec.fronts.style === "sliding") return spec.fronts.sliding?.leaves === 3 ? "sliding3" : "sliding2";
  return spec.sections.some((sec) => sec.doors.length > 0) ? "hinged" : "none";
}
const DIMS = ["width", "height", "depth"] as const;

function doorChoice(section: FurnitureSpec["sections"][number]): DoorChoice {
  const d = section.doors.find((x) => x.kind === "hinged");
  if (!d) return "none";
  if (d.leaves === 2) return "2";
  return d.hinge_side === "right" ? "1R" : "1L";
}

function carcassThickness(spec: FurnitureSpec): number {
  return spec.construction.carcass_thickness;
}

function ConfidenceBadge({ c, t }: { c?: Confidence[string]; t: T }) {
  if (!c) return null;
  const pct = Math.round(c.value * 100);
  const variant = c.value >= 0.85 ? "success" : c.value >= 0.5 ? "warning" : "destructive";
  const label = c.source === "user_anchor" ? t("conf.measured") : c.source === "user_edit" ? t("conf.edited")
    : c.source === "printed_dimension" ? t("conf.printed") : `${pct}%`;
  return <Badge variant={variant} title={(c.sources ?? [c.source]).join(", ")}>{label}</Badge>;
}

function IssueList({ issues }: { issues: SpecIssue[] }) {
  const { t, locale } = useI18n();
  if (!issues.length) return null;
  return (
    <ul className="space-y-2">
      {issues.map((i, k) => (
        <li key={k} className="flex gap-2 text-sm">
          {i.severity === "error" ? <AlertCircle className="size-4 shrink-0 text-destructive" />
            : i.severity === "warning" ? <TriangleAlert className="size-4 shrink-0 text-warning" />
            : <Info className="size-4 shrink-0 text-muted-foreground" />}
          <span>{tCode(t, locale, `issue.${i.rule_code}`, i.params, i.message)}</span>
        </li>
      ))}
    </ul>
  );
}

export function SpecPanel({ designId, spec: specOut, catalog, busy, onSaved }: {
  designId: string; spec: SpecOut; catalog: Catalog | null; busy: boolean; onSaved: () => void;
}) {
  const { t, locale } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<FurnitureSpec>(specOut.spec);
  const [issues, setIssues] = useState<SpecIssue[]>(specOut.issues);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (!editing) { setDraft(specOut.spec); setIssues(specOut.issues); } }, [specOut, editing]);

  // Live validation while editing (debounced).
  useEffect(() => {
    if (!editing) return;
    const timer = setTimeout(async () => {
      setValidating(true);
      try {
        setIssues((await api.validateSpec(designId, draft)).issues);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError && e.status === 422 ? t("spec.invalid") : t("spec.validation_failed"));
      } finally {
        setValidating(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [draft, editing, designId, t]);

  const hasErrors = issues.some((i) => i.severity === "error");
  const allMaterials = catalog?.materials ?? [];
  // Only boards of carcass thickness can be carcass or front material (the 8 mm back board cannot).
  const materials = allMaterials.filter((m) => m.thickness === carcassThickness(specOut.spec));
  const materialName = (code: string) => localMaterialName(t, code, allMaterials.find((m) => m.code === code)?.name);
  const conf = specOut.field_confidence;
  const s = editing ? draft : specOut.spec;

  function update(mut: (d: FurnitureSpec) => void) {
    setDraft((prev) => {
      const next = structuredClone(prev);
      mut(next);
      if (next.fronts.style !== "sliding") { // sliding doors are chosen explicitly, never inferred from sections
        const anyDoors = next.sections.some((sec) => sec.doors.length > 0);
        next.fronts.style = anyDoors ? (next.fronts.style === "none" ? "overlay_full" : next.fronts.style) : "none";
        if (anyDoors && next.fronts.handle.kind === "none") next.fronts.handle = { kind: "handle", hardware: { code: "HANDLE-BAR-128" }, position: "auto" };
      }
      return next;
    });
  }

  function setBase(kind: "plinth" | "legs" | "none") {
    update((d) => {
      d.construction.base = kind === "plinth" ? { kind, height: 100, setback: 50, material: { code: d.construction.carcass_material.code } }
        : kind === "legs" ? { kind, height: 100, leg: { code: "LEG-ADJ-100" }, kickboard: false } : { kind: "none" };
    });
  }

  function setDoors(i: number, choice: DoorChoice) {
    update((d) => {
      d.sections[i].doors = choice === "none" ? []
        : choice === "2" ? [{ kind: "hinged", leaves: 2, spans: [0, 0] }]
        : [{ kind: "hinged", leaves: 1, hinge_side: choice === "1R" ? "right" : "left", spans: [0, 0] }];
    });
  }

  function setFrontType(ft: FrontType) {
    update((d) => {
      if (ft === "sliding2" || ft === "sliding3") {
        d.fronts.style = "sliding";
        d.fronts.sliding = { leaves: ft === "sliding3" ? 3 : 2, track: { code: "SLIDING-TRACK-2" }, overlap: 40 };
        d.fronts.handle = { kind: "none" };
        d.sections.forEach((sec) => { sec.doors = []; });
        return;
      }
      d.fronts.style = "overlay_full"; // re-derived from the sections' doors by update()
      d.fronts.sliding = null;
      d.sections.forEach((sec) => {
        sec.doors = ft === "hinged" ? [{ kind: "hinged", leaves: 2, spans: [0, 0] }] : [];
      });
    });
  }

  function setLayout(i: number, layout: Layout) {
    update((d) => {
      const shelves = d.sections[i].compartments[0]?.adjustable_shelves ?? 3;
      d.sections[i].compartments = compartmentsFor(layout, layout === "shelves" ? shelves || 3 : 0);
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const res = await api.saveSpec(designId, draft);
      setIssues(res.issues);
      if (res.spec_id) { setEditing(false); onSaved(); }
      else setError(t("spec.fix_errors"));
    } catch (e) {
      setError(e instanceof ApiError && e.code?.startsWith("error.") ? t(e.code as Parameters<T>[0]) : t("spec.save_failed"));
    } finally {
      setSaving(false);
    }
  }

  const sectionsTotal = useMemo(() => s.sections.length, [s]);
  // Structured notes (code + params) are shown in the user's language; plain notes as written.
  const notes = specOut.notes_detail?.length
    ? specOut.notes_detail.map((n) => tCode(t, locale, `note.${n.code}`, n.params, n.text))
    : s.notes;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("spec.title", { category: categoryName(t, s.category) })}</CardTitle>
        <CardDescription>
          v{specOut.version} · {specOut.origin === "ai"
            ? t("spec.origin.ai", { provider: specOut.provider, model: specOut.model }) : t("spec.origin.edited")}
        </CardDescription>
        <CardAction>
          {!editing ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}><Pencil /> {t("spec.edit")}</Button>
          ) : (
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setError(null); }}>{t("spec.cancel")}</Button>
              <Button size="sm" disabled={saving || validating || hasErrors || busy} onClick={save}>
                {saving && <Loader2 className="animate-spin" />} {t("spec.save")}
              </Button>
            </div>
          )}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="grid grid-cols-3 gap-3">
          {DIMS.map((dim) => (
            <div key={dim} className="space-y-1.5">
              <Label className="justify-between text-xs text-muted-foreground">
                {t(`dim.${dim}`)} {!editing && <ConfidenceBadge c={conf[`/overall/${dim}`]} t={t} />}
              </Label>
              {editing ? (
                <Input type="number" min={250} max={4000} value={draft.overall[dim]}
                       onChange={(e) => update((d) => { d.overall[dim] = Number(e.target.value) || 0; })} />
              ) : (
                <div className="text-lg font-semibold tabular-nums">{s.overall[dim]} <span className="text-sm font-normal text-muted-foreground">mm</span></div>
              )}
            </div>
          ))}
        </section>

        <section className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("spec.carcass")}</Label>
            {editing ? (
              <NativeSelect value={draft.construction.carcass_material.code}
                            onChange={(e) => update((d) => { d.construction.carcass_material.code = e.target.value; })}>
                {materials.map((m) => <option key={m.code} value={m.code}>{materialName(m.code)}</option>)}
              </NativeSelect>
            ) : <div className="text-sm">{materialName(s.construction.carcass_material.code)}</div>}
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("spec.fronts")}</Label>
            {editing ? (
              <NativeSelect value={draft.fronts.material.code} onChange={(e) => update((d) => { d.fronts.material.code = e.target.value; })}>
                {materials.map((m) => <option key={m.code} value={m.code}>{materialName(m.code)}</option>)}
              </NativeSelect>
            ) : <div className="text-sm">{s.fronts.style === "none" ? t("spec.no_fronts") : materialName(s.fronts.material.code)}</div>}
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("spec.front_type")}</Label>
            {editing ? (
              <NativeSelect value={frontTypeOf(draft)} onChange={(e) => setFrontType(e.target.value as FrontType)}>
                <option value="hinged">{t("spec.front_type.hinged")}</option>
                <option value="sliding2">{t("spec.front_type.sliding2")}</option>
                <option value="sliding3">{t("spec.front_type.sliding3")}</option>
                <option value="none">{t("spec.front_type.none")}</option>
              </NativeSelect>
            ) : <div className="text-sm">{t(`spec.front_type.${frontTypeOf(s)}`)}</div>}
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label className="text-xs text-muted-foreground">{t("spec.base")}</Label>
            {editing ? (
              <NativeSelect value={draft.construction.base.kind} onChange={(e) => setBase(e.target.value as "plinth" | "legs" | "none")}>
                <option value="plinth">{t("spec.base.plinth")}</option>
                <option value="legs">{t("spec.base.legs")}</option>
                <option value="none">{t("spec.base.none")}</option>
              </NativeSelect>
            ) : <div className="text-sm">{t(`spec.base.${s.construction.base.kind}`)}</div>}
          </div>
        </section>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">{t("spec.sections")} <span className="text-muted-foreground">{t("spec.sections.count", { count: sectionsTotal })}</span></h3>
            {!editing && <ConfidenceBadge c={conf["/sections"]} t={t} />}
            {editing && (
              <div className="flex gap-1">
                <Button size="sm" variant="outline" disabled={draft.sections.length <= 1}
                        onClick={() => update((d) => { d.sections.pop(); })}>−</Button>
                <Button size="sm" variant="outline" disabled={draft.sections.length >= 8}
                        onClick={() => update((d) => { d.sections.push(structuredClone(d.sections[d.sections.length - 1])); })}>+</Button>
              </div>
            )}
          </div>
          <div className="grid gap-2">
            {s.sections.map((sec, i) => {
              const layout = layoutOf(sec);
              const shelves = layout === "shelves" ? sec.compartments[0]?.adjustable_shelves ?? 0 : 0;
              const sliding = s.fronts.style === "sliding";
              const doorText = { none: t("spec.doors.none"), "1L": t("spec.doors.short.1L"), "1R": t("spec.doors.short.1R"), "2": t("spec.doors.2") }[doorChoice(sec)];
              return (
                <div key={i} className="space-y-2 rounded-md border px-3 py-2 text-sm">
                  {editing ? (
                    <>
                      <div className="font-medium">S{i + 1}</div>
                      <div className="grid grid-cols-2 gap-2">
                        <Input aria-label={t("spec.section.width", { n: i + 1 })} placeholder="auto" type="number"
                               value={sec.width === "auto" ? "" : sec.width}
                               onChange={(e) => update((d) => { d.sections[i].width = e.target.value ? Number(e.target.value) : "auto"; })} />
                        <NativeSelect aria-label={t("spec.layout", { n: i + 1 })} value={layout} onChange={(e) => setLayout(i, e.target.value as Layout)}>
                          <option value="shelves">{t("spec.layout.shelves")}</option>
                          <option value="hanging_top">{t("spec.layout.hanging_top")}</option>
                          <option value="hanging">{t("spec.layout.hanging")}</option>
                        </NativeSelect>
                        {layout === "shelves" && (
                          <Input aria-label={t("spec.section.shelves", { n: i + 1 })} type="number" min={0} max={12} value={shelves}
                                 onChange={(e) => update((d) => { d.sections[i].compartments[0].adjustable_shelves = Math.max(0, Number(e.target.value) || 0); })} />
                        )}
                        {!sliding && (
                          <NativeSelect aria-label={t("spec.section.doors", { n: i + 1 })} value={doorChoice(sec)} onChange={(e) => setDoors(i, e.target.value as DoorChoice)}>
                            <option value="none">{t("spec.doors.none")}</option>
                            <option value="1L">{t("spec.doors.1L")}</option>
                            <option value="1R">{t("spec.doors.1R")}</option>
                            <option value="2">{t("spec.doors.2")}</option>
                          </NativeSelect>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-medium">S{i + 1}</span>
                      <span className="text-muted-foreground">· {sec.width === "auto" ? t("spec.auto_width") : `${sec.width} mm`}</span>
                      <span>· {t(`spec.layout.${layout}`)}{layout === "shelves" ? ` (${t("spec.shelves", { count: shelves })})` : ""}</span>
                      {!sliding && <span>· {doorText}</span>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {editing && <p className="text-xs text-muted-foreground">{t(draft.fronts.style === "sliding" ? "spec.columns_hint_sliding" : "spec.columns_hint")}</p>}
        </section>

        {(issues.length > 0 || validating) && (
          <section className="space-y-2">
            <h3 className="flex items-center gap-2 text-sm font-medium">{t("spec.checks")} {validating && <Loader2 className="size-3 animate-spin" />}</h3>
            <IssueList issues={issues} />
          </section>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {notes.length > 0 && (
          <section className="space-y-1">
            <h3 className="text-sm font-medium">{t("spec.notes")}</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </section>
        )}
      </CardContent>
    </Card>
  );
}
