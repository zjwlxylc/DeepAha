"""No network access on submission. Dispatch DNS check is defense-in-depth only."""
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SENSITIVE = {'token','access_token','auth','authorization','password','passwd','secret',
             'cookie','session','sessionid','session_id','api_key','apikey','signature','sig','key'}
LOCAL_SUFFIXES = ('.local','.localhost','.internal','.lan','.home','.test','.invalid','.onion')


def canonicalize(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError('请填写不超过2048字符的公开网址')
    if value != value.strip() or any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value:
        raise ValueError('网址含有空白、控制字符或反斜线')
    try:
        p = urlsplit(value)
        if p.scheme.lower() not in ('http','https') or not p.hostname or p.username is not None or p.password is not None:
            raise ValueError()
        if p.port not in (None, 80 if p.scheme.lower()=='http' else 443):
            raise ValueError()
        raw = p.hostname.rstrip('.')
        if '%' in raw or ':' in raw:
            raise ValueError()
        host = raw.encode('idna').decode('ascii').lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
        if '.' not in host or host.endswith(LOCAL_SUFFIXES) or len(host)>253:
            raise ValueError()
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}',host):
            raise ValueError()
        pairs = parse_qsl(p.query, keep_blank_values=True, max_num_fields=40)
        if any(k.casefold() in SENSITIVE for k,_ in pairs):
            raise ValueError()
        pairs = [(k,v) for k,v in pairs if not k.casefold().startswith('utm_') and k.casefold() not in ('gclid','fbclid')]
        # Preserve meaningful query order: some websites treat it as significant.
        return urlunsplit((p.scheme.lower(),host,p.path or '/',urlencode(pairs),''))
    except (ValueError, UnicodeError):
        raise ValueError('仅支持标准端口的公开网站域名；不能提交内网、IP、登录凭据或带令牌的网址') from None


def validate_public_dns(value: str, resolver=None) -> list[str]:
    """Does not fetch a URL. The actual collector must enforce redirects and egress."""
    host = urlsplit(canonicalize(value)).hostname
    try:
        records = resolver(host) if resolver else [r[4][0] for r in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)]
        addresses = sorted(set(records))
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise ValueError()
        return addresses
    except (OSError,ValueError):
        raise ValueError('域名无法安全解析到公网；未启动采集') from None
