"""Scope checks and short-lived, target-bound confirmation tokens."""
from __future__ import annotations
import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from .contract import canonical_json, parse_json, text
from .errors import ImporterError


@dataclass(frozen=True)
class Principal:
    subject: str
    producer: str
    scopes: frozenset[str]

    def __post_init__(self):
        text(self.subject, 'authenticated subject', 200)
        text(self.producer, 'producer namespace', 200)

    def require(self, scope: str):
        if scope not in self.scopes:
            raise ImporterError('FORBIDDEN', '当前身份没有此操作权限。', 403)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def unb64(value: str) -> bytes:
    if not isinstance(value, str): raise ValueError('not a string')
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


class TokenSigner:
    def __init__(self, secret: bytes, ttl_seconds: int = 600, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ImporterError('WEAK_SIGNING_KEY', '服务端确认签名密钥至少需要 32 字节。', 500)
        if not 10 <= ttl_seconds <= 3600: raise ValueError('TTL outside supported range')
        self._secret, self.ttl, self.clock = secret, ttl_seconds, clock

    def sign(self, claims: dict) -> str:
        now = int(self.clock())
        payload = dict(claims, issued_at=now, expires_at=now + self.ttl)
        encoded = b64(canonical_json(payload))
        mac = hmac.new(self._secret, encoded.encode('ascii'), hashlib.sha256).digest()
        return encoded + '.' + b64(mac)

    def verify(self, token: str) -> dict:
        try:
            if not isinstance(token, str) or len(token) > 16384: raise ValueError
            payload, signature = token.split('.')
            expected = hmac.new(self._secret, payload.encode('ascii'), hashlib.sha256).digest()
            if not hmac.compare_digest(unb64(signature), expected): raise ValueError
            claims = parse_json(unb64(payload), 12000)
            now = int(self.clock())
            if not isinstance(claims, dict) or type(claims.get('expires_at')) is not int or type(claims.get('issued_at')) is not int:
                raise ValueError
            if claims['issued_at'] > now + 30 or claims['expires_at'] <= now:
                raise ImporterError('PREVIEW_EXPIRED', '预览已过期，请重新预览后确认。', 409)
            return claims
        except ImporterError:
            raise
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ImporterError('INVALID_CONFIRMATION_TOKEN', '确认令牌无效，请重新预览。', 403) from exc
