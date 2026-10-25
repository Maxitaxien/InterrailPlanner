"""One bounded query to an admin-configured SearXNG. No arbitrary page fetching."""
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

import httpx
from app.core.config import get_settings


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def plain(value, limit):
    parser = PlainText()
    parser.feed(str(value)[:8000])
    return ' '.join(unescape(' '.join(parser.parts)).split())[:limit]


def public_link(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
            return None
        if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host) or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid')):
            return None
        if re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*', host):
            return None  # Browsers also accept abbreviated/hex IPv4 spellings.
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        return urlunsplit(('https', host, parts.path, parts.query, ''))[:2000] if len(value) <= 2000 else None
    except (TypeError, ValueError):
        return None


def normalized_text(value):
    value = unicodedata.normalize('NFKD', value).casefold()
    value = ''.join(char for char in value if not unicodedata.combining(char))
    value = value.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '–': '-', '—': '-'}))
    return ' '.join(value.split())


PRIVATE_TEXT = re.compile(
    r'https?://\S+|\b[\w.+-]+@[\w.-]+\.\w+\b|'
    r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|'
    r'\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|'
    r'(?<!\w)\+?\d[\d ().-]{5,}\d(?!\w)|\b[\w-]{32,}\b', re.IGNORECASE)


def public_question(value):
    """Basic redaction before local planning, not a complete PII detector."""
    return PRIVATE_TEXT.sub('[private detail removed]', plain(value, 600))


def validated_query(query, city, allowed_years=()):
    """Natural-language search only: one short, city-anchored query, no URLs/tools."""
    query = ' '.join(query.split())
    if not 3 <= len(query) <= 180 or len(query.split()) > 24:
        raise ValueError('Search query must be concise')
    numbers = re.findall(r'(?<!\w)\d+(?!\w)', query)
    if (not re.fullmatch(r"[\w\s’'&(),.?-]+", query) or PRIVATE_TEXT.search(query)
            or any(number not in {str(year) for year in allowed_years} for number in numbers)
            or re.search(r'\b[\w-]+(?:\.[\w-]+)+\b', query)):
        raise ValueError('Search query contains private details or unsupported syntax')
    words = re.sub(r'[^\w]+', ' ', normalized_text(query)).strip()
    city_words = re.sub(r'[^\w]+', ' ', normalized_text(city.name)).strip()
    if f' {city_words} ' not in f' {words} ':
        raise ValueError('Search query must include the selected city')
    return query


class CitySearch:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport

    async def search(self, db, city, query=None, allowed_years=()):
        settings = self.settings
        if not settings.searxng_base_url:
            return {'status': 'not_configured', 'sources': [], 'cached': False}
        query = validated_query(query or f'things to do in {city.name}', city, allowed_years)
        now = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=settings.ai_web_timeout_seconds, follow_redirects=False, transport=self.transport) as client:
                async with client.stream('GET', settings.searxng_base_url.rstrip('/') + '/search', params={
                    'q': query, 'format': 'json', 'language': 'en', 'safesearch': 1,
                    'categories': 'general', 'pageno': 1,
                }) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 512_000:
                            raise ValueError('Oversized search response')
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
                raise ValueError('Invalid search response')
            sources, seen = [], set()
            for item in payload['results'][:40]:
                if not isinstance(item, dict): continue
                url = public_link(item.get('url', ''))
                if not url or url in seen: continue
                title, excerpt = plain(item.get('title', ''), 160), plain(item.get('content', ''), 400)
                if not title or not excerpt: continue
                seen.add(url)
                sources.append({'id': f'w{len(sources)+1}', 'title': title, 'url': url,
                                'excerpt': excerpt, 'retrieved_at': now.isoformat(), 'kind': 'search_excerpt'})
                if len(sources) == 6: break
            result = {'status': 'searched' if sources else 'empty', 'sources': sources,
                      'query': query,
                      'queried_at': now.isoformat(), 'cached': False, 'provider': 'self-hosted-searxng'}
            return result
        except (httpx.HTTPError, ValueError, TypeError):
            return {'status': 'unavailable', 'sources': [], 'cached': False}
