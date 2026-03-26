from fastapi import FastAPI

from app.core.config import settings
from app.routers.chatbot import router as chatbot_router
from app.routers.species import router as species_router

app = FastAPI(title=settings.app_name, version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


app.include_router(species_router, prefix="/api")
app.include_router(chatbot_router, prefix="/api")
