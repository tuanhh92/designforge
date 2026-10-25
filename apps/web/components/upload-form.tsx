"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ImagePlus, Loader2, Ruler, X } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/components/i18n-provider";
import { api, ApiError } from "@/lib/api";
import { categoryName } from "@/lib/i18n";
import { cn, formatBytes } from "@/lib/utils";

const MAX_FILES = 6;
const MAX_BYTES = 20 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];
const CATEGORIES = ["wardrobe", "tall_cabinet", "bookcase", "base_cabinet", "wall_cabinet", "sideboard",
  "shoe_cabinet", "tv_unit", "chest_of_drawers", "vanity"];

interface Picked { file: File; url: string }

export function UploadForm() {
  const router = useRouter();
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<Picked[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => () => picked.forEach((p) => URL.revokeObjectURL(p.url)), [picked]);

  function addFiles(files: FileList | File[]) {
    setError(null);
    const next = [...picked];
    for (const f of Array.from(files)) {
      if (!TYPES.includes(f.type)) { setError(t("upload.bad_type", { name: f.name })); continue; }
      if (f.size > MAX_BYTES) { setError(t("upload.too_large", { name: f.name, max_mb: 20 })); continue; }
      if (next.length >= MAX_FILES) { setError(t("upload.too_many", { max: MAX_FILES })); break; }
      if (next.some((p) => p.file.name === f.name && p.file.size === f.size)) continue;
      next.push({ file: f, url: URL.createObjectURL(f) });
    }
    setPicked(next);
  }

  function remove(i: number) {
    URL.revokeObjectURL(picked[i].url);
    setPicked(picked.filter((_, k) => k !== i));
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!picked.length) { setError(t("upload.error.need_one")); return; }
    const form = new FormData(e.currentTarget);
    form.delete("images");
    picked.forEach((p) => form.append("images", p.file, p.file.name));
    for (const key of ["category", "anchor_dimension", "anchor_value_mm", "notes", "name"]) {
      if (!form.get(key)) form.delete(key);
    }
    if (!form.get("anchor_value_mm")) form.delete("anchor_dimension");
    setSubmitting(true);
    setError(null);
    try {
      const { id } = await api.createDesign(form);
      router.push(`/designs/${id}`);
    } catch (err) {
      // Upload errors come back as upload.<reason> codes with params; show them in the user's language.
      const known = err instanceof ApiError && err.code?.startsWith("upload.");
      setError(known ? t(err.code as Parameters<typeof t>[0], err.params) : err instanceof ApiError ? err.message : t("upload.error.network"));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader>
          <CardTitle>{t("upload.images.title")}</CardTitle>
          <CardDescription>{t("upload.images.desc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
            className={cn(
              "flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-sm text-muted-foreground transition-colors",
              dragging ? "border-primary bg-accent" : "hover:bg-accent/50",
            )}
          >
            <ImagePlus className="size-8" />
            <span><span className="font-medium text-foreground">{t("upload.drop.click")}</span> {t("upload.drop.or")}</span>
            <span className="text-xs">{t("upload.drop.types")}</span>
          </button>
          <input ref={inputRef} type="file" name="images" accept={TYPES.join(",")} multiple hidden
                 onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
          {picked.length > 0 && (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {picked.map((p, i) => (
                <li key={p.url} className="group relative overflow-hidden rounded-md border">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={p.url} alt={p.file.name} className="aspect-square w-full object-cover" />
                  <div className="truncate px-2 py-1 text-xs text-muted-foreground">{p.file.name} · {formatBytes(p.file.size)}</div>
                  <button type="button" onClick={() => remove(i)} aria-label={t("upload.remove", { name: p.file.name })}
                          className="absolute right-1 top-1 rounded-full bg-background/90 p-1 opacity-0 shadow group-hover:opacity-100 focus:opacity-100">
                    <X className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{t("upload.details.title")}</CardTitle>
            <CardDescription>{t("upload.details.desc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">{t("upload.name")}</Label>
              <Input id="name" name="name" placeholder={t("upload.name.placeholder")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">{t("upload.category")}</Label>
              <NativeSelect id="category" name="category" defaultValue="">
                <option value="">{t("upload.category.auto")}</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{categoryName(t, c)}</option>)}
              </NativeSelect>
            </div>
            <div className="space-y-2">
              <Label><Ruler className="size-4" /> {t("upload.anchor")}</Label>
              <div className="grid grid-cols-[1fr_120px] gap-2">
                <NativeSelect name="anchor_dimension" defaultValue="height" aria-label={t("upload.anchor")}>
                  <option value="width">{t("dim.width")}</option>
                  <option value="height">{t("dim.height")}</option>
                  <option value="depth">{t("dim.depth")}</option>
                </NativeSelect>
                <div className="relative">
                  <Input name="anchor_value_mm" type="number" min={100} max={6000} step={1} placeholder="2400" aria-label={t("upload.anchor.value")} className="pr-10" />
                  <span className="pointer-events-none absolute right-3 top-2 text-sm text-muted-foreground">mm</span>
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="notes">{t("upload.notes")}</Label>
              <Textarea id="notes" name="notes" maxLength={1000} placeholder={t("upload.notes.placeholder")} />
            </div>
          </CardContent>
        </Card>
        {error && (
          <Alert variant="destructive">
            <AlertTitle>{t("upload.error.title")}</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          {submitting ? <><Loader2 className="animate-spin" /> {t("upload.submitting")}</> : t("upload.submit")}
        </Button>
      </div>
    </form>
  );
}
