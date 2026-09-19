from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase project. Only SUPABASE_URL and the database password are needed to reach the database:
    # the backend builds the connection itself (see app/db.py). DATABASE_URL is an optional full override.
    supabase_db_password: Optional[str] = None
    supabase_region: Optional[str] = None  # e.g. ap-south-1; only needed if the direct host is unreachable (IPv4-only networks)
    database_url: Optional[str] = None

    # Supabase Auth. Provide EITHER the legacy HS256 JWT secret OR just the project URL
    # (asymmetric projects are verified through the project's JWKS endpoint).
    supabase_url: Optional[str] = None
    supabase_jwt_secret: Optional[str] = None
    supabase_jwt_audience: str = "authenticated"

    cors_origins: str = "http://localhost:3000"

    # Behaviour
    app_timezone: str = "Asia/Kolkata"
    demo_mode: bool = True  # enables the Demo Bank Simulator endpoints

    # AI agent (LangGraph + configurable LLM provider)
    llm_provider: str = "gemini"  # gemini | openai | anthropic
    llm_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.6-flash"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Account Aggregator sandbox (Setu). Leave blank to keep the adapter inactive.
    setu_client_id: Optional[str] = None
    setu_client_secret: Optional[str] = None
    setu_product_instance_id: Optional[str] = None
    setu_base_url: str = "https://fiu-sandbox.setu.co"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
