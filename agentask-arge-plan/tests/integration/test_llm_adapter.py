"""httpx LLM adapteri — yerel sahte OpenAI uyumlu sunucuyla (gerçek model değil). Dış fallback yok."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentask.application.ports.llm import LLMRejected, LLMUnavailableError
from agentask.config import load_settings
from agentask.infrastructure.llm.httpx_llm import HttpxLLM
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from tests.conftest import EnvFileFactory
from tests.support_lab import free_port


class FakeModel:
    def __init__(self) -> None:
        self.mode = "schema_ok"
        self.requests: list[dict[str, Any]] = []
        app = FastAPI()

        @app.post("/v1/chat/completions")
        async def complete(request: Request) -> JSONResponse:
            body = await request.json()
            self.requests.append({"body": body, "auth": request.headers.get("authorization")})
            if self.mode == "no_schema" and "response_format" in body:
                return JSONResponse({"error": "response_format unsupported"}, 400)
            if self.mode == "slow":
                await asyncio.sleep(3)
            content = {"garbage": "bu json değil {"}.get(
                self.mode, json.dumps({"operation_id": "vaka_notu", "arguments": {"metin": "Arandı"}})
            )
            if self.mode == "plan":
                content = json.dumps(
                    {"steps": [{"operation_id": "vaka_notu", "arguments": {"metin": "Arandı"}}]}
                )
            if self.mode == "garbage":
                content = "bu json değil {"
            return JSONResponse({"choices": [{"message": {"content": content}}]})

        self.port = free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> FakeModel:
        self.thread.start()
        while not self.server.started:
            pass
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(5)


@pytest.fixture(scope="module")
def model() -> Iterator[FakeModel]:
    with FakeModel() as m:
        yield m


def llm(make_env_file: EnvFileFactory, model: FakeModel, **kw: str) -> HttpxLLM:
    values = {
        "LLM_ENABLED": "true",
        "LLM_BASE_URL": f"http://127.0.0.1:{model.port}/v1",
        "LLM_MODEL": "yerel-model",
        "LLM_TIMEOUT_SECONDS": "1",
        **kw,
    }
    return HttpxLLM(load_settings(make_env_file(**values)))


SCHEMA = {"type": "object", "properties": {"operation_id": {"type": "string", "enum": ["vaka_notu"]}}}


async def test_json_schema_mode_and_bearer_auth(make_env_file: EnvFileFactory, model: FakeModel) -> None:
    model.mode, model.requests[:] = "schema_ok", []
    client = llm(make_env_file, model, LLM_AUTH_MODE="bearer", LLM_API_KEY="ic-anahtar")
    out = await client.complete_json("sistem", "kullanıcı", SCHEMA, 100)
    assert out == {"operation_id": "vaka_notu", "arguments": {"metin": "Arandı"}}
    sent = model.requests[-1]
    assert sent["auth"] == "Bearer ic-anahtar"
    assert sent["body"]["response_format"]["type"] == "json_schema" and sent["body"]["max_tokens"] == 100
    assert sent["body"]["model"] == "yerel-model" and sent["body"]["temperature"] == 0


async def test_falls_back_to_strict_parse_on_same_endpoint(
    make_env_file: EnvFileFactory, model: FakeModel
) -> None:
    model.mode, model.requests[:] = "no_schema", []
    client = llm(make_env_file, model, LLM_AUTH_MODE="basic", LLM_USERNAME="u", LLM_PASSWORD="p")
    out = await client.complete_json("s", "u", SCHEMA, 50)
    assert out["operation_id"] == "vaka_notu"
    assert len(model.requests) == 2 and "response_format" not in model.requests[1]["body"]
    assert model.requests[1]["auth"].startswith("Basic ")
    await client.complete_json("s", "u", SCHEMA, 50)  # yetenek önbelleğe alınır
    assert len(model.requests) == 3


async def test_garbage_output_rejected(make_env_file: EnvFileFactory, model: FakeModel) -> None:
    model.mode = "garbage"
    with pytest.raises(LLMRejected):
        await llm(make_env_file, model).complete_json("s", "u", SCHEMA, 50)


async def test_timeout_is_unavailable_without_fallback(
    make_env_file: EnvFileFactory, model: FakeModel
) -> None:
    model.mode = "slow"
    with pytest.raises(LLMUnavailableError):
        await llm(make_env_file, model).complete_json("s", "u", SCHEMA, 50)


async def test_unreachable_endpoint_is_unavailable(make_env_file: EnvFileFactory) -> None:
    settings = load_settings(
        make_env_file(LLM_ENABLED="true", LLM_BASE_URL="http://127.0.0.1:1/v1", LLM_MODEL="m")
    )
    with pytest.raises(LLMUnavailableError):
        await HttpxLLM(settings).complete_json("s", "u", SCHEMA, 50)


async def test_disabled_llm_never_connects() -> None:
    with pytest.raises(LLMUnavailableError):
        await UnavailableLLM("disabled").complete_json("s", "u", SCHEMA, 50)


async def test_plan_schema_through_real_connector(make_env_file: EnvFileFactory, model: FakeModel) -> None:
    """F: çok adımlı plan şeması gerçek bağlayıcıdan (HttpxLLM) sahte model sunucusuna gider; yanıt yine
    kodla doğrulanır. Gerçek kurum modeli değildir (BLOCKED)."""
    from agentask.domain.assistant import CatalogOperation, CatalogParam, plan_schema, validate_model_plan

    ops = [
        CatalogOperation(
            release_id="rel-1",
            operation_id="vaka_notu",
            revision=1,
            content_hash="h",
            title="Vaka notu",
            intent_phrases=[],
            parameters=[CatalogParam(name="metin", title="Metin", max_length=50)],
        )
    ]
    model.mode, model.requests[:] = "plan", []
    client = llm(make_env_file, model)
    raw = await client.complete_json("sistem", "Arandı notu ekle", plan_schema(ops), 100)
    steps = validate_model_plan(raw, ops, "Arandı notu ekle")
    assert [(s.operation_id, s.arguments) for s in steps] == [("vaka_notu", {"metin": "Arandı"})]
    sent = model.requests[-1]["body"]["response_format"]["json_schema"]["schema"]
    assert sent["properties"]["steps"]["maxItems"] == 5
