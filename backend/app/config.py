from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente (ver .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    gcp_project_id: str = "navalha-dev"
    # Quando definida, o SDK do Firestore usa o emulador automaticamente.
    firestore_emulator_host: str | None = None
    firebase_auth_emulator_host: str | None = None
    cors_origins: list[str] = ["http://localhost:5173"]
    slot_step_minutes: int = 30
    booking_horizon_days: int = 60  # até quantos dias à frente o link público mostra horários
    # Chave TEMPORÁRIA das rotas /admin até a Fase 3 (login com claims). Vazia = rotas /admin desligadas.
    admin_api_key: str | None = None
    # "firestore" (padrão) ou "memory" (dev sem emulador; os dados somem ao reiniciar)
    repository: str = "firestore"
    # com repository=memory: cria a Barbearia MF ao subir (para testar sem emulador)
    seed_demo: bool = False
    # limite por IP nas rotas públicas: "requisições/segundos"
    rate_limit_enabled: bool = True
    rate_limit_booking: str = "6/600"  # 6 agendamentos a cada 10 min por IP
    rate_limit_read: str = "120/60"
    # pasta com o build do React (Dockerfile copia para cá); se existir, a API serve o site
    static_dir: str = "static"


@lru_cache
def get_settings() -> Settings:
    return Settings()
