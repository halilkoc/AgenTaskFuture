"""Error envelope: code, safe_message, correlation_id, retryable, details (redakte)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from agentask.application.errors import (
    ApplicationError,
    ApplicationNotConfigured,
    CandidateStale,
    ContentConflict,
    DependencyUnavailable,
    DraftConflict,
    DraftNotFound,
    DraftNotReady,
    EffectNotAcknowledged,
    Forbidden,
    IdempotencyConflict,
    InterruptionChanged,
    LoginFailed,
    LoginLocked,
    MigrationRequired,
    NavigationNotAllowed,
    PlanInvalid,
    PublishConflict,
    ReleaseSuperseded,
    RunNotFound,
    RunNotResumable,
    ScreenNotRecognized,
    ServiceShuttingDown,
    SessionApplicationMismatch,
    SessionBusy,
    SessionLimitReached,
    SessionNotFound,
    StaleApproval,
    TargetNotUnique,
    Unauthenticated,
)
from agentask.application.observability import SOFTWARE, log_event
from agentask.application.services.artifacts import ArtifactMissing, ArtifactNotFound, ArtifactRejected
from agentask.domain.catalog import IllegalStepTransition, StepNotFound
from agentask.domain.runtime import IllegalTransition

logger = logging.getLogger(__name__)

_STATUS: dict[type[ApplicationError], int] = {
    Unauthenticated: 401,
    LoginFailed: 401,
    LoginLocked: 429,
    Forbidden: 403,
    DependencyUnavailable: 503,
    SessionNotFound: 404,
    SessionBusy: 409,
    SessionLimitReached: 429,
    NavigationNotAllowed: 403,
    ServiceShuttingDown: 503,
    CandidateStale: 409,
    PlanInvalid: 422,
    ApplicationNotConfigured: 422,
    ArtifactRejected: 422,
    ArtifactNotFound: 404,
    ArtifactMissing: 503,
    SessionApplicationMismatch: 409,
    InterruptionChanged: 409,
    IdempotencyConflict: 409,
    RunNotFound: 404,
    RunNotResumable: 409,
    DraftNotFound: 404,
    DraftConflict: 409,
    TargetNotUnique: 409,
    EffectNotAcknowledged: 403,
    DraftNotReady: 409,
    ContentConflict: 409,
    StaleApproval: 409,
    PublishConflict: 409,
    ReleaseSuperseded: 409,
    MigrationRequired: 409,
    ScreenNotRecognized: 409,
}


def status_for(exc: ApplicationError) -> int:
    return next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)


class ErrorEnvelope(BaseModel):
    code: str
    safe_message: str
    correlation_id: str
    retryable: bool
    details: dict[str, object] = Field(default_factory=dict)


_SLUG_PATTERN = r"^[a-z][a-z0-9_]{0,60}$"


def _reason_tr(err: dict[str, Any]) -> str:
    """Pydantic hata türünden Türkçe neden. Girdi değeri ASLA kullanılmaz (secret olabilir); yalnız şema
    bilgisi (sınırlar, desen, izinli değerler) ve kodda yazılmış doğrulayıcı mesajları kullanılır."""
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    if kind == "missing":
        return "zorunlu alan boş bırakılamaz"
    if kind == "string_too_short":
        return f"en az {ctx.get('min_length')} karakter olmalı"
    if kind == "string_too_long":
        return f"en fazla {ctx.get('max_length')} karakter olabilir"
    if kind == "string_pattern_mismatch":
        if ctx.get("pattern") == _SLUG_PATTERN:
            return "küçük harfle başlamalı; yalnız küçük harf, rakam ve _ içerebilir (en fazla 61 karakter)"
        return "biçimi uygun değil"
    if kind in {"int_parsing", "int_type", "int_from_float"}:
        return "tam sayı olmalı"
    if kind in {"greater_than_equal", "greater_than"}:
        return f"{ctx.get('ge', ctx.get('gt'))} veya daha büyük olmalı"
    if kind in {"less_than_equal", "less_than"}:
        return f"{ctx.get('le', ctx.get('lt'))} veya daha küçük olmalı"
    if kind in {"literal_error", "enum"}:
        return f"izin verilen değerlerden biri olmalı: {ctx.get('expected', '')}".strip()
    if kind == "extra_forbidden":
        return "tanınmayan alan"
    if kind == "too_short":
        return f"en az {ctx.get('min_length')} öğe gerekli"
    if kind == "too_long":
        return f"en fazla {ctx.get('max_length')} öğe olabilir"
    if kind in {"bool_parsing", "bool_type"}:
        return "evet/hayır değeri olmalı"
    if kind in {"string_type", "dict_type", "list_type", "model_type", "model_attributes_type"}:
        return "türü uygun değil"
    if kind == "value_error":
        return str(err.get("msg", "")).removeprefix("Value error, ") or "geçersiz değer"
    return "geçersiz değer"


def field_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for err in errors[:20]:
        loc = [str(p) for p in err.get("loc", ()) if p not in {"body", "query", "path"}]
        out.append(
            {"field": ".".join(loc) or "(genel)", "reason": err.get("type", ""), "message": _reason_tr(err)}
        )
    return out


def _summary(errors: list[dict[str, str]], default: str) -> str:
    if not errors:
        return default
    first = errors[0]
    more = f" (+{len(errors) - 1} hata daha)" if len(errors) > 1 else ""
    return f"{default.rstrip('.')}: {first['field']} — {first['message']}{more}"


def correlation_id_of(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unknown"))


def _respond(request: Request, status: int, envelope: ErrorEnvelope) -> JSONResponse:
    # Beklenen hata burada loglanmaz: tek kayıt, ara katmanın istek olayıdır (error_code bu bilgiyle yazılır).
    request.state.error_code = envelope.code
    return JSONResponse(status_code=status, content=envelope.model_dump())


def internal_error_response(request: Request) -> JSONResponse:
    """Beklenmeyen hata yanıtı; iç ayrıntı yanıta girmez. Loglama çağıranındır (tek kayıt)."""
    return _respond(
        request,
        500,
        ErrorEnvelope(
            code="internal_error",
            safe_message="Beklenmeyen bir hata oluştu.",
            correlation_id=correlation_id_of(request),
            retryable=False,
        ),
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def _application_error(request: Request, exc: ApplicationError) -> Response:
        if (
            isinstance(exc, Unauthenticated)
            and request.method == "GET"
            and not request.url.path.startswith("/api/")
            and request.app.state.container.admin_auth is not None
        ):
            return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)
        return _respond(
            request,
            status_for(exc),
            ErrorEnvelope(
                code=exc.code,
                safe_message=exc.safe_message,
                correlation_id=correlation_id_of(request),
                retryable=exc.retryable,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        raw: list[dict[str, Any]] = [dict(e) for e in exc.errors()]
        fields = [".".join(str(p) for p in err.get("loc", ())) for err in raw]
        errors = field_errors(raw)
        return _respond(
            request,
            422,
            ErrorEnvelope(
                code="invalid_request",
                safe_message=_summary(errors, "İstek doğrulanamadı."),
                correlation_id=correlation_id_of(request),
                retryable=False,
                details={"fields": fields, "errors": errors},
            ),
        )

    @app.exception_handler(ValidationError)
    async def _domain_validation(request: Request, exc: ValidationError) -> JSONResponse:
        # Girdi değerleri (secret olabilir) yanıtta yer almaz.
        raw: list[dict[str, Any]] = [dict(e) for e in exc.errors(include_input=False, include_url=False)]
        fields = [".".join(str(p) for p in e.get("loc", ())) for e in raw]
        errors = field_errors(raw)
        return _respond(
            request,
            422,
            ErrorEnvelope(
                code="invalid_request",
                safe_message=_summary(errors, "Girdi doğrulanamadı."),
                correlation_id=correlation_id_of(request),
                retryable=False,
                details={"fields": fields[:20], "errors": errors},
            ),
        )

    @app.exception_handler(IllegalStepTransition)
    @app.exception_handler(IllegalTransition)
    async def _illegal_state(request: Request, exc: Exception) -> JSONResponse:
        return _respond(
            request,
            409,
            ErrorEnvelope(
                code="invalid_state",
                safe_message="Bu işlem mevcut durumda yapılamaz.",
                correlation_id=correlation_id_of(request),
                retryable=False,
            ),
        )

    @app.exception_handler(StepNotFound)
    async def _step_missing(request: Request, exc: StepNotFound) -> JSONResponse:
        return _respond(
            request,
            404,
            ErrorEnvelope(
                code="step_not_found",
                safe_message="Adım bulunamadı.",
                correlation_id=correlation_id_of(request),
                retryable=False,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {404: "Kaynak bulunamadı.", 405: "Yöntem desteklenmiyor."}
        return _respond(
            request,
            exc.status_code,
            ErrorEnvelope(
                code=f"http_{exc.status_code}",
                safe_message=messages.get(exc.status_code, "İstek işlenemedi."),
                correlation_id=correlation_id_of(request),
                retryable=False,
            ),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Yalnız ara katmanın dışında oluşan hatalar buraya gelir; rota hataları ara katmanda bir kez yazılır.
        log_event(
            logger,
            "unhandled_error",
            level=logging.ERROR,
            exc_info=exc,
            correlation_id=correlation_id_of(request),
            error_code="internal_error",
            error_kind=SOFTWARE,
        )
        return internal_error_response(request)
