import { en, vi, type MessageKey } from "./messages";

export type Locale = "vi" | "en";
export const LOCALES: Locale[] = ["vi", "en"];
/** The product launches in Vietnam: Vietnamese unless the user switches. */
export const DEFAULT_LOCALE: Locale = "vi";
export const LOCALE_COOKIE = "df_locale";

const DICTS: Record<Locale, Record<MessageKey, string>> = { en, vi };

export type Params = Record<string, string | number | null | undefined>;
export type T = (key: MessageKey, params?: Params) => string;

export function isLocale(v: unknown): v is Locale {
  return v === "vi" || v === "en";
}

function fill(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (m, k) => (params[k] ?? m).toString());
}

export function makeT(locale: Locale): T {
  return (key, params) => fill(DICTS[locale][key] ?? en[key] ?? key, params);
}

/** Server messages: translate by code when we know it, else show the server's English text. */
export function tCode(t: T, locale: Locale, code: string | null | undefined, params: Params | undefined, fallback: string): string {
  if (!code || !(code in en)) return fallback;
  return t(code as MessageKey, localizeParams(t, params));
}

/** Params that are themselves vocabulary (category, dimension) are translated too. */
function localizeParams(t: T, params?: Params): Params | undefined {
  if (!params) return params;
  const out: Params = { ...params };
  if (typeof out.category === "string" && `category.${out.category}` in en) out.category = t(`category.${out.category}` as MessageKey);
  if (typeof out.dimension === "string" && `dim.${out.dimension}` in en) out.dimension = t(`dim.${out.dimension}` as MessageKey);
  if (typeof out.kind === "string" && `job.kind.${out.kind}` in en) out.kind = t(`job.kind.${out.kind}` as MessageKey);
  return out;
}

export function categoryName(t: T, category: string | null | undefined): string {
  if (!category) return "—";
  const key = `category.${category}` as MessageKey;
  return key in en ? t(key) : category.replace(/_/g, " ");
}

export function materialName(t: T, code: string, fallback?: string): string {
  const key = `material.${code}` as MessageKey;
  return key in en ? t(key) : fallback ?? code;
}

// Longest first: "Top rail" must win over "Top", "Sliding door" over "Door".
const PART_PREFIXES = ["Plinth front", "Sliding door", "Hanging rail", "Fixed shelf", "Top rail", "Bottom rail",
  "Divider", "Shelf", "Door", "Top", "Bottom", "Back"] as const;

/** Generator labels are English ("Shelf S1-2"): translate the part word, keep the position code. */
export function partLabel(t: T, label: string): string {
  if (label === "Gable L") return t("part.gable_l");
  if (label === "Gable R") return t("part.gable_r");
  const prefix = PART_PREFIXES.find((p) => label === p || label.startsWith(`${p} `));
  return prefix ? t(`part.${prefix}` as MessageKey) + label.slice(prefix.length) : label;
}

export function intlLocale(locale: Locale): string {
  return locale === "vi" ? "vi-VN" : "en-GB";
}
