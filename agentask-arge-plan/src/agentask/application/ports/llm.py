"""LLMPort: kurum içi model. Unavailable normal bir sonuçtur; dış/yedek model yoktur.

Model yalnız tipli seçim önerir (operation id + argüman). Çıktı çağıranda şema/enum ile yeniden doğrulanır."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class LLMAvailability:
    available: bool
    reason: str


class LLMUnavailableError(RuntimeError):
    """Model kapalı, erişilemez veya zaman aşımı. Kullanıcıya kural/manuel yol sunulur."""


class LLMRejected(ValueError):
    """Model yanıtı JSON nesnesi değil veya sözleşmeye uymuyor; reddedilir, kullanılmaz."""


class LLMPort(Protocol):
    def availability(self) -> LLMAvailability: ...

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_output_tokens: int
    ) -> dict[str, Any]: ...
