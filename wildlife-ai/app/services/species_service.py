from __future__ import annotations

import re
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

    def list_species(
        self,
        keyword: str,
        page: int,
        size: int,
        sector_slug: str = "",
        conservation_status: str = "",
    ) -> dict[str, Any]:
        query = self._build_species_list_query(
            keyword=keyword,
            sector_slug=sector_slug,
            conservation_status=conservation_status,
        )

        projection = {
            "_id": 1,
            "scientific_name": 1,
            "common_name_vi": 1,
            "conservation": 1,
            "conservation_status": 1,
            "image_url": 1,
            "thumbnail_url": 1,
            "media_assets.url": 1,
            "media_assets.blob_url": 1,
            "media_assets.is_hero": 1,
            "media_assets.thumbnail_url": 1,
            "group": 1,
            "distribution": 1,
        }

        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query, projection)
            .sort([("common_name_vi", 1), ("scientific_name", 1)])
            .skip(page * size)
            .limit(size)
        )
        content = [self._to_card(doc).model_dump() for doc in cursor]

        return {
            "content": content,
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": (total + size - 1) // size if size > 0 else 0,
        }

    def _build_species_list_query(
        self, keyword: str, sector_slug: str, conservation_status: str
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []

        if keyword.strip():
            escaped_keyword = re.escape(keyword.strip())
            filters.append(
                {
                    "$or": [
                        {
                            "scientific_name": {
                                "$regex": escaped_keyword,
                                "$options": "i",
                            }
                        },
                        {
                            "common_name_vi": {
                                "$regex": escaped_keyword,
                                "$options": "i",
                            }
                        },
                    ]
                }
            )

        sector_query = self._sector_query(sector_slug)
        if sector_query:
            filters.append(sector_query)

        status_query = self._conservation_status_query(conservation_status)
        if status_query:
            filters.append(status_query)

        if not filters:
            return {}
        if len(filters) == 1:
            return filters[0]
        return {"$and": filters}

    def _sector_query(self, sector_slug: str) -> dict[str, Any] | None:
        normalized = (sector_slug or "").strip().lower()
        if normalized == "chim":
            return {"group": {"$regex": "(aves|bird)", "$options": "i"}}
        if normalized == "thu":
            return {"group": {"$regex": "(mamm|mammalia)", "$options": "i"}}
        if normalized == "luong-cu":
            return {"group": {"$regex": "(amphib|amphibia)", "$options": "i"}}
        if normalized == "khac":
            return {
                "$nor": [
                    {"group": {"$regex": "(aves|bird)", "$options": "i"}},
                    {"group": {"$regex": "(mamm|mammalia)", "$options": "i"}},
                    {"group": {"$regex": "(amphib|amphibia)", "$options": "i"}},
                ]
            }
        return None

    def _conservation_status_query(
        self, conservation_status: str
    ) -> dict[str, Any] | None:
        normalized = (conservation_status or "").strip().upper()
        if normalized not in {"LC", "NT", "VU", "EN", "CR", "DD"}:
            return None

        exact = f"^{re.escape(normalized)}$"
        return {
            "$or": [
                {"conservation_status": {"$regex": exact, "$options": "i"}},
                {"conservation.iucn.category": {"$regex": exact, "$options": "i"}},
                {"conservation.iucn_category": {"$regex": exact, "$options": "i"}},
                {"conservation.iucnCategory": {"$regex": exact, "$options": "i"}},
            ]
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
            shortDescription=doc.get("short_description") or doc.get("description"),
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

        # Try to extract species names from the question
        # Look for scientific names (e.g., "Genus species") or Vietnamese names
        question_lower = question.lower()

        # First, try longer phrases (2-3 consecutive words)
        # by checking if any scientific_name is contained in the question
        docs = list(
            self.collection.find(
                {}, {"_id": 1, "scientific_name": 1, "common_name_vi": 1}
            )
        )

        for doc in docs:
            sci_name = str(doc.get("scientific_name") or "").lower()
            vi_name = str(doc.get("common_name_vi") or "").lower()

            # Check if scientific name appears as a substring in the question
            if sci_name and sci_name in question_lower:
                return self.collection.find_one({"_id": doc["_id"]})

            # Check if Vietnamese name appears as substring
            if vi_name and len(vi_name) > 2 and vi_name in question_lower:
                return self.collection.find_one({"_id": doc["_id"]})

        # Fallback: try regex match on individual species names
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

    def candidates_from_predicted_names(
        self, predictions: list[tuple[str, float]], limit: int = 6
    ) -> list[SpeciesCardResponse]:
        cards: list[SpeciesCardResponse] = []
        seen_ids: set[str] = set()

        for predicted_name, _ in predictions:
            normalized = self._normalize_species_text(predicted_name)
            if not normalized:
                continue

            doc = self.collection.find_one(
                {
                    "scientific_name": {
                        "$regex": f"^{re.escape(normalized)}$",
                        "$options": "i",
                    }
                }
            )

            if doc is None:
                # Fallback for punctuation/spacing mismatches between class mapping and DB.
                cursor = self.collection.find(
                    {},
                    {
                        "_id": 1,
                        "scientific_name": 1,
                        "common_name_vi": 1,
                        "conservation": 1,
                        "image_url": 1,
                        "thumbnail_url": 1,
                        "media_assets": 1,
                    },
                )
                for candidate in cursor:
                    sci = self._normalize_species_text(
                        str(candidate.get("scientific_name") or "")
                    )
                    if sci == normalized:
                        doc = candidate
                        break

            if doc is None:
                continue

            doc_id = str(doc.get("_id"))
            if doc_id in seen_ids:
                continue

            seen_ids.add(doc_id)
            cards.append(self._to_card(doc))
            if len(cards) >= limit:
                break

        return cards

    def _normalize_species_text(self, value: str) -> str:
        text = (value or "").replace("_", " ").strip().lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

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
            conservationStatus=self._resolve_conservation_status(doc),
            heroImageUrl=self._resolve_hero_image(doc),
            thumbnailUrl=self._resolve_thumbnail_image(doc),
            group=doc.get("group"),
            region=self._resolve_primary_region(doc),
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
            conservationStatus=self._resolve_conservation_status(doc),
            shortDescription=doc.get("short_description") or doc.get("description"),
            heroImageUrl=self._resolve_hero_image(doc),
            mediaUrls=media_urls,
        )

    def _resolve_conservation_status(self, doc: dict[str, Any]) -> str | None:
        conservation = doc.get("conservation") or {}
        nested = conservation.get("iucn") or {}
        for value in (
            nested.get("category"),
            conservation.get("iucn_category"),
            conservation.get("iucnCategory"),
            doc.get("conservation_status"),
        ):
            if value:
                return str(value)
        return None

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

    def _resolve_thumbnail_image(self, doc: dict[str, Any]) -> str | None:
        thumbnail_url = doc.get("thumbnail_url")
        if thumbnail_url:
            return thumbnail_url

        assets = doc.get("media_assets") or []
        for asset in assets:
            if asset.get("is_hero") and asset.get("thumbnail_url"):
                return asset.get("thumbnail_url")

        for asset in assets:
            if asset.get("thumbnail_url"):
                return asset.get("thumbnail_url")

        return self._resolve_hero_image(doc)

    def _resolve_primary_region(self, doc: dict[str, Any]) -> str | None:
        distribution = doc.get("distribution") or {}
        for key in ("primary_region", "region", "range"):
            value = distribution.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        countries = distribution.get("countries")
        if isinstance(countries, list) and countries:
            first_country = countries[0]
            if isinstance(first_country, str):
                return first_country
        return None
