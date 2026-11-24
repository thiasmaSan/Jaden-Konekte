from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str = "api"
    mqtt_password_file: Optional[str] = None
    mqtt_password: Optional[str] = None

    capteur_delai_hors_ligne_s: int = Field(
        default=120,
        ge=1,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
