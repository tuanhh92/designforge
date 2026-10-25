import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api, type DesignSummary } from "@/lib/api";
import { categoryName } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";

export default async function DesignsPage() {
  const { t } = await getT();
  let designs: DesignSummary[] = [];
  let error = false;
  try {
    designs = await api.listDesigns();
  } catch {
    error = true;
  }
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("designs.title")}</h1>
        <Button asChild><Link href="/">{t("nav.new")}</Link></Button>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertTitle>{t("designs.api_down.title")}</AlertTitle>
          <AlertDescription>{t("designs.api_down.body")}</AlertDescription>
        </Alert>
      )}
      {!error && designs.length === 0 && <p className="text-muted-foreground">{t("designs.empty")}</p>}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {designs.map((d) => (
          <li key={d.id}>
            <Link href={`/designs/${d.id}`}>
              <Card className="gap-3 overflow-hidden py-0 transition-shadow hover:shadow-md">
                {d.cover_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={d.cover_url} alt="" className="aspect-[4/3] w-full object-cover" />
                ) : <div className="aspect-[4/3] bg-muted" />}
                <CardContent className="space-y-2 px-4 pb-4">
                  <div className="truncate font-medium">{d.name}</div>
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>{categoryName(t, d.category)}</span>
                    <StatusBadge status={d.status} t={t} />
                  </div>
                </CardContent>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
