"""Yapılandırılmış otomasyon uygulamaları (AUTOMATION_APPLICATIONS_JSON).

Listede bulunmak yetki değildir: rol, yayın ve oturum kontrolleri ayrıca uygulanır.
Uygulama kimliği katalogdaki `application_id` ile aynı anlamı taşır;
yayımlanmış işlemler bu kimlikle kapsamlanır.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentask.domain.origins import origin_of

APPLICATION_ID_PATTERN = r"^[a-z][a-z0-9_]{0,60}$"


class AutomationApplication(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=APPLICATION_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=2000)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError("base_url http(s)://host[:port][/yol] biçiminde olmalı")
        if parts.username is not None or parts.password is not None:
            raise ValueError("base_url kimlik bilgisi içeremez")
        if parts.fragment:
            raise ValueError("base_url # parçası içeremez")
        return value.strip()

    @property
    def origin(self) -> str:
        origin = origin_of(self.base_url)
        assert origin is not None  # _base_url doğruladı
        return origin

    def public(self) -> dict[str, str]:
        """Frontend'e giden alanlar (allowlist)."""
        return {"id": self.id, "name": self.name, "base_url": self.base_url}


class ApplicationRegistry:
    def __init__(self, applications: Iterable[AutomationApplication]) -> None:
        self._items = tuple(applications)
        self._by_id = {a.id: a for a in self._items}

    def __iter__(self) -> Any:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def get(self, application_id: str) -> AutomationApplication | None:
        return self._by_id.get(application_id)

    def public(self) -> list[dict[str, str]]:
        return [a.public() for a in self._items]
