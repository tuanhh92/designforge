"""Furniture Analysis Service (pipeline stage 1: image understanding).

Providers:
  openai     → GPT vision via the Responses API, strict JSON-schema output
  anthropic  → Claude vision via a forced tool call
  mock       → no network, no key: a deterministic observation derived from the image's proportions and
               colour. Lets the whole pipeline run locally; its confidences are deliberately low.
"""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass
from uuid import UUID

from PIL import Image, ImageStat

from df_ai.prompts import PERCEPTION_SYSTEM, PERCEPTION_VERSION, perception_user_prompt
from df_ai.vision import CallMeta, extract_with_repair
from df_domain.observation import ImageObservation
from df_domain.ports import ImageInput

from .catalog import DefaultCatalog
from .config import Settings, get_settings
from .storage import get_storage


@dataclass(frozen=True)
class SourceImage:
    id: UUID
    storage_key: str


@dataclass(frozen=True)
class AnalysisResult:
    observation: ImageObservation
    meta: CallMeta


def _data_url(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


async def analyze(images: list[SourceImage], category_hint: str | None, notes: str | None,
                  settings: Settings | None = None) -> AnalysisResult:
    settings = settings or get_settings()
    storage = get_storage()
    blobs = [storage.get(i.storage_key) for i in images]
    if settings.ai_provider == "mock":
        return mock_analyze(blobs, category_hint)

    inputs = [ImageInput(image_id=i.id, url=_data_url(b), role="reference") for i, b in zip(images, blobs)]
    model = _vision_model(settings)
    observation, meta = await extract_with_repair(
        model, system=PERCEPTION_SYSTEM, prompt=perception_user_prompt(category_hint, notes),
        images=inputs, schema=ImageObservation, prompt_version=PERCEPTION_VERSION,
    )
    return AnalysisResult(observation, meta)


def _vision_model(settings: Settings):
    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("AI_PROVIDER=openai but OPENAI_API_KEY is empty")
        from openai import AsyncOpenAI

        from df_ai.vision import OpenAIVisionModel
        return OpenAIVisionModel(AsyncOpenAI(api_key=settings.openai_api_key, timeout=120), settings.openai_model)
    if settings.ai_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("AI_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")
        from anthropic import AsyncAnthropic

        from df_ai.vision import AnthropicVisionModel
        return AnthropicVisionModel(AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=120), settings.anthropic_model)
    raise RuntimeError(f"unknown AI provider {settings.ai_provider}")


# ── mock provider ───────────────────────────────────────────────────────────

def mock_analyze(blobs: list[bytes], category_hint: str | None) -> AnalysisResult:
    t0 = time.monotonic()
    im = Image.open(io.BytesIO(blobs[0])).convert("RGB")
    w, h = im.size
    ratio = w / h
    # Average colour of the central region ≈ the furniture's dominant finish.
    crop = im.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
    r, g, b = (int(c) for c in ImageStat.Stat(crop).mean)
    colour_hex = f"#{r:02X}{g:02X}{b:02X}"
    material_code = DefaultCatalog().match_material("", colour_hex, None)
    colour_name = DefaultCatalog().material(material_code).sketchup_material_name.split(" ", 3)[-1]

    category = category_hint or ("wardrobe" if ratio < 0.8 else "bookcase" if ratio < 1.3 else "sideboard")
    sections = {"wardrobe": 2, "bookcase": 1, "sideboard": 3}.get(category, 2)
    doors = {"wardrobe": 3, "bookcase": 0, "sideboard": 3}.get(category, sections)
    shelves = {"bookcase": 4, "sideboard": 1}.get(category, 3)
    fronts = []
    if doors:
        for i in range(sections):
            x0, x1 = i / sections, (i + 1) / sections
            leaves = 2 if (doors > sections and i == sections - 1) else 1
            for leaf in range(leaves):
                lx0 = x0 + (x1 - x0) * leaf / leaves
                lx1 = x0 + (x1 - x0) * (leaf + 1) / leaves
                fronts.append({"x0": round(lx0, 3), "y0": 0.05, "x1": round(lx1, 3), "y1": 1.0, "kind": "door",
                               "handle_side": "right" if leaf == 0 else "left"})
    ev = "mock provider: derived from image proportions/colour, not real analysis"
    obs = ImageObservation.model_validate({
        "view": "front", "image_kind": "photo",
        "category": {"value": category, "confidence": 0.9 if category_hint else 0.3, "evidence": ev},
        "width_to_height": {"value": round(max(0.2, min(ratio, 5.0)), 3), "confidence": 0.3, "evidence": ev},
        "depth_to_width": None,
        "section_count": {"value": sections, "confidence": 0.3, "evidence": ev},
        "section_width_shares": [round(1 / sections, 4)] * sections,
        "fronts": fronts,
        "door_count": {"value": len(fronts), "confidence": 0.3, "evidence": ev},
        "drawer_count": {"value": 0, "confidence": 0.3, "evidence": ev},
        "visible_shelf_count": {"value": shelves if not doors else 0, "confidence": 0.3, "evidence": ev},
        "base_type": "plinth" if category != "sideboard" else "legs",
        "handle_type": "handle",
        "materials": [{"surface": "melamine", "colour_name": colour_name, "colour_hex": colour_hex,
                       "applies_to": "all", "confidence": 0.3, "evidence": ev}],
        "scale_cues": [], "printed_text": [], "style_tags": ["modern"],
        "construction_hints": [], "review_hints": ["Mock analysis — set AI_PROVIDER=openai or anthropic for real results."],
    })
    meta = CallMeta("mock", "mock-v1", PERCEPTION_VERSION, 0, 0, int((time.monotonic() - t0) * 1000))
    return AnalysisResult(obs, meta)
