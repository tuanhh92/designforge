"use client";

import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { JobEvent, JobOut } from "@/lib/api";
import { intlLocale, tCode } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";

function JobIcon({ status }: { status: JobOut["status"] }) {
  if (status === "running") return <Loader2 className="size-4 animate-spin" />;
  if (status === "succeeded") return <CheckCircle2 className="size-4 text-success" />;
  if (status === "failed") return <XCircle className="size-4 text-destructive" />;
  return <CircleDashed className="size-4 text-muted-foreground" />;
}

export function JobProgress({ jobs, events }: { jobs: JobOut[]; events: JobEvent[] }) {
  const { t, locale } = useI18n();
  const latest = jobs[0];
  if (!latest) return null;
  const stepKey = `job.step.${latest.step}` as MessageKey;
  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><JobIcon status={latest.status} /> {t(`job.kind.${latest.kind}`)}</CardTitle>
        <CardDescription>
          {t(`job.status.${latest.status}`)}
          {latest.step ? ` · ${tCode(t, locale, stepKey, undefined, latest.step)}` : ""}
          {latest.attempts > 1 ? ` · ${t("job.attempt", { attempt: latest.attempts, max: latest.max_attempts })}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Progress value={Math.round((latest.status === "succeeded" ? 1 : latest.progress) * 100)} />
        {latest.error && <p className="text-sm text-destructive">{latest.error.message}</p>}
        <ol className="max-h-48 space-y-1 overflow-y-auto font-mono text-xs">
          {events.map((e) => (
            <li key={e.id} className={cn("flex gap-2", e.level === "error" && "text-destructive", e.level === "warning" && "text-warning")}>
              <span className="shrink-0 text-muted-foreground">{new Date(e.ts).toLocaleTimeString(intlLocale(locale))}</span>
              {e.level !== "info" && <AlertTriangle className="size-3 shrink-0 translate-y-0.5" />}
              <span>{tCode(t, locale, e.code, e.params, e.message)}</span>
            </li>
          ))}
        </ol>
        {jobs.length > 1 && (
          <div className="flex flex-wrap gap-3 border-t pt-3 text-xs text-muted-foreground">
            {jobs.slice(1, 6).map((j) => (
              <span key={j.id} className="flex items-center gap-1"><JobIcon status={j.status} /> {t(`job.kind.${j.kind}`)}</span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
