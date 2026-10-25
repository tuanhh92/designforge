import type { Metadata } from "next";
import Link from "next/link";
import { Hammer } from "lucide-react";
import { I18nProvider } from "@/components/i18n-provider";
import { LocaleToggle } from "@/components/locale-toggle";
import { getT } from "@/lib/i18n/server";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: "DesignForge", description: t("app.tagline") };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { locale, t } = await getT();
  return (
    <html lang={locale}>
      <body className="min-h-screen">
        <I18nProvider initialLocale={locale}>
          <header className="border-b bg-card">
            <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
              <Link href="/" className="flex items-center gap-2 font-semibold">
                <Hammer className="size-5" /> DesignForge
              </Link>
              <nav className="flex gap-4 text-sm text-muted-foreground">
                <Link href="/" className="hover:text-foreground">{t("nav.new")}</Link>
                <Link href="/designs" className="hover:text-foreground">{t("nav.designs")}</Link>
              </nav>
              <div className="ml-auto"><LocaleToggle /></div>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
        </I18nProvider>
      </body>
    </html>
  );
}
