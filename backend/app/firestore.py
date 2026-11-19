import os
from functools import lru_cache

from google.cloud import firestore

from app.config import get_settings


@lru_cache
def get_db() -> firestore.Client:
    """Cliente Firestore. Em dev, aponta para o emulador via FIRESTORE_EMULATOR_HOST."""
    settings = get_settings()
    if settings.firestore_emulator_host:
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host
    elif settings.env == "dev":
        raise RuntimeError(
            "env=dev sem FIRESTORE_EMULATOR_HOST: recusando conectar em Firestore real."
        )
    return firestore.Client(project=settings.gcp_project_id)
