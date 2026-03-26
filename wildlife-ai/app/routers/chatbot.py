from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatQueryRequest,
    ClearSessionRequest,
    ConfirmSpeciesRequest,
)
from app.services.chatbot_service import ChatbotService
from app.services.species_service import SpeciesService

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])
chatbot_service = ChatbotService(SpeciesService())


@router.post("/query")
def query(req: ChatQueryRequest):
    try:
        return chatbot_service.query(req)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@router.post("/confirm-species")
def confirm_species(req: ConfirmSpeciesRequest):
    try:
        return chatbot_service.confirm_species(req.sessionId, req.speciesId)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@router.post("/clear-species")
def clear_species(req: ClearSessionRequest):
    return chatbot_service.clear_species(req.sessionId)
