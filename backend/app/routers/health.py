from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "env": s.env, "emulator": bool(s.firestore_emulator_host)}
