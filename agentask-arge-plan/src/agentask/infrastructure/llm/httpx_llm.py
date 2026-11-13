"""Kurum içi OpenAI uyumlu (ör. vLLM) chat completions adapteri.

- Auth: none | basic | bearer (Settings). TLS doğrulaması varsayılan açık; CA bundle opsiyonel.
- Yapılandırılmış çıktı: önce response_format=json_schema denenir; uç 400 ile reddederse aynı uçta
şemasız istem +
  sıkı JSON parse kullanılır (yetenek önbelleğe alınır). Başka model/uç denenmez.
- İstem/yanıt içeriği loglanmaz.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from agentask.application.ports.llm import LLMAvailability, LLMRejected, LLMUnavailableError
from agentask.config.settings import LLMAuthMode, Settings

logger = logging.getLogger(__name__)


class HttpxLLM:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        assert settings.llm_base_url is not None and settings.llm_model is not None
        self._url = str(settings.llm_base_url).rstrip("/") + "/chat/completions"
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds
        verify: bool | str = settings.llm_tls_verify
        if settings.llm_tls_verify and settings.llm_ca_bundle is not None:
            verify = str(settings.llm_ca_bundle)
        self._client_kwargs: dict[str, Any] = {
            "verify": verify,
            "timeout": self._timeout,
            "transport": transport,
        }
        self._headers: dict[str, str] = {}
        self._auth: httpx.BasicAuth | None = None
        if settings.llm_auth_mode is LLMAuthMode.BEARER and settings.llm_api_key is not None:
            self._headers["Authorization"] = f"Bearer {settings.llm_api_key.get_secret_value()}"
        elif settings.llm_auth_mode is LLMAuthMode.BASIC and settings.llm_password is not None:
            self._auth = httpx.BasicAuth(
                settings.llm_username or "", settings.llm_password.get_secret_value()
            )
        self._schema_supported: bool | None = None

    def availability(self) -> LLMAvailability:
        return LLMAvailability(available=True, reason="configured")

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                if self._auth is not None:
                    return await client.post(self._url, json=payload, headers=self._headers, auth=self._auth)
                return await client.post(self._url, json=payload, headers=self._headers)
        except httpx.HTTPError as exc:
            logger.warning("llm_unavailable type=%s", type(exc).__name__)
            raise LLMUnavailableError("model_unreachable_or_timeout") from None

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_output_tokens: int
    ) -> dict[str, Any]:
        base = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        response: httpx.Response | None = None
        if self._schema_supported is not False:
            response = await self._post(
                {
                    **base,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "agentask_choice", "schema": schema, "strict": True},
                    },
                }
            )
            if response.status_code == 400 and self._schema_supported is None:
                self._schema_supported = False
                response = None
            elif response.is_success:
                self._schema_supported = True
        if response is None:
            strict = {
                **base,
                "messages": [
                    {"role": "system", "content": system + "\nYalnız tek bir JSON nesnesi döndür."},
                    {"role": "user", "content": user},
                ],
            }
            response = await self._post(strict)
        if not response.is_success:
            logger.warning("llm_http_error status=%d", response.status_code)
            raise LLMUnavailableError(f"http_{response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMRejected("not_json") from None
        if not isinstance(parsed, dict):
            raise LLMRejected("not_object")
        return parsed
