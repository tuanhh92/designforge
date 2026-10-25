import { UploadForm } from "@/components/upload-form";
import { getT } from "@/lib/i18n/server";

export default async function NewDesignPage() {
  const { t } = await getT();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("upload.title")}</h1>
        <p className="text-muted-foreground">{t("upload.subtitle")}</p>
      </div>
      <UploadForm />
    </div>
  );
}
