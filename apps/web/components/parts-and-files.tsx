"use client";

import { Box, Download, FileText } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Artifact, Part } from "@/lib/api";
import { materialName, partLabel, tCode } from "@/lib/i18n";
import { formatBytes } from "@/lib/utils";

const ORDER = ["skp", "png", "glb", "obj", "stl", "parts_csv", "part_graph", "spec_json"];

export function ArtifactList({ artifacts }: { artifacts: Artifact[] }) {
  const { t, locale } = useI18n();
  const sorted = [...artifacts].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  const fake = artifacts.some((a) => a.producer.includes("fake"));
  const hasSkp = artifacts.some((a) => a.kind === "skp");
  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle>{t("files.title")}</CardTitle>
        <CardDescription>
          {hasSkp ? (fake ? t("files.fake") : t("files.sketchup")) : t("files.gltf_only")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y text-sm">
          {sorted.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 py-2">
              <span className="flex min-w-0 items-center gap-2">
                {a.kind === "skp" ? <Box className="size-4 shrink-0" /> : <FileText className="size-4 shrink-0 text-muted-foreground" />}
                <span className="truncate">{tCode(t, locale, `files.kind.${a.kind}`, undefined, a.kind)}</span>
                <span className="truncate text-xs text-muted-foreground">{a.name}</span>
                {a.producer.includes("fake") && <Badge variant="warning">{t("files.fake_badge")}</Badge>}
              </span>
              <a href={`${a.url}?download=true`} className="flex shrink-0 items-center gap-1 text-muted-foreground hover:text-foreground">
                {formatBytes(a.bytes)} <Download className="size-4" />
              </a>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function SceneRenders({ artifacts }: { artifacts: Artifact[] }) {
  const { t, locale } = useI18n();
  const pngs = artifacts.filter((a) => a.kind === "png");
  if (!pngs.length) return null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {pngs.map((p) => (
        <a key={p.id} href={p.url} target="_blank" rel="noreferrer" className="overflow-hidden rounded-md border bg-white">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={p.url} alt={p.name} className="aspect-[4/3] w-full object-contain" />
          <div className="px-2 py-1 text-xs text-muted-foreground">
            {(() => { const scene = p.name.replace(/^scene-|\.png$/g, ""); return tCode(t, locale, `scene.${scene}`, undefined, scene); })()}
          </div>
        </a>
      ))}
    </div>
  );
}

export function PartsTable({ parts }: { parts: Part[] }) {
  const { t } = useI18n();
  const sheets = new Set(parts.map((p) => p.material_code)).size;
  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle>{t("parts.title")}</CardTitle>
        <CardDescription>{t("parts.desc", { parts: parts.length, materials: sheets })}</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("parts.col.part")}</TableHead>
              <TableHead>{t("parts.col.material")}</TableHead>
              <TableHead className="text-right">{t("parts.col.finished")}</TableHead>
              <TableHead className="text-right">{t("parts.col.cut")}</TableHead>
              <TableHead>{t("parts.col.banded")}</TableHead>
              <TableHead className="text-right">{t("parts.col.ops")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {parts.map((p) => (
              <TableRow key={p.key}>
                <TableCell><div className="font-medium">{partLabel(t, p.label)}</div><div className="text-xs text-muted-foreground">{p.key}</div></TableCell>
                <TableCell title={p.material_code}>{materialName(t, p.material_code)}</TableCell>
                <TableCell className="text-right tabular-nums">{p.length} × {p.width} × {p.thickness}</TableCell>
                <TableCell className="text-right tabular-nums">{p.cut_length} × {p.cut_width}</TableCell>
                <TableCell>{Object.entries(p.edge_band).filter(([, v]) => v).map(([k]) => k).join(" ") || "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{p.operations.length}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
