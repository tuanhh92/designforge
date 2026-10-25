"""The vision client must be closed inside the analysis call (no network: the model is faked)."""
import asyncio
import io
from uuid import uuid4

import pytest
from PIL import Image

from df_ai.vision import CallMeta
from df_services import analysis
from df_services.config import Settings


class FakeClient:
    closed = False

    async def close(self):
        FakeClient.closed = True


class FakeModel:
    def __init__(self, fail: bool):
        self.client, self.fail = FakeClient(), fail


@pytest.fixture()
def image(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    analysis.get_storage.cache_clear()
    buf = io.BytesIO()
    Image.new("RGB", (400, 400), "#C8A27A").save(buf, "JPEG")
    analysis.get_storage().put("img.jpg", buf.getvalue())
    yield analysis.SourceImage(uuid4(), "img.jpg")
    analysis.get_storage.cache_clear()


@pytest.mark.parametrize("fail", [False, True])
def test_client_closed_on_success_and_failure(image, monkeypatch, fail):
    FakeClient.closed = False
    obs = analysis.mock_analyze([analysis.get_storage().get("img.jpg")], "wardrobe").observation

    async def fake_extract(model, **_):
        if model.fail:
            raise RuntimeError("provider error")
        return obs, CallMeta("openai", "fake", "p", 0, 0, 0)

    monkeypatch.setattr(analysis, "_vision_model", lambda s: FakeModel(fail))
    monkeypatch.setattr(analysis, "extract_with_repair", fake_extract)
    settings = Settings(ai_provider="openai", openai_api_key="x")
    if fail:
        with pytest.raises(RuntimeError):
            asyncio.run(analysis.analyze([image], None, None, settings))
    else:
        assert asyncio.run(analysis.analyze([image], None, None, settings)).observation == obs
    assert FakeClient.closed
