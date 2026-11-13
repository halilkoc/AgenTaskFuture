"""Error envelope: code, safe_message, correlation_id, retryable, details (redakte)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from agentask.application.errors import (
    ApplicationError,
    CandidateStale,
    ContentConflict,
    DependencyUnavailable,
    DraftConflict,
    DraftNotFound,
    DraftNotReady,
    EffectNotAcknowledged,
    Forbidden,
    IdempotencyConflict,
    NavigationNotAllowed,
    PlanInvalid,
    PublishConflict,
    ReleaseSuperseded,
    RunNotFound,
    RunNotResumable,
    ServiceShuttingDown,
    SessionBusy,
    SessionLimitReached,
    SessionNotFound,
    StaleApproval,
    TargetNotUnique,
    Unauthenticated,
)
from agentask.domain.catalog import IllegalStepTransition, StepNotFound
from agentask.domain.runtime import IllegalTransition

logger = logging.getLogger(__name__)

_STATUS: dict[type[ApplicationError], int] = {
    Unauthenticated: 401,
    Forbidden: 403,
    DependencyUnavailable: 503,
    SessionNotFound: 404,
    SessionBusy: 409,
    SessionLimitReached: 429,
    NavigationNotAllowed: 403,
    ServiceShuttingDown: 503,
    CandidateStale: 409,
    PlanInvalid: 422,
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
}


def status_for(exc: ApplicationError) -> int:
    return next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)


class ErrorEnvelope(BaseModel):
    code: str
    safe_message: str
    correlation_id: str
    retryable: bool
    details: dict[str, object] = Field(default_factory=dict)


def correlation_id_of(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unknown"))


def _respond(request: Request, status: int, envelope: ErrorEnvelope) -> JSONResponse:
    return JSONResponse(status_code=status, content=envelope.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def _application_error(request: Request, exc: ApplicationError) -> JSONResponse:
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
        fields = [".".join(str(p) for p in err.get("loc", ())) for err in exc.errors()]
        return _respond(
            request,
            422,
            ErrorEnvelope(
                code="invalid_request",
                safe_message="İstek doğrulanamadı.",
                correlation_id=correlation_id_of(request),
                retryable=False,
                details={"fields": fields},
            ),
        )

    @app.exception_handler(ValidationError)
    async def _domain_validation(request: Request, exc: ValidationError) -> JSONResponse:
        # Girdi değerleri (secret olabilir) yanıtta yer almaz.
        fields = [".".join(str(p) for p in e["loc"]) for e in exc.errors(include_input=False)]
        return _respond(
            request,
            422,
            ErrorEnvelope(
                code="invalid_request",
                safe_message="Girdi doğrulanamadı.",
                correlation_id=correlation_id_of(request),
                retryable=False,
                details={"fields": fields[:20]},
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
        logger.error(
            "unhandled_error type=%s",
            type(exc).__name__,
            extra={"correlation_id": correlation_id_of(request)},
        )
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
