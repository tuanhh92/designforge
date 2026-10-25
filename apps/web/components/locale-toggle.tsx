"use client";

import { useI18n } from "@/components/i18n-provider";
import { LOCALES } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LABEL = { vi: "VI", en: "EN" } as const;
const NAME = { vi: "Tiếng Việt", en: "English" } as const;

export function LocaleToggle() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div role="group" aria-label={t("locale.label")} className="flex rounded-md border p-0.5 text-xs font-medium">
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          title={NAME[l]}
          aria-pressed={locale === l}
          onClick={() => locale !== l && setLocale(l)}
          className={cn(
            "rounded px-2 py-1 transition-colors",
            locale === l ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {LABEL[l]}
        </button>
      ))}
    </div>
  );
}
