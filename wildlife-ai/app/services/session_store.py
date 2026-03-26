from dataclasses import dataclass, field

from app.models.schemas import SpeciesCandidateResponse


@dataclass
class ChatSessionState:
    current_species_id: str | None = None
    current_species_name: str | None = None
    pending_question: str | None = None
    awaiting_confirmation: bool = False
    pending_candidates: list[SpeciesCandidateResponse] = field(default_factory=list)
