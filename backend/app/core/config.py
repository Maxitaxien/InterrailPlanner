from functools import lru_cache
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ScoreWeights(BaseModel):
    interest_match: float = Field(default=.30, ge=0, le=1)
    travel_efficiency: float = Field(default=.25, ge=0, le=1)
    pace: float = Field(default=.20, ge=0, le=1)
    diversity: float = Field(default=.15, ge=0, le=1)
    endpoint_quality: float = Field(default=.10, ge=0, le=1)

    @model_validator(mode="after")
    def normalized(self):
        if abs(sum(self.model_dump().values()) - 1) > .000001:
            raise ValueError("Route score weights must sum to 1")
        return self

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://interrail@localhost:5432/interrail"
    ollama_base_url: str = "http://ollama:11434"
    llm_model: str = "qwen3:14b"
    llm_timeout_seconds: int = 90
    llm_fallback_enabled: bool = False
    llm_num_ctx: int = Field(default=8192, ge=2048, le=32768)
    llm_num_predict: int = Field(default=2048, ge=256, le=8192)
    llm_thinking: bool = False
    searxng_base_url: str | None = None
    ai_web_timeout_seconds: float = Field(default=15, gt=0, le=45)
    motis_base_url: str | None = None
    motis_timeout_seconds: float = Field(default=30, gt=0, le=120)
    motis_feed_status_path: str | None = None
    allaboard_enabled: bool = False
    allaboard_api_key: SecretStr | None = None
    allaboard_environment: str = Field(default="test", pattern=r"^(test|live)$")
    allaboard_timeout_seconds: float = Field(default=30, gt=0, le=60)
    route_score_weights: ScoreWeights = Field(default_factory=ScoreWeights)

@lru_cache
def get_settings() -> Settings:
    return Settings()
