"""Configuration settings for ops-api."""
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ops API settings loaded from environment."""
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # Server
    port: int = 8100
    
    # Database
    database_url: str = "sqlite:///./data/resolvix.db"
    
    # Security
    service_key: str = Field(..., description="X-Service-Key for runtime auth")
    session_secret: str = Field(..., min_length=32, description="Session cookie signing secret")
    seed_password: str = "DemoPassword123!"
    
    # URLs
    ops_public_url: str = "http://localhost:8100"
    cors_origins: str = "http://localhost:5173"
    
    # Runtime integration
    runtime_mode: str = "mock"  # mock | real
    runtime_url: str = "http://localhost:8000"
    
    # Notifications
    notify_mode: str = "mock"  # mock | twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    
    # Config files (relative to ops/api directory)
    departments_file: str = "../../contracts/config/departments.yaml"
    urgency_rules_file: str = "../../contracts/config/urgency_rules.yaml"
    sms_templates_file: str = "../../contracts/config/sms_templates.yaml"
    seed_users_file: str = "seed_users.yaml"
    
    # Timezone
    timezone: str = "Asia/Kolkata"
    
    # Seed
    seed_users_on_startup: bool = True
    
    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative file path against the ops/api directory."""
        # __file__ is in resolvix_ops/config.py, so go up to ops/api
        base_dir = Path(__file__).parent.parent
        return (base_dir / relative_path).resolve()
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS as comma-separated list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def load_settings() -> Settings:
    """Load and validate settings."""
    return Settings()  # type: ignore[call-arg]
