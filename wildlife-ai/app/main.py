import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.routers.chatbot import chatbot_service, router as chatbot_router
from app.routers.species import router as species_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    preload_status = chatbot_service.preload_runtime()
    logger.info(
        "AI runtime preload completed: rag_loaded=%s vision_loaded=%s errors=%s",
        preload_status.get("rag", {}).get("loaded"),
        preload_status.get("visionLoaded"),
        preload_status.get("errors"),
    )
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


app.include_router(species_router, prefix="/api")
app.include_router(chatbot_router, prefix="/api")
