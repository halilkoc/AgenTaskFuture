from __future__ import annotations

from typing import Any

from agentask.application.ports.llm import LLMAvailability, LLMUnavailableError


class UnavailableLLM:
    """LLM kapalıyken kullanılan açık 'yok' adapteri. Hiçbir bağlantı kurmaz."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def availability(self) -> LLMAvailability:
        return LLMAvailability(available=False, reason=self._reason)

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_output_tokens: int
    ) -> dict[str, Any]:
        raise LLMUnavailableError(self._reason)
