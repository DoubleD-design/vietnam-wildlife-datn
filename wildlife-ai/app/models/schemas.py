from typing import Any

from pydantic import BaseModel, Field


class SpeciesCardResponse(BaseModel):
    id: str
    scientificName: str | None = None
    vietnameseName: str | None = None
    conservationStatus: str | None = None
    heroImageUrl: str | None = None


class SpeciesSummaryResponse(BaseModel):
    id: str
    scientificName: str | None = None
    vietnameseName: str | None = None
    conservationStatus: str | None = None
    shortDescription: str | None = None
    heroImageUrl: str | None = None
    mediaUrls: list[str] = Field(default_factory=list)


class SpeciesScientificProfileResponse(BaseModel):
    id: str
    canonicalId: str | None = None
    scientificName: str | None = None
    authority: str | None = None
    rank: str | None = None
    commonNameVi: str | None = None
    commonNameEn: str | None = None
    group: str | None = None
    taxonomy: dict[str, Any] = Field(default_factory=dict)
    imageUrl: str | None = None
    mediaAssets: list[dict[str, Any]] = Field(default_factory=list)
    description: str | None = None
    distribution: dict[str, Any] = Field(default_factory=dict)
    behavior: str | None = None
    ecology: dict[str, Any] = Field(default_factory=dict)
    conservation: dict[str, Any] = Field(default_factory=dict)
    searchKeywords: list[str] = Field(default_factory=list)


class ChatQueryRequest(BaseModel):
    sessionId: str
    question: str | None = None
    imageUrl: str | None = None
    imageRejected: bool = False


class ConfirmSpeciesRequest(BaseModel):
    sessionId: str
    speciesId: str


class ClearSessionRequest(BaseModel):
    sessionId: str


class SpeciesCandidateResponse(BaseModel):
    speciesId: str
    scientificName: str | None = None
    vietnameseName: str | None = None
    heroImageUrl: str | None = None


class ChatQueryResponse(BaseModel):
    status: str
    message: str
    answer: str | None = None
    activeSpeciesId: str | None = None
    activeSpeciesName: str | None = None
    candidates: list[SpeciesCandidateResponse] = Field(default_factory=list)
