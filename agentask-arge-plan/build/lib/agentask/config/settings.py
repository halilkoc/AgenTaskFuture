"""Tek typed Settings katmanı.

Kurallar (docs/05_CONFIGURATION.md):
- Öncelik: process environment > seçili .env dosyası.
- Zorunlu alanların varsayılanı yoktur; tek kaynak .env.example'dır (iki yerde default tutulmaz).
- Seçili dotenv içindeki bilinmeyen anahtarlar yazım hatası olarak reddedilir;
  ilgisiz process env yok sayılır.
- Boş değer "ayarlanmamış" demektir: opsiyonel alanlarda None, zorunlu alanlarda açık hata.
- Geçersiz değer sessizce default'a düşmez; hata mesajlarında girdi değeri yer almaz.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AnyHttpUrl,
    Field,
    PositiveInt,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentask.config.errors import ConfigurationError
from agentask.domain.origins import normalize_origin as _normalize_origin

MIN_SIGNING_KEY_LENGTH = 32


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DEV = "dev"
    UNCONFIGURED = "unconfigured"


class DraftBackend(StrEnum):
    LOCAL_FILE = "local_file"


class RunnerMode(StrEnum):
    LOCAL = "local"


class BrowserEngine(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class CatalogBackend(StrEnum):
    MONGO = "mongo"
    DISABLED = "disabled"


class ApprovedActionSet(StrEnum):
    NONE = "none"
    LAB = "lab"


class LLMAuthMode(StrEnum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


Port = Annotated[int, Field(ge=1, le=65535)]


def is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="forbid",
        env_ignore_empty=True,
        env_file_encoding="utf-8",
        frozen=True,
        hide_input_in_errors=True,
        validate_default=True,
    )

    # Uygulama ve kimlik
    app_env: AppEnv
    app_host: str = Field(min_length=1)
    app_port: Port
    app_timezone: str
    app_base_url: AnyHttpUrl
    auth_mode: AuthMode
    dev_auth_enabled: bool
    session_signing_key: SecretStr

    # MongoDB
    mongo_uri: SecretStr
    mongo_database: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    mongo_tls_ca_file: Path | None = None
    mongo_server_selection_timeout_ms: PositiveInt
    catalog_backend: CatalogBackend
    catalog_environment: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,30}$")
    catalog_application_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")

    # Taslak, artefakt, runner ve tarayıcı
    draft_backend: DraftBackend
    draft_directory: Path
    artifact_directory: Path
    runner_mode: RunnerMode
    browser_engine: BrowserEngine
    browser_headless: bool
    browser_executable_path: Path | None = None
    playwright_browsers_path: Path | None = None
    browser_launch_timeout_ms: PositiveInt
    browser_max_sessions: PositiveInt
    browser_max_sessions_per_user: PositiveInt
    browser_session_idle_seconds: PositiveInt

    # Hedef uygulama
    target_allowed_origins: list[str] = Field(min_length=1)
    target_base_url: AnyHttpUrl

    # Deney uygulaması (yalnızca loopback; production'da kullanılamaz)
    lab_primary_origin: str | None = None
    lab_secondary_origin: str | None = None

    # Zaman aşımı ve tarama sınırları
    action_timeout_ms: PositiveInt
    navigation_timeout_ms: PositiveInt
    readiness_timeout_ms: PositiveInt
    frame_scan_timeout_ms: PositiveInt
    frame_scan_max_depth: PositiveInt
    frame_scan_max_elements: PositiveInt
    frame_scan_concurrency: PositiveInt
    observe_timeout_ms: PositiveInt
    observe_max_frames: PositiveInt
    picker_wait_max_ms: PositiveInt

    # Çalışma sınırları
    run_directory: Path
    approved_action_set: ApprovedActionSet
    outcome_timeout_ms: PositiveInt
    reconcile_timeout_ms: PositiveInt
    table_no_progress_limit: PositiveInt
    composition_enabled: bool
    composition_max_depth: PositiveInt
    composition_max_items: PositiveInt
    run_max_steps: PositiveInt
    run_max_duration_seconds: PositiveInt
    table_max_pages: PositiveInt
    table_max_rows: PositiveInt
    recovery_max_attempts: Annotated[int, Field(ge=0)]
    session_lease_seconds: PositiveInt

    # LLM (yalnızca kurum içi; dış fallback yok)
    llm_enabled: bool
    llm_base_url: AnyHttpUrl | None = None
    llm_model: str | None = None
    llm_auth_mode: LLMAuthMode
    llm_api_key: SecretStr | None = None
    llm_username: str | None = None
    llm_password: SecretStr | None = None
    llm_tls_verify: bool
    llm_ca_bundle: Path | None = None
    llm_timeout_seconds: PositiveInt
    llm_context_tokens: PositiveInt
    llm_max_input_tokens: PositiveInt
    llm_max_output_tokens: PositiveInt
    llm_context_reserve_tokens: Annotated[int, Field(ge=0)]
    llm_max_calls_per_run: PositiveInt

    # Log ve kanıt
    log_level: LogLevel
    log_format: LogFormat
    evidence_retention_days: PositiveInt
    evidence_screenshots_enabled: bool

    # ---- alan doğrulamaları -------------------------------------------------

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("app_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("geçerli bir IANA saat dilimi olmalı") from exc
        return value

    @field_validator("session_signing_key")
    @classmethod
    def _strong_signing_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SIGNING_KEY_LENGTH:
            raise ValueError(f"en az {MIN_SIGNING_KEY_LENGTH} karakter olmalı")
        return value

    @field_validator("mongo_uri")
    @classmethod
    def _mongo_scheme(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("mongodb:// veya mongodb+srv:// ile başlamalı")
        return value

    @field_validator("target_allowed_origins")
    @classmethod
    def _origins(cls, value: list[str]) -> list[str]:
        normalized = [_normalize_origin(item) for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("tekrarlanan origin var")
        return normalized

    @field_validator("lab_primary_origin", "lab_secondary_origin")
    @classmethod
    def _lab_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        origin = _normalize_origin(value)
        if not origin.startswith("http://"):
            raise ValueError("deney uygulaması origin'i http olmalı")
        host = origin.removeprefix("http://").rsplit(":", 1)[0]
        if not is_loopback_host(host):
            raise ValueError("deney uygulaması yalnızca loopback adreste çalışabilir")
        return origin

    @field_validator("llm_model", "llm_username")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    # ---- alanlar arası kurallar ---------------------------------------------

    @model_validator(mode="after")
    def _cross_field_rules(self) -> Self:
        problems: list[str] = []
        production = self.app_env is AppEnv.PRODUCTION

        # Kimlik
        if self.auth_mode is AuthMode.DEV:
            if self.app_env is not AppEnv.DEVELOPMENT:
                problems.append("AUTH_MODE=dev yalnızca APP_ENV=development ile kullanılabilir")
            if not self.dev_auth_enabled:
                problems.append("AUTH_MODE=dev için DEV_AUTH_ENABLED=true açıkça verilmeli")
            if not is_loopback_host(self.app_host):
                problems.append("AUTH_MODE=dev yalnızca loopback APP_HOST ile kullanılabilir")
        if production:
            if self.dev_auth_enabled:
                problems.append("production ortamında DEV_AUTH_ENABLED=true kabul edilmez")
            if self.auth_mode is AuthMode.UNCONFIGURED:
                problems.append("production ortamında AUTH_MODE=unconfigured hazır kimlik değildir")

        # Hedef
        target_origin = _normalize_origin(str(self.target_base_url))
        if target_origin not in self.target_allowed_origins:
            problems.append("TARGET_BASE_URL origin'i TARGET_ALLOWED_ORIGINS içinde olmalı")

        # Deney uygulaması
        lab = (self.lab_primary_origin, self.lab_secondary_origin)
        if (lab[0] is None) != (lab[1] is None):
            problems.append("LAB_PRIMARY_ORIGIN ve LAB_SECONDARY_ORIGIN birlikte verilmeli")
        elif lab[0] is not None and lab[0] == lab[1]:
            problems.append("LAB_PRIMARY_ORIGIN ve LAB_SECONDARY_ORIGIN farklı origin olmalı")
        if production and (lab[0] is not None or lab[1] is not None):
            problems.append("production ortamında LAB_* deney uygulaması ayarları kabul edilmez")
        if production and self.approved_action_set is ApprovedActionSet.LAB:
            problems.append("production ortamında APPROVED_ACTION_SET=lab (deney aksiyonları) kabul edilmez")

        # Gözlem bütçesi
        if self.observe_timeout_ms < self.frame_scan_timeout_ms:
            problems.append("OBSERVE_TIMEOUT_MS, FRAME_SCAN_TIMEOUT_MS değerinden küçük olamaz")

        # Browser oturumları
        if self.browser_max_sessions_per_user > self.browser_max_sessions:
            problems.append("BROWSER_MAX_SESSIONS_PER_USER, BROWSER_MAX_SESSIONS değerini aşamaz")

        # LLM
        if self.llm_enabled:
            if self.llm_base_url is None:
                problems.append("LLM_ENABLED=true iken LLM_BASE_URL zorunlu")
            if self.llm_model is None:
                problems.append("LLM_ENABLED=true iken LLM_MODEL zorunlu")
            if self.llm_auth_mode is LLMAuthMode.BEARER and self.llm_api_key is None:
                problems.append("LLM_AUTH_MODE=bearer iken LLM_API_KEY zorunlu")
            if self.llm_auth_mode is LLMAuthMode.BASIC and (
                self.llm_username is None or self.llm_password is None
            ):
                problems.append("LLM_AUTH_MODE=basic iken LLM_USERNAME ve LLM_PASSWORD zorunlu")
            if (
                self.llm_base_url is not None
                and self.llm_base_url.scheme == "http"
                and self.llm_auth_mode is not LLMAuthMode.NONE
                and production
            ):
                problems.append("production ortamında kimlik bilgisi http üzerinden LLM'e taşınamaz")
            budget = self.llm_max_input_tokens + self.llm_max_output_tokens + self.llm_context_reserve_tokens
            if budget > self.llm_context_tokens:
                problems.append(
                    "LLM_MAX_INPUT_TOKENS + LLM_MAX_OUTPUT_TOKENS + LLM_CONTEXT_RESERVE_TOKENS "
                    "LLM_CONTEXT_TOKENS değerini aşamaz"
                )
        if not self.llm_tls_verify and self.app_env is not AppEnv.DEVELOPMENT:
            problems.append("LLM_TLS_VERIFY=false yalnızca development ortamında açıkça seçilebilir")

        if problems:
            raise ValueError("; ".join(problems))
        return self

    # ---- yardımcılar --------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION


def load_settings(env_file: Path | None = None, *, use_default_env_file: bool = True) -> Settings:
    """Settings'i yükler ve doğrular.

    env_file verilirse dosya mevcut olmalıdır. Verilmezse çalışma dizinindeki .env (varsa) okunur.
    use_default_env_file=False yalnızca process environment ile yükler.
    """
    selected: Path | None
    if env_file is not None:
        if not env_file.is_file():
            raise ConfigurationError([f"--env-file bulunamadı: {env_file}"])
        selected = env_file
    elif use_default_env_file and Path(".env").is_file():
        selected = Path(".env")
    else:
        selected = None
    try:
        return Settings(_env_file=selected)
    except ValidationError as exc:
        raise ConfigurationError.from_validation_error(exc) from None
