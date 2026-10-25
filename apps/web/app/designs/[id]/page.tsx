"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import { JobProgress } from "@/components/job-progress";
import { ArtifactList, PartsTable, SceneRenders } from "@/components/parts-and-files";
import { SpecPanel } from "@/components/spec-panel";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/i18n-provider";
import { api, ApiError, type Catalog, type DesignDetail, type Part } from "@/lib/api";
import { tCode } from "@/lib/i18n";

// three.js needs the browser: never render it on the server.
const ModelViewer = dynamic(() => import("@/components/model-viewer"), {
  ssr: false,
  loading: () => <div className="flex h-[480px] items-center justify-center rounded-lg border"><Loader2 className="animate-spin" /></div>,
});

const POLL_MS = 1500;

export default function DesignPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useI18n();
  const [design, setDesign] = useState<DesignDetail | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [parts, setParts] = useState<Part[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    try {
      setDesign(await api.getDesign(id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("detail.load_failed"));
    }
  }, [id, t]);

  useEffect(() => { load(); api.catalog().then(setCatalog).catch(() => {}); }, [load]);

  // Poll while a job is queued or running.
  useEffect(() => {
    if (!design?.busy) return;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [design?.busy, load]);

  const graphUrl = design?.artifacts.find((a) => a.kind === "part_graph")?.url;
  useEffect(() => {
    if (!graphUrl) { setParts([]); return; }
    api.parts(graphUrl).then(setParts).catch(() => setParts([]));
  }, [graphUrl]);

  async function act(fn: () => Promise<unknown>) {
    setActing(true);
    try { await fn(); await load(); } catch (e) {
      setError(e instanceof ApiError && e.code?.startsWith("error.") ? t(e.code as Parameters<typeof t>[0]) : t("error.action"));
    } finally { setActing(false); }
  }

  if (!design) {
    return error
      ? <Alert variant="destructive"><AlertTitle>{t("detail.error")}</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>
      : <div className="flex justify-center py-24"><Loader2 className="animate-spin" /></div>;
  }

  const glb = design.artifacts.find((a) => a.kind === "glb");
  const statusText = design.status_message
    ? tCode(t, locale, design.status_code, design.status_params, design.status_message) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{design.name}</h1>
            <StatusBadge status={design.status} t={t} />
          </div>
          {statusText && <p className="text-sm text-muted-foreground">{statusText}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={design.busy || acting} onClick={() => act(() => api.reanalyze(id))}>
            <Sparkles /> {t("detail.reanalyse")}
          </Button>
          <Button variant="outline" size="sm" disabled={design.busy || acting || !design.spec} onClick={() => act(() => api.rebuild(id))}>
            <RefreshCw /> {t("detail.rebuild")}
          </Button>
        </div>
      </div>

      {error && <Alert variant="destructive"><AlertTitle>{t("detail.error")}</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      {design.status === "unsupported" && (
        <Alert><AlertTitle>{t("detail.unsupported.title")}</AlertTitle><AlertDescription>{statusText}</AlertDescription></Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-6">
          {glb ? <ModelViewer key={glb.id} url={glb.url} /> : (
            <div className="flex h-[480px] flex-col items-center justify-center gap-2 rounded-lg border text-muted-foreground">
              {design.busy ? <><Loader2 className="animate-spin" /> {t("detail.building")}</> : t("detail.no_model")}
            </div>
          )}
          <SceneRenders artifacts={design.artifacts} />
          {parts.length > 0 && <PartsTable parts={parts} />}
        </div>
        <div className="min-w-0 space-y-6">
          <JobProgress jobs={design.jobs} events={design.events} />
          {design.spec && (
            <SpecPanel designId={id} spec={design.spec} catalog={catalog} busy={design.busy} onSaved={load} />
          )}
          {design.artifacts.length > 0 && <ArtifactList artifacts={design.artifacts} />}
          <div className="grid grid-cols-3 gap-2">
            {design.images.map((img) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={img.id} src={img.url} alt={t("detail.reference")} className="aspect-square w-full rounded-md border object-cover" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
