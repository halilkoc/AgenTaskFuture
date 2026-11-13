"""AUTH_MODE=local_admin: .env ile yapılandırılan GEÇİCİ tek admin girişi. Kurumsal SSO değildir.

Oturum belirteci rastgeledir ve yalnız özeti bellekte tutulur (tek worker); uygulama yeniden başlayınca
oturum düşer. Durum değiştiren her istek, oturuma bağlı CSRF belirteci ister. Parola, hash, cookie ve
belirteç loglanmaz.
Hata halinde başka kimlik kaynağına düşülmez.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie

from agentask.application.errors import Forbidden, LoginFailed, LoginLocked, Unauthenticated
from agentask.application.observability import log_event
from agentask.application.ports.identity import IdentityRequest
from agentask.domain.identity import Principal, Role
from agentask.domain.passwords import hash_password, verify_password

logger = logging.getLogger(__name__)
COOKIE_NAME = "agentask_admin_session"
CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_MAX_SESSIONS = 20
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))  # bilinmeyen kullanıcıda aynı işi yapmak için


@dataclass(slots=True)
class _Session:
    user: str
    csrf: str
    expires_at: float


@dataclass(slots=True)
class _Failures:
    count: int = 0
    locked_until: float = 0.0


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cookie_token(header: str | None) -> str | None:
    if not header:
        return None
    try:
        morsel = SimpleCookie(header).get(COOKIE_NAME)
    except CookieError:
        return None
    return morsel.value if morsel is not None else None


class LocalAdminIdentity:
    source = "local_admin"

    def __init__(
        self,
        username: str,
        password_hash: str,
        session_ttl_seconds: int,
        max_attempts: int,
        lockout_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._username = username
        self._hash = password_hash
        self._ttl = session_ttl_seconds
        self._max_attempts = max_attempts
        self._lockout = lockout_seconds
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._failures: dict[str, _Failures] = {}

    @property
    def session_ttl_seconds(self) -> int:
        return self._ttl

    def _active(self, token: str | None) -> tuple[str, _Session] | None:
        if not token:
            return None
        key = _digest(token)
        session = self._sessions.get(key)
        if session is None:
            return None
        if session.expires_at <= self._clock():
            del self._sessions[key]
            return None
        return key, session

    async def authenticate(self, request: IdentityRequest) -> Principal:
        found = self._active(_cookie_token(request.headers.get("cookie")))
        if found is None:
            raise Unauthenticated("Oturum açmanız gerekiyor.")
        session = found[1]
        if request.method.upper() not in _SAFE_METHODS and not hmac.compare_digest(
            request.headers.get(CSRF_HEADER, ""), session.csrf
        ):
            raise Forbidden("İstek doğrulanamadı; sayfayı yenileyip yeniden deneyin.")
        return Principal(
            user_id=session.user,
            display_name=session.user,
            roles=frozenset(Role),
            identity_source=self.source,
        )

    def csrf_for(self, cookie_header: str | None) -> str:
        found = self._active(_cookie_token(cookie_header))
        return found[1].csrf if found else ""

    async def login(self, username: str, password: str, client: str | None) -> str:
        """Başarılıysa oturum belirteci döner. Deneme sayacı hash'ten ÖNCE artar (eşzamanlı deneme aşamaz)."""
        key = client or "unknown"
        failures = self._failures.setdefault(key, _Failures())
        now = self._clock()
        if failures.locked_until > now:
            log_event(
                logger,
                "auth_login",
                level=logging.WARNING,
                audit=True,
                outcome="locked",
                error_code="login_locked",
            )
            raise LoginLocked()
        if failures.locked_until:
            failures.count, failures.locked_until = 0, 0.0
        failures.count += 1
        known = hmac.compare_digest(username.strip().lower().encode(), self._username.encode())
        verified = await asyncio.to_thread(verify_password, password, self._hash if known else _DUMMY_HASH)
        if not (known and verified):
            if failures.count >= self._max_attempts:
                failures.locked_until = now + self._lockout
            # Denenen kullanıcı adı yazılmaz: yanlışlıkla parola girilmiş olabilir.
            log_event(
                logger,
                "auth_login",
                level=logging.WARNING,
                audit=True,
                outcome="failed",
                error_code="login_failed",
            )
            raise LoginFailed()
        self._failures.pop(key, None)
        expired = [k for k, s in self._sessions.items() if s.expires_at <= now]
        for item in expired:
            del self._sessions[item]
        while len(self._sessions) >= _MAX_SESSIONS:
            del self._sessions[next(iter(self._sessions))]
        token = secrets.token_urlsafe(32)
        self._sessions[_digest(token)] = _Session(self._username, secrets.token_urlsafe(32), now + self._ttl)
        log_event(logger, "auth_login", audit=True, outcome="success", actor=self._username)
        return token

    def logout(self, cookie_header: str | None) -> None:
        found = self._active(_cookie_token(cookie_header))
        if found is not None:
            del self._sessions[found[0]]
            log_event(logger, "auth_logout", audit=True, outcome="success", actor=found[1].user)
