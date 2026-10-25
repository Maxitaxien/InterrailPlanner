import hashlib
import json
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from app.models.integrations import Attraction, AICache
from app.ai.ollama import OllamaProvider

PROMPT_VERSION = "curated-ranking-v1"
class Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attraction_id: str
    reason_tags: list[Literal["culture", "food", "beaches", "nature", "history", "relaxation", "mountains", "coast", "nightlife"]] = Field(max_length=4)
class Picks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choices: list[Pick] = Field(min_length=1, max_length=12)

def provider_for(model=None): return OllamaProvider(model)

async def recommend(db, itinerary, model=None):
    provider = provider_for(model)
    destination_ids = [s["destination_id"] for s in itinerary.result["stops"]]
    interests = itinerary.trip.request["preferences"]["interests"]
    attractions = db.scalars(select(Attraction).where(Attraction.destination_id.in_(destination_ids)).order_by(Attraction.id)).all()
    catalog = {a.id: a for a in attractions}
    context = {"interests": interests, "attractions": [{"id": a.id, "name": a.name, "destination_id": a.destination_id, "tags": a.interest_tags} for a in attractions], "schema": Picks.model_json_schema(), "prompt_version": PROMPT_VERSION, "model": provider.model}
    key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    cached = db.scalar(select(AICache).where(AICache.input_hash == key))
    if cached:
        return {**cached.output_json, "cached": True}
    picks, source = None, "deterministic"
    # Only curated IDs and validated category tags can leave the model boundary. No free-text transport facts.
    for _ in range(2):
        try:
            proposed = await provider.generate_structured("Rank curated attractions for the interests. Return only known attraction IDs with relevant tags from each attraction. Never invent attractions, transport, prices or rules.", json.dumps(context), Picks)
            ids = [p.attraction_id for p in proposed.choices]
            if len(ids) != len(set(ids)) or any(p.attraction_id not in catalog or not set(p.reason_tags) <= set(catalog[p.attraction_id].interest_tags) for p in proposed.choices):
                raise ValueError("Unrecognized recommendation ID or tags")
            picks, source = proposed.choices, "ollama"
            break
        except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
            continue
    if picks is None:
        ranked = sorted(attractions, key=lambda a: (-len(set(a.interest_tags) & set(interests)), a.id))[:12]
        picks = [Pick(attraction_id=a.id, reason_tags=[t for t in a.interest_tags if t in interests][:4]) for a in ranked]
    result = {"source": source, "model": provider.model if source == "ollama" else None, "cached": False,
        "prompt_version": PROMPT_VERSION, "cloud_used": False,
        "recommendations": [{"id": p.attraction_id, "destination_id": catalog[p.attraction_id].destination_id, "name": catalog[p.attraction_id].name,
            "description": catalog[p.attraction_id].description, "reason": "Matches your interest in " + ", ".join(p.reason_tags) if p.reason_tags else "A curated option for this stop.",
            "source": catalog[p.attraction_id].source} for p in picks],
        "warning": "Curated suggestions; verify opening times, access and tickets separately."}
    # Do not persist outage fallbacks: a restored Ollama should be tried on the next request.
    if source == "ollama":
        from sqlalchemy.exc import IntegrityError
        try:
            with db.begin_nested():
                db.add(AICache(input_hash=key, model_name=provider.model, prompt_version=PROMPT_VERSION, output_json=result))
                db.flush()
            db.commit()
        except IntegrityError:
            pass  # Another identical request already cached this result.
    return result
