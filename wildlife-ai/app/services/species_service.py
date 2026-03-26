from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from app.core.config import settings
from app.models.schemas import (
    SpeciesCardResponse,
    SpeciesScientificProfileResponse,
    SpeciesSummaryResponse,
)


class SpeciesService:
    def __init__(self) -> None:
        self.client = MongoClient(settings.mongodb_uri)
        self.collection = self.client[settings.mongodb_database][
            settings.mongodb_species_collection
        ]

    def list_species(self, keyword: str, page: int, size: int) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if keyword.strip():
            query = {
                "$or": [
                    {"scientific_name": {"$regex": keyword, "$options": "i"}},
                    {"common_name_vi": {"$regex": keyword, "$options": "i"}},
                ]
            }

        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(page * size).limit(size)
        content = [self._to_card(doc).model_dump() for doc in cursor]

        return {
            "content": content,
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": (total + size - 1) // size if size > 0 else 0,
        }

    def get_species_summary(self, species_id: str) -> SpeciesSummaryResponse:
        doc = self._find_by_id(species_id)
        return self._to_summary(doc)

    def get_scientific_profile(
        self, species_id: str
    ) -> SpeciesScientificProfileResponse:
        doc = self._find_by_id(species_id)
        return SpeciesScientificProfileResponse(
            id=str(doc.get("_id")),
            canonicalId=doc.get("canonical_id"),
            scientificName=doc.get("scientific_name"),
            authority=doc.get("authority"),
            rank=doc.get("rank"),
            commonNameVi=doc.get("common_name_vi"),
            commonNameEn=doc.get("common_name_en"),
            group=doc.get("group"),
            taxonomy=doc.get("taxonomy") or {},
            imageUrl=doc.get("image_url"),
            mediaAssets=doc.get("media_assets") or [],
            description=doc.get("description"),
            distribution=doc.get("distribution") or {},
            behavior=doc.get("behavior"),
            ecology=doc.get("ecology") or {},
            conservation=doc.get("conservation") or {},
            searchKeywords=doc.get("search_keywords") or [],
        )

    def get_species_doc(self, species_id: str) -> dict[str, Any]:
        return self._find_by_id(species_id)

    def find_species_mentioned(self, question: str) -> dict[str, Any] | None:
        if not question.strip():
            return None

        query = {
            "$or": [
                {"scientific_name": {"$regex": question, "$options": "i"}},
                {"common_name_vi": {"$regex": question, "$options": "i"}},
            ]
        }
        return self.collection.find_one(query)

    def top_candidates(self, limit: int = 6) -> list[SpeciesCardResponse]:
        docs = list(self.collection.find({}).limit(limit))
        return [self._to_card(doc) for doc in docs]

    def _find_by_id(self, species_id: str) -> dict[str, Any]:
        query: dict[str, Any]
        if ObjectId.is_valid(species_id):
            query = {"_id": ObjectId(species_id)}
        else:
            query = {"_id": species_id}

        doc = self.collection.find_one(query)
        if not doc:
            raise ValueError(f"Species not found: {species_id}")
        return doc

    def _to_card(self, doc: dict[str, Any]) -> SpeciesCardResponse:
        return SpeciesCardResponse(
            id=str(doc.get("_id")),
            scientificName=doc.get("scientific_name"),
            vietnameseName=doc.get("common_name_vi"),
            conservationStatus=(doc.get("conservation") or {})
            .get("iucn", {})
            .get("category"),
            heroImageUrl=self._resolve_hero_image(doc),
        )

    def _to_summary(self, doc: dict[str, Any]) -> SpeciesSummaryResponse:
        media_urls: list[str] = []
        for asset in doc.get("media_assets") or []:
            url = asset.get("blob_url") or asset.get("url")
            if url:
                media_urls.append(url)

        return SpeciesSummaryResponse(
            id=str(doc.get("_id")),
            scientificName=doc.get("scientific_name"),
            vietnameseName=doc.get("common_name_vi"),
            conservationStatus=(doc.get("conservation") or {})
            .get("iucn", {})
            .get("category"),
            shortDescription=doc.get("description"),
            heroImageUrl=self._resolve_hero_image(doc),
            mediaUrls=media_urls,
        )

    def _resolve_hero_image(self, doc: dict[str, Any]) -> str | None:
        image_url = doc.get("image_url")
        if image_url:
            return image_url

        assets = doc.get("media_assets") or []
        for asset in assets:
            if asset.get("is_hero"):
                return asset.get("blob_url") or asset.get("url")

        if assets:
            return assets[0].get("blob_url") or assets[0].get("url")
        return None
