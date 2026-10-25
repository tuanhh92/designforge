"""VisionModel port + OpenAI / Anthropic adapters + ensemble.

Model IDs come from settings (env), never hard-coded at call sites.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Protocol, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from df_domain.ports import ImageInput

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class CallMeta:
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    trace_id: str | None = None


class VisionModel(Protocol):
    provider: str
    model: str

    async def extract(
        self, *, system: str, prompt: str, images: Sequence[ImageInput], schema: type[T], prompt_version: str
    ) -> tuple[T, CallMeta]: ...


UNSUPPORTED_STRICT_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                               "minLength", "maxLength", "minItems", "maxItems", "pattern", "format")


def to_strict_schema(model: type[BaseModel]) -> dict:
    """OpenAI strict mode needs every property `required` and `additionalProperties: false`
    everywhere; optional fields become `anyOf [T, null]`. Walk the Pydantic schema and enforce it."""
    schema = model.model_json_schema()

    def walk(node: dict) -> None:
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for key in ("properties", "$defs"):
            for child in node.get(key, {}).values():
                walk(child)
        for key in ("items", "anyOf", "oneOf", "allOf"):
            val = node.get(key)
            for child in val if isinstance(val, list) else [val] if isinstance(val, dict) else []:
                walk(child)
        node.pop("default", None)
        for kw in UNSUPPORTED_STRICT_KEYWORDS:  # Pydantic re-validates these after the call
            node.pop(kw, None)

    walk(schema)
    return schema


class OpenAIVisionModel:
    provider = "openai"

    def __init__(self, client, model: str):  # client: openai.AsyncOpenAI
        self.client, self.model = client, model

    async def extract(self, *, system, prompt, images, schema, prompt_version):
        content = [{"type": "input_text", "text": prompt}]
        content += [{"type": "input_image", "image_url": img.url} for img in images]
        t0 = time.monotonic()
        resp = await self.client.responses.create(
            model=self.model,
            instructions=system,
            input=[{"role": "user", "content": content}],
            text={"format": {"type": "json_schema", "name": schema.__name__,
                             "schema": to_strict_schema(schema), "strict": True}},
        )
        parsed = schema.model_validate_json(resp.output_text)
        return parsed, CallMeta(self.provider, self.model, prompt_version, resp.usage.input_tokens,
                                resp.usage.output_tokens, int((time.monotonic() - t0) * 1000))


class AnthropicVisionModel:
    provider = "anthropic"

    def __init__(self, client, model: str, max_tokens: int = 8000):  # client: anthropic.AsyncAnthropic
        self.client, self.model, self.max_tokens = client, model, max_tokens

    async def extract(self, *, system, prompt, images, schema, prompt_version):
        content = [{"type": "image", "source": _anthropic_image_source(img.url)} for img in images]
        content.append({"type": "text", "text": prompt})
        tool = {"name": "record_result", "description": f"Record the {schema.__name__}.",
                "input_schema": schema.model_json_schema()}
        t0 = time.monotonic()
        resp = await self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
            tools=[tool], tool_choice={"type": "tool", "name": "record_result"},
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        parsed = schema.model_validate(block.input)
        return parsed, CallMeta(self.provider, self.model, prompt_version, resp.usage.input_tokens,
                                resp.usage.output_tokens, int((time.monotonic() - t0) * 1000))


def _anthropic_image_source(url: str) -> dict:
    """Anthropic takes base64 for inline images and a URL source for hosted ones."""
    if url.startswith("data:"):
        header, data = url.split(",", 1)
        return {"type": "base64", "media_type": header[5:].split(";", 1)[0], "data": data}
    return {"type": "url", "url": url}


async def extract_with_repair(model: VisionModel, *, attempts: int = 2, **kwargs):
    """One repair round on schema violation: re-ask with the validation error appended."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await model.extract(**kwargs)
        except ValidationError as e:  # noqa: PERF203
            last = e
            kwargs = {**kwargs, "prompt": kwargs["prompt"] + f"\n\nYour previous answer failed validation:\n{e}\nReturn a corrected answer."}
    raise last  # type: ignore[misc]


async def ensemble(models: Sequence[VisionModel], **kwargs):
    """Run models in parallel; return all successful results. Fusion is done by the caller
    (df_ai.fusion) because it is schema-specific (counts vs ratios vs enums)."""
    results = await asyncio.gather(*(extract_with_repair(m, **kwargs) for m in models), return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception)]
    if not ok:
        raise RuntimeError(f"all vision models failed: {[repr(r) for r in results]}")
    return ok
