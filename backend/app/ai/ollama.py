import httpx
import re
from pydantic import BaseModel
from app.core.config import get_settings

class OllamaProvider:
    def __init__(self, model: str | None = None, transport=None):
        self.settings = get_settings()
        self.model = model or self.settings.llm_model
        self.transport = transport

    async def models(self):
        async with httpx.AsyncClient(base_url=self.settings.ollama_base_url, timeout=5, transport=self.transport) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", []) if not m.get('remote_host') and not m.get('remote_model') and 'cloud' not in m['name'].lower()]

    async def generate_structured(self, system_prompt, user_prompt, response_model):
        if not re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,100}', self.model) or 'cloud' in self.model.lower() or '://' in self.model:
            raise ValueError('Choose an installed local model, not a cloud model or URL')
        async with httpx.AsyncClient(base_url=self.settings.ollama_base_url, timeout=self.settings.llm_timeout_seconds, transport=self.transport) as client:
            metadata = await client.post('/api/show', json={'model': self.model})
            metadata.raise_for_status()
            details = metadata.json()
            if not isinstance(details, dict) or details.get('remote_host') or details.get('remote_model'):
                raise ValueError('Remote inference models are not permitted')
            response = await client.post("/api/chat", json={"model": self.model, "stream": False,
                "think": self.settings.llm_thinking,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "format": response_model.model_json_schema(), "options": {"temperature": .3, "num_ctx": self.settings.llm_num_ctx, "num_predict": self.settings.llm_num_predict}})
            response.raise_for_status()
            answer = response.json()
            if not isinstance(answer, dict) or answer.get('remote_host') or answer.get('remote_model') or len(response.content) > 2_000_000:
                raise ValueError('Unexpected remote or oversized model response')
            return response_model.model_validate_json(answer["message"]["content"])
