from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select
from app.models.integrations import TravelRulesCache, ExternalRequest

SOURCES = {"reservations": "https://www.interrail.com/en/plan-your-trip/reservations",
    "countries": "https://www.interrail.com/en/plan-your-trip/tips-and-tricks/trains-europe/trains-country"}
class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden = 0; self.parts = []; self.started = False
    def handle_starttag(self, tag, attrs):
        if tag == "h1": self.started = True
        if tag == "footer": self.started = False
        if tag in {"script", "style", "noscript"}: self.hidden += 1
    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}: self.hidden = max(0, self.hidden-1)
    def handle_data(self, data):
        if self.started and not self.hidden and data.strip(): self.parts.append(data.strip())

def utc(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

class OfficialRailRules:
    def __init__(self, transport=None): self.transport = transport
    async def lookup(self, topic):
        # Fixed, reviewed source URLs only; callers cannot supply URLs or redirect destinations.
        url = SOURCES[topic]
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, transport=self.transport) as client:
            async with client.stream("GET", url, headers={"User-Agent": "InterrailHelper/0.1 local-planning"}) as response:
                response.raise_for_status()
                if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
                    raise ValueError("Source not available as HTML")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000: raise ValueError("Source too large")
        parser = VisibleText(); parser.feed(raw.decode("utf-8", errors="replace"))
        excerpt = " ".join(parser.parts)[:1000]
        if not excerpt: raise ValueError("No readable source content")
        return {"verification_status": "needs_verification", "source_url": url, "topic": topic,
            "source_excerpt": excerpt, "notice": "Source text retrieved on request. It has not been interpreted as a rule or confirmation of pass validity."}

async def rail_rules(db, topic, provider=None):
    now = datetime.now(timezone.utc)
    cached = db.scalar(select(TravelRulesCache).where(TravelRulesCache.lookup_key == topic))
    if cached and utc(cached.expires_at) > now:
        return {**cached.content_json, "cached": True, "retrieved_at": utc(cached.retrieved_at).isoformat(), "expires_at": utc(cached.expires_at).isoformat()}
    try:
        content = await (provider or OfficialRailRules()).lookup(topic)
        expires = now + timedelta(hours=24)
        if cached:
            cached.content_json, cached.retrieved_at, cached.expires_at = content, now, expires
        else:
            db.add(TravelRulesCache(lookup_key=topic, source_url=SOURCES[topic], content_json=content, retrieved_at=now, expires_at=expires, source_version="official-html-v1"))
        db.add(ExternalRequest(provider="interrail.com", request_type="rail-rules", status="ok"))
        from sqlalchemy.exc import IntegrityError
        try: db.commit()
        except IntegrityError: db.rollback()  # Concurrent equivalent lookup can win the cache insert.
        return {**content, "cached": False, "retrieved_at": now.isoformat(), "expires_at": expires.isoformat()}
    except (httpx.HTTPError, ValueError):
        db.add(ExternalRequest(provider="interrail.com", request_type="rail-rules", status="unavailable", error_code="PROVIDER_UNAVAILABLE"))
        db.commit()
        return {"verification_status": "unknown", "topic": topic, "source_url": SOURCES[topic], "cached": False,
            "retrieved_at": None, "expires_at": None, "source_excerpt": None,
            "notice": "The source could not be retrieved. Open the official source and verify manually. Expired cache content is not presented as current."}
