from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import httpx2

USER_AGENT = "DeepAha/0.2 (+https://github.com/zjwlxylc/DeepAha)"
MAX_RESPONSE_BYTES = 25_000_000


class NetworkTransportTimeout(RuntimeError):
    """A bounded HTTP attempt exceeded its configured timeout."""


class NetworkTransportError(RuntimeError):
    """A bounded HTTP attempt failed before a response was available."""


class ResponseTooLarge(RuntimeError):
    """A streaming response exceeded the raw-evidence size limit."""


@dataclass(frozen=True, slots=True)
class HttpRequest:
    url: str
    headers: Mapping[str, str]
    timeout_seconds: int
    max_bytes: int = MAX_RESPONSE_BYTES


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    url: str
    media_type: str | None
    etag: str | None
    last_modified: str | None
    location: str | None
    body: bytes


class HttpTransport(Protocol):
    def get_once(self, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError


class HostResolver(Protocol):
    def resolve(self, host: str) -> tuple[str, ...]:
        raise NotImplementedError


class HttpxTransport:
    def get_once(self, request: HttpRequest) -> HttpResponse:
        headers = {"User-Agent": USER_AGENT, **request.headers}
        try:
            with (
                httpx2.Client(
                    follow_redirects=False,
                    trust_env=False,
                    timeout=request.timeout_seconds,
                ) as client,
                client.stream("GET", request.url, headers=headers) as response,
            ):
                declared_length = response.headers.get("Content-Length")
                if declared_length is not None:
                    try:
                        if int(declared_length) > request.max_bytes:
                            raise ResponseTooLarge
                    except ValueError:
                        pass

                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > request.max_bytes:
                        raise ResponseTooLarge
                    content.extend(chunk)

                return HttpResponse(
                    status_code=response.status_code,
                    url=str(response.url),
                    media_type=response.headers.get("Content-Type"),
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    location=response.headers.get("Location"),
                    body=bytes(content),
                )
        except ResponseTooLarge:
            raise
        except httpx2.TimeoutException as error:
            raise NetworkTransportTimeout from error
        except httpx2.TransportError as error:
            raise NetworkTransportError from error


__all__ = [
    "HostResolver",
    "HttpRequest",
    "HttpResponse",
    "HttpTransport",
    "HttpxTransport",
    "NetworkTransportError",
    "NetworkTransportTimeout",
    "ResponseTooLarge",
]
