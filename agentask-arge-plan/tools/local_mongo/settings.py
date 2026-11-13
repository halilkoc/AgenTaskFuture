"""Araca özgü ayarlar: uygulamayla aynı seçili .env / ortam değişkenlerinden, LOCAL_MONGO_ önekiyle okunur.

Yalnız araç çalıştığında (LOCAL_MONGO_AUTOSTART=true veya açık araç komutu) yüklenir; araç kapalıyken
zorunlu değildir.
Önekli yazım hataları reddedilir; önek dışı anahtarlar uygulama Settings'ine aittir ve burada yok sayılır.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

PREFIX = "LOCAL_MONGO_"
_APP_KEYS = {"LOCAL_MONGO_AUTOSTART"}


class ToolConfigurationError(Exception):
    pass


class LocalMongoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        case_sensitive=False,
        extra="ignore",
        frozen=True,
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    image: str = Field(min_length=3, max_length=200, pattern=r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$")
    project: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,40}$")
    volume: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,60}$")
    port: int = Field(ge=1024, le=65535)
    start_timeout_seconds: int = Field(ge=5, le=600)
    backup_dir: Path
    root_username: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    root_password: SecretStr | None = None


def load_tool_settings(env_file: Path | None) -> LocalMongoSettings:
    known = {PREFIX + name.upper() for name in LocalMongoSettings.model_fields} | _APP_KEYS
    if env_file is not None and env_file.is_file():
        unknown = sorted(
            k for k in dotenv_values(env_file) if k.upper().startswith(PREFIX) and k.upper() not in known
        )
        if unknown:
            raise ToolConfigurationError(f"Bilinmeyen yerel Mongo aracı ayarı: {', '.join(unknown)}")
    try:
        return LocalMongoSettings(_env_file=env_file)
    except ValidationError as exc:
        fields = sorted({PREFIX + str(e["loc"][0]).upper() for e in exc.errors(include_input=False)})
        raise ToolConfigurationError(f"Geçersiz yerel Mongo aracı ayarı: {', '.join(fields)}") from None
