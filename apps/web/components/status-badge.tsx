import { Badge } from "@/components/ui/badge";
import type { DesignStatus } from "@/lib/api";
import type { T } from "@/lib/i18n";

/** Pure (no hooks) so server and client components can both render it; pass the active `t`. */
export function StatusBadge({ status, t }: { status: DesignStatus; t: T }) {
  const variant =
    status === "model_ready" ? "success" : status === "failed" ? "destructive" : status === "unsupported" ? "warning" : "secondary";
  return <Badge variant={variant}>{t(`badge.${status}`)}</Badge>;
}
