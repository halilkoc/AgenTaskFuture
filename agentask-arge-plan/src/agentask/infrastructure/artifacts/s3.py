"""Kurum içi S3 uyumlu nesne deposu (ADR 0018). Dış SDK yok: AWS Signature V4 burada uygulanır, istekler
mevcut `httpx` ile yapılır.

- Yalnız dört işlem: PutObject, GetObject, DeleteObject, ListObjectsV2. Serbest URL/HTTP aracı değildir; uç
  nokta ve kova yalnız Settings'ten gelir, anahtarlar yalnız kod üretimli kimliklerdir (yol geçişi yok).
- PutObject atomiktir (nesne tamamı yazılınca görünür); içerik özeti `x-amz-content-sha256` ile imzaya girer.
- Kimlik bilgileri loglanmaz, hata mesajlarına konmaz. TLS doğrulaması kapatılamaz; kurum CA'sı S3_CA_BUNDLE.
- Gerçek kurum S3 bağlantısı bu ortamda doğrulanmadı (BLOCKED); sözleşme testleri sahte S3 ve AWS örnek imza
  vektörüyle yapılır.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import ssl
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

import httpx

from agentask.domain.artifacts import ARTIFACT_ID_PATTERN

logger = logging.getLogger(__name__)
_KEY = re.compile(ARTIFACT_ID_PATTERN)
_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
MAX_LIST_PAGES = 1000  # sonsuz sayfalama koruması
MAX_LIST_BYTES = 5_000_000


class ObjectStoreError(RuntimeError):
    """Depo isteği başarısız (ayrıntı güvenli; kimlik bilgisi içermez)."""


def _uri_encode(value: str, safe: str = "") -> str:
    return quote(value, safe="-_.~" + safe)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sign_v4(
    *,
    method: str,
    host: str,
    path: str,
    query: dict[str, str],
    headers: dict[str, str],
    payload_sha256: str,
    amz_date: str,
    region: str,
    access_key: str,
    secret_key: str,
    service: str = "s3",
) -> str:
    """Authorization başlığı (AWS SigV4). `headers` imzalanacak başlıklardır (host otomatik eklenir)."""
    signed = {k.lower(): " ".join(v.strip().split()) for k, v in headers.items()}
    signed["host"] = host
    names = sorted(signed)
    canonical_headers = "".join(f"{n}:{signed[n]}\n" for n in names)
    canonical_query = "&".join(f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted(query.items()))
    canonical_request = "\n".join(
        [
            method,
            _uri_encode(path, safe="/"),
            canonical_query,
            canonical_headers,
            ";".join(names),
            payload_sha256,
        ]
    )
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()]
    )
    key = _hmac(
        _hmac(_hmac(_hmac(("AWS4" + secret_key).encode("utf-8"), date), region), service), "aws4_request"
    )
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(names)}, "
        f"Signature={signature}"
    )


class S3ObjectStore:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        prefix: str = "",
        addressing: Literal["path", "virtual"] = "path",
        ca_bundle: Path | None = None,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        parts = urlsplit(endpoint)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("geçersiz S3 uç noktası")
        self._scheme, self._bucket, self._region = parts.scheme, bucket, region
        self._prefix, self._addressing = prefix, addressing
        netloc = parts.netloc
        self._host = f"{bucket}.{netloc}" if addressing == "virtual" else netloc
        self._base = parts.path.rstrip("/")
        self._access, self._secret = access_key, secret_key
        self._clock = clock
        verify: ssl.SSLContext | bool = True
        if ca_bundle is not None:
            verify = ssl.create_default_context(cafile=str(ca_bundle))
        self._client = httpx.AsyncClient(
            timeout=timeout_s, verify=verify, transport=transport, follow_redirects=False
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _object_path(self, key: str = "") -> str:
        bucket = "" if self._addressing == "virtual" else f"/{self._bucket}"
        return (
            f"{self._base}{bucket}/{key}" if key or self._addressing == "virtual" else f"{self._base}{bucket}"
        )

    def _key(self, key: str) -> str:
        if not _KEY.fullmatch(key):
            raise ValueError("geçersiz nesne anahtarı")
        return f"{self._prefix}{key}"

    async def _send(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: bytes = b"",
        extra: dict[str, str] | None = None,
    ) -> httpx.Response:
        query = query or {}
        payload = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
        amz_date = self._clock().strftime("%Y%m%dT%H%M%SZ")
        headers = {"x-amz-content-sha256": payload, "x-amz-date": amz_date, **(extra or {})}
        headers["Authorization"] = sign_v4(
            method=method,
            host=self._host,
            path=path,
            query=query,
            headers=headers,
            payload_sha256=payload,
            amz_date=amz_date,
            region=self._region,
            access_key=self._access,
            secret_key=self._secret,
        )
        url = httpx.URL(scheme=self._scheme, host=self._host.split(":")[0], path=path, params=query)
        if ":" in self._host:
            url = url.copy_with(port=int(self._host.rsplit(":", 1)[1]))
        try:
            return await self._client.request(method, url, content=body or None, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("s3_request_failed op=%s type=%s", method, type(exc).__name__)
            raise ObjectStoreError(f"S3 isteği tamamlanamadı ({type(exc).__name__}).") from None

    @staticmethod
    def _fail(op: str, response: httpx.Response) -> ObjectStoreError:
        logger.warning("s3_error op=%s status=%s", op, response.status_code)
        return ObjectStoreError(f"S3 {op} başarısız (HTTP {response.status_code}).")

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        response = await self._send(
            "PUT", self._object_path(self._key(key)), body=data, extra={"content-type": content_type}
        )
        if response.status_code != 200:
            raise self._fail("put", response)

    async def get(self, key: str) -> bytes | None:
        response = await self._send("GET", self._object_path(self._key(key)))
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise self._fail("get", response)
        return response.content

    async def delete(self, key: str) -> None:
        response = await self._send("DELETE", self._object_path(self._key(key)))
        if response.status_code not in {200, 204, 404}:
            raise self._fail("delete", response)

    async def list_keys(self) -> list[str]:
        keys: list[str] = []
        token: str | None = None
        for _ in range(MAX_LIST_PAGES):
            query = {"list-type": "2", "prefix": self._prefix}
            if token:
                query["continuation-token"] = token
            response = await self._send("GET", self._object_path(), query=query)
            if response.status_code != 200 or len(response.content) > MAX_LIST_BYTES:
                raise self._fail("list", response)
            root = ElementTree.fromstring(response.content)  # noqa: S314 - kurum içi, boyut sınırlı yanıt
            for item in root.iter(f"{_NS}Contents"):
                name = (item.findtext(f"{_NS}Key") or "").removeprefix(self._prefix)
                if _KEY.fullmatch(name):
                    keys.append(name)
            if (root.findtext(f"{_NS}IsTruncated") or "false") != "true":
                return sorted(keys)
            token = root.findtext(f"{_NS}NextContinuationToken")
            if not token:
                raise ObjectStoreError("S3 listesi devam belirteci olmadan kesildi.")
        raise ObjectStoreError("S3 listesi sayfa sınırını aştı.")
