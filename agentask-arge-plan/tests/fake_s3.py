"""YALNIZ TEST: bellek içi S3 uyumlu sahte depo (httpx MockTransport). Gerçek S3 yerine geçmiş gibi sunulmaz.

Her isteğin SigV4 imzasını, içerik özetini ve tarih başlığını doğrular; imza/özet tutmazsa 403/400 döner.
ListObjectsV2 küçük sayfalarla (max_keys) sayfalamayı zorlar. Hata enjeksiyonu: fail_next."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx

from agentask.infrastructure.artifacts.s3 import sign_v4

_AUTH = re.compile(
    r"Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, SignedHeaders=([^,]+), Signature=(\w+)"
)


class FakeS3:
    def __init__(self, bucket: str, access: str, secret: str, region: str, page_size: int = 2) -> None:
        self.bucket, self.access, self.secret, self.region = bucket, access, secret, region
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.page_size = page_size
        self.fail_next: int | None = None  # bir sonraki isteğe dönülecek HTTP durumu
        self.requests: list[tuple[str, str]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _verify(self, request: httpx.Request) -> bool:
        match = _AUTH.fullmatch(request.headers.get("authorization", "").removeprefix("AWS4-HMAC-SHA256 "))
        if match is None or match.group(1) != self.access or match.group(3) != self.region:
            return False
        body = request.content
        if request.headers.get("x-amz-content-sha256") != hashlib.sha256(body).hexdigest():
            return False
        names = match.group(4).split(";")
        headers = {n: request.headers[n] for n in names if n != "host"}
        parts = urlsplit(str(request.url))
        expected = sign_v4(
            method=request.method,
            host=request.headers["host"],
            path=unquote(parts.path),
            query=dict(parse_qsl(parts.query, keep_blank_values=True)),
            headers=headers,
            payload_sha256=request.headers["x-amz-content-sha256"],
            amz_date=request.headers["x-amz-date"],
            region=self.region,
            access_key=self.access,
            secret_key=self.secret,
        )
        return expected.endswith(f"Signature={match.group(5)}")

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = unquote(urlsplit(str(request.url)).path)
        self.requests.append((request.method, path))
        if self.fail_next is not None:
            status, self.fail_next = self.fail_next, None
            return httpx.Response(status)
        if not self._verify(request):
            return httpx.Response(403, text="<Error><Code>SignatureDoesNotMatch</Code></Error>")
        if not path.startswith(f"/{self.bucket}"):
            return httpx.Response(404)
        key = path.removeprefix(f"/{self.bucket}").lstrip("/")
        if request.method == "PUT":
            self.objects[key] = (request.content, request.headers.get("content-type", ""))
            return httpx.Response(200)
        if request.method == "GET" and key:
            found = self.objects.get(key)
            return httpx.Response(200, content=found[0]) if found else httpx.Response(404)
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        if request.method == "GET":
            query = dict(parse_qsl(urlsplit(str(request.url)).query, keep_blank_values=True))
            names = sorted(k for k in self.objects if k.startswith(query.get("prefix", "")))
            start = int(query.get("continuation-token", "0"))
            page = names[start : start + self.page_size]
            more = start + self.page_size < len(names)
            items = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in page)
            token = f"<NextContinuationToken>{start + self.page_size}</NextContinuationToken>" if more else ""
            xml = (
                '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                f"{items}<IsTruncated>{'true' if more else 'false'}</IsTruncated>{token}</ListBucketResult>"
            )
            return httpx.Response(200, content=xml.encode())
        return httpx.Response(405)
