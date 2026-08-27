from __future__ import annotations

import re
import time
import unicodedata
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
        self.client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        self.collection = self.client[settings.mongodb_database][
            settings.mongodb_species_collection
        ]
        self._lookup_cache: list[dict[str, Any]] | None = None
        self._lookup_cache_loaded_at = 0.0
        self._lookup_cache_ttl_seconds = 300

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
            "media_assets.medium_url": 1,
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
            legal=doc.get("legal") or {},
            safety=doc.get("safety") or {},
            searchKeywords=doc.get("search_keywords") or [],
        )

    def get_species_doc(self, species_id: str) -> dict[str, Any]:
        return self._find_by_id(species_id)

    def find_species_mentioned(self, question: str) -> dict[str, Any] | None:
        mentions = self.find_species_mentions(question)
        return mentions[0] if mentions else None

    def find_species_mentions(self, question: str) -> list[dict[str, Any]]:
        normalized_question = self._normalize_query_text(question)
        if not normalized_question:
            return []

        docs = self._species_lookup_docs()
        alias_owners: dict[str, set[str]] = {}
        for doc in docs:
            doc_id = str(doc.get("_id"))
            for alias in self._species_aliases(doc):
                normalized_alias = self._normalize_query_text(alias)
                if normalized_alias:
                    alias_owners.setdefault(normalized_alias, set()).add(doc_id)

        matches: list[tuple[int, int, dict[str, Any]]] = []
        for doc in docs:
            best: tuple[int, int] | None = None
            for alias in self._species_aliases(doc):
                normalized_alias = self._normalize_query_text(alias)
                if len(normalized_alias) < 3:
                    continue
                if len(alias_owners.get(normalized_alias, set())) != 1:
                    continue
                match = re.search(
                    rf"(?<![a-zA-Z0-9]){re.escape(normalized_alias)}(?![a-zA-Z0-9])",
                    normalized_question,
                )
                if not match:
                    continue
                candidate = (match.start(), len(normalized_alias))
                if best is None or candidate[1] > best[1]:
                    best = candidate
            if best is not None:
                matches.append((best[0], best[1], doc))

        matches.sort(key=lambda item: (item[0], -item[1]))
        selected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        occupied: list[tuple[int, int]] = []
        for start, length, doc in matches:
            end = start + length
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            doc_id = str(doc.get("_id"))
            if doc_id in seen_ids:
                continue
            selected.append(doc)
            seen_ids.add(doc_id)
            occupied.append((start, end))
        return selected

    def resolve_named_entities(self, labels: list[str]) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for raw_label in labels:
            label = re.sub(r"\s+", " ", str(raw_label or "")).strip(" .,:;!?")
            if not label:
                continue
            exact_docs = self._find_species_exact_matches(label)
            if len(exact_docs) == 1:
                exact_doc = exact_docs[0]
                entities.append(
                    {
                        "label": label,
                        "status": "matched",
                        "doc": exact_doc,
                        "display_name": self._display_species_name(exact_doc),
                    }
                )
                continue
            if len(exact_docs) > 1:
                entities.append(
                    {
                        "label": label,
                        "status": "ambiguous",
                        "doc": None,
                        "display_name": label,
                        "candidates": [
                            self._display_species_name(candidate)
                            for candidate in exact_docs[:5]
                        ],
                        "candidate_docs": exact_docs[:5],
                    }
                )
                continue

            candidates = self._find_species_candidates_by_label(label, limit=5)
            if len(candidates) == 1:
                doc = candidates[0]
                entities.append(
                    {
                        "label": label,
                        "status": "nearest_match",
                        "doc": None,
                        "display_name": self._display_species_name(doc),
                        "candidate_docs": candidates,
                    }
                )
            elif len(candidates) > 1:
                entities.append(
                    {
                        "label": label,
                        "status": "ambiguous",
                        "doc": None,
                        "display_name": label,
                        "candidates": [
                            self._display_species_name(candidate)
                            for candidate in candidates
                        ],
                        "candidate_docs": candidates,
                    }
                )
            else:
                entities.append(
                    {
                        "label": label,
                        "status": "not_found",
                        "doc": None,
                        "display_name": label,
                    }
                )
        return entities

    def answer_multi_species_comparison(
        self,
        question: str,
        entities: list[dict[str, Any]],
        intents: list[str] | None = None,
        fact_overrides: dict[str, dict[str, str]] | None = None,
    ) -> str:
        fact_overrides = fact_overrides or {}
        requested = [item for item in (intents or []) if item != "general"]
        if not requested:
            requested = ["distribution", "habitat", "diet", "conservation"]
        supported = [
            item
            for item in requested
            if item
            in {
                "name",
                "scientific_name",
                "taxonomy",
                "group",
                "occurrence",
                "distribution",
                "habitat",
                "diet",
                "conservation",
                "threats",
                "population_trend",
                "behavior",
                "identification",
                "reproduction",
            }
        ]
        if not supported:
            supported = ["distribution", "habitat", "diet", "conservation"]

        matched = [entity for entity in entities if isinstance(entity.get("doc"), dict)]
        headers = [self._display_species_name(entity["doc"]) for entity in matched]
        rows: list[tuple[str, list[str]]] = []
        for intent in supported:
            values = [
                self._comparison_value(
                    entity["doc"], intent, fact_overrides.get(str(entity["doc"].get("_id")), {})
                )
                for entity in matched
            ]
            rows.append((self._comparison_intent_label(intent), values))

        lines = ["**Bảng so sánh**", ""]
        lines.append("| Tiêu chí | " + " | ".join(self._escape_table(item) for item in headers) + " |")
        lines.append("|---|" + "---|" * len(headers))
        for label, values in rows:
            lines.append(
                f"| {self._escape_table(label)} | "
                + " | ".join(self._escape_table(value or "Chưa có dữ liệu") for value in values)
                + " |"
            )

        same: list[str] = []
        different: list[str] = []
        for label, values in rows:
            normalized_values = {
                self._normalize_query_text(value)
                for value in values
                if value and "chua co du lieu" not in self._normalize_query_text(value)
            }
            if len(normalized_values) == 1 and len(values) > 1:
                same.append(label.lower())
            elif len(normalized_values) > 1:
                different.append(label.lower())

        lines.extend(["", "**Điểm giống nhau**"])
        lines.append(
            "- Các loài có dữ liệu tương đồng về " + ", ".join(same) + "."
            if same
            else "- Chưa thấy tiêu chí nào có giá trị hoàn toàn giống nhau trong dữ liệu hiện có."
        )
        lines.extend(["", "**Điểm khác nhau**"])
        lines.append(
            "- Khác biệt được ghi nhận ở " + ", ".join(different) + "."
            if different
            else "- Dữ liệu hiện có chưa đủ để xác định khác biệt rõ ràng."
        )
        lines.extend(["", "**Kết luận**"])
        diet_target = self._diet_target_from_comparison_question(question)
        if "diet" in supported and diet_target:
            target_aliases = self._diet_target_aliases(diet_target)
            matching_names = (
                [
                    self._display_species_name(entity["doc"])
                    for entity in matched
                    if self._contains_any_term(
                        self._comparison_value(
                            entity["doc"],
                            "diet",
                            fact_overrides.get(str(entity["doc"].get("_id")), {}),
                        ),
                        target_aliases,
                    )
                ]
                if target_aliases
                else []
            )
            if matching_names:
                lines.append(
                    f"- Theo dữ liệu thức ăn, {', '.join(matching_names)} ăn {diet_target}."
                )
            else:
                lines.append(
                    f"- Dữ liệu hiện có chưa ghi nhận loài nào trong nhóm ăn {diet_target}."
                )
        elif "conservation" in supported:
            priority = {"CR": 0, "EN": 1, "VU": 2, "NT": 3, "LC": 4, "DD": 5, "NE": 6}
            ranked = sorted(
                (
                    priority.get((self._resolve_conservation_status(entity["doc"]) or "").upper(), 99),
                    self._display_species_name(entity["doc"]),
                    self._resolve_conservation_status(entity["doc"]) or "không rõ",
                )
                for entity in matched
            )
            if ranked and ranked[0][0] < 99:
                lines.append(
                    f"- Theo thứ bậc IUCN trong dữ liệu, {ranked[0][1]} có mức cảnh báo cao nhất ({ranked[0][2]})."
                )
            else:
                lines.append("- Chưa đủ dữ liệu IUCN để kết luận loài nào có mức cảnh báo cao hơn.")
        else:
            lines.append(
                f"- So sánh tập trung vào {', '.join(self._comparison_intent_label(item).lower() for item in supported)}; các khác biệt cụ thể được thể hiện trong bảng."
            )
        return "\n".join(lines)

    def _diet_target_from_comparison_question(self, question: str) -> str | None:
        match = re.search(
            r"loài\s+nào\s+ăn\s+(.+?)(?:[?.!]|$)",
            question or "",
            flags=re.IGNORECASE,
        )
        if match:
            target = match.group(1).strip(" .,:;!?")
            if self._normalize_query_text(target) not in {"gi", "nhung gi"}:
                return target

        normalized = self._normalize_query_text(question)
        match = re.search(r"loai nao an (.+?)(?:$| thi | trong )", normalized)
        if match:
            target = match.group(1).strip()
            if target not in {"gi", "nhung gi"}:
                return target
        return None

    def _diet_target_aliases(self, target: str) -> list[str]:
        normalized = self._normalize_query_text(target)
        aliases = {
            "ca": ["ca", "fish", "fishes", "small fish"],
            "con trung": ["con trung", "insect", "insects"],
            "dong vat co vu nho": ["dong vat co vu nho", "small mammal", "small mammals"],
            "giap xac": ["giap xac", "crustacean", "crustaceans"],
            "luong cu": ["luong cu", "amphibian", "amphibians"],
            "bo sat": ["bo sat", "reptile", "reptiles"],
            "qua": ["qua", "fruit", "fruits"],
            "co": ["co", "grass", "grasses"],
        }
        return aliases.get(normalized, [normalized] if normalized else [])

    def _contains_any_term(self, value: str, terms: list[str]) -> bool:
        normalized_value = self._normalize_query_text(value)
        return any(
            re.search(
                rf"(?<![a-zA-Z0-9]){re.escape(term)}(?![a-zA-Z0-9])",
                normalized_value,
            )
            for term in terms
            if term
        )

    def display_species_name(self, doc: dict[str, Any]) -> str:
        return self._display_species_name(doc)

    def resolve_hero_image(self, doc: dict[str, Any]) -> str | None:
        return self._resolve_hero_image(doc)

    def resolve_thumbnail_image(self, doc: dict[str, Any]) -> str | None:
        return self._resolve_thumbnail_image(doc)

    def _comparison_intent_label(self, intent: str) -> str:
        return {
            "name": "Tên thường gọi",
            "scientific_name": "Tên khoa học",
            "taxonomy": "Phân loại",
            "group": "Nhóm loài",
            "occurrence": "Ghi nhận tại Việt Nam",
            "distribution": "Phân bố",
            "habitat": "Sinh cảnh",
            "diet": "Thức ăn",
            "conservation": "Bảo tồn",
            "threats": "Mối đe dọa",
            "population_trend": "Xu hướng quần thể",
            "behavior": "Tập tính",
            "identification": "Nhận dạng",
            "reproduction": "Sinh sản",
        }.get(intent, intent)

    def _comparison_value(
        self, doc: dict[str, Any], intent: str, overrides: dict[str, str]
    ) -> str:
        if intent in overrides:
            return overrides[intent]
        taxonomy = doc.get("taxonomy") or {}
        conservation = doc.get("conservation") or {}
        if intent == "name":
            return str(doc.get("common_name_vi") or "Chưa có dữ liệu")
        if intent == "scientific_name":
            return str(doc.get("scientific_name") or "Chưa có dữ liệu")
        if intent == "taxonomy":
            values = [taxonomy.get("class"), taxonomy.get("order"), taxonomy.get("family")]
            return " - ".join(str(item) for item in values if item) or "Chưa có dữ liệu"
        if intent == "group":
            return str(taxonomy.get("class") or "Chưa có dữ liệu")
        if intent in {"occurrence", "distribution"}:
            return self._resolve_distribution_regions(doc) or "Chưa có dữ liệu"
        if intent == "habitat":
            return self._resolve_habitat(doc) or "Chưa có dữ liệu"
        if intent == "diet":
            return self._resolve_diet(doc) or "Chưa có dữ liệu"
        if intent == "conservation":
            return self._format_conservation_fact(doc).removeprefix("bảo tồn: ")
        if intent == "threats":
            threats = conservation.get("major_threats") or conservation.get("threats")
            return ", ".join(self._flatten_text_values(threats)) or "Chưa có dữ liệu"
        if intent == "population_trend":
            iucn = conservation.get("iucn") or {}
            return str(iucn.get("population_trend") or "Chưa có dữ liệu")
        if intent == "behavior":
            return str(doc.get("behavior") or "Chưa có dữ liệu")
        if intent == "identification":
            return str(doc.get("short_description") or doc.get("description") or "Chưa có dữ liệu")
        return "Chưa có dữ liệu"

    def _escape_table(self, value: str) -> str:
        compact = re.sub(r"\s+", " ", str(value or "")).strip()
        return compact.replace("|", "\\|")

    def answer_general_query(self, question: str, limit: int = 30) -> str | None:
        normalized = self._normalize_query_text(question)
        if not self._looks_like_general_query(normalized):
            return None

        if self._is_top_threatened_query(normalized):
            return self._build_top_threatened_answer(limit=limit)

        iucn_category = self._extract_iucn_category(normalized)
        if iucn_category:
            query = self._conservation_status_query(iucn_category) or {}
            return self._build_species_list_answer(
                title=f"Các loài có mức IUCN {iucn_category}",
                query=query,
                limit=limit,
                note="Danh sách dựa trên metadata bảo tồn trong MongoDB.",
            )

        family = self._extract_family(question)
        if family:
            query = {
                "taxonomy.family": {
                    "$regex": f"^{re.escape(family)}$",
                    "$options": "i",
                }
            }
            return self._build_species_list_answer(
                title=f"Các loài thuộc họ {family}",
                query=query,
                limit=limit,
                note="Danh sách dựa trên metadata phân loại học trong MongoDB.",
            )

        habitat = self._extract_habitat(normalized)
        if habitat:
            query = self._habitat_query(habitat["patterns"])
            return self._build_species_list_answer(
                title=f"Các loài sống ở {habitat['label']}",
                query=query,
                limit=limit,
                note="Danh sách dựa trên metadata sinh cảnh trong MongoDB.",
            )

        diet = self._extract_diet(normalized)
        if diet:
            query = self._diet_query(diet["patterns"])
            return self._build_species_list_answer(
                title=f"Các loài ăn {diet['label']}",
                query=query,
                limit=limit,
                note="Danh sách dựa trên metadata thức ăn/chế độ ăn trong MongoDB.",
            )

        regions = self._extract_regions(question)
        if regions:
            query = self._region_query(regions)
            title_regions = "/".join(regions)
            return self._build_species_list_answer(
                title=f"Các loài phân bố ở {title_regions}",
                query=query,
                limit=limit,
                note="Danh sách dựa trên metadata vùng phân bố trong MongoDB.",
            )

        return None

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

    def _normalize_query_text(self, value: str) -> str:
        text = (value or "").replace("đ", "d").replace("Đ", "D")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def _find_species_exact_matches(self, label: str) -> list[dict[str, Any]]:
        normalized_label = self._normalize_query_text(label)
        if not normalized_label:
            return []
        matches: list[dict[str, Any]] = []
        for doc in self._species_lookup_docs():
            aliases = {
                self._normalize_query_text(item) for item in self._species_aliases(doc)
            }
            if normalized_label in aliases:
                matches.append(doc)
        return matches

    def _find_species_candidates_by_label(self, label: str, limit: int = 5) -> list[dict[str, Any]]:
        normalized_label = self._normalize_query_text(label)
        if not normalized_label:
            return []
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for doc in self._species_lookup_docs():
            aliases = [self._normalize_query_text(item) for item in self._species_aliases(doc)]
            scores = [
                abs(len(alias) - len(normalized_label))
                for alias in aliases
                if normalized_label in alias or alias in normalized_label
            ]
            if not scores:
                continue
            ranked.append(
                (
                    min(scores),
                    str(doc.get("common_name_vi") or doc.get("scientific_name") or ""),
                    doc,
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:limit]]

    def _species_lookup_docs(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if (
            self._lookup_cache is not None
            and now - self._lookup_cache_loaded_at < self._lookup_cache_ttl_seconds
        ):
            return [doc.copy() for doc in self._lookup_cache]

        projection = {
            "_id": 1,
            "scientific_name": 1,
            "common_name_vi": 1,
            "common_name_en": 1,
            "search_keywords": 1,
            "group": 1,
            "conservation": 1,
            "conservation_status": 1,
            "taxonomy": 1,
            "distribution": 1,
            "ecology": 1,
            "behavior": 1,
            "description": 1,
            "short_description": 1,
            "region": 1,
            "image_url": 1,
            "thumbnail_url": 1,
        }
        docs = list(self.collection.find({}, projection))
        self._lookup_cache = [doc.copy() for doc in docs]
        self._lookup_cache_loaded_at = now
        return docs

    def _species_aliases(self, doc: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("scientific_name", "common_name_vi", "common_name_en"):
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
        keywords = doc.get("search_keywords") or []
        if isinstance(keywords, list):
            values.extend(
                str(item).strip()
                for item in keywords
                if isinstance(item, str) and len(item.strip()) >= 4
            )
        return self._dedupe_values(values)

    def _display_species_name(self, doc: dict[str, Any]) -> str:
        vi_name = str(doc.get("common_name_vi") or "").strip()
        sci_name = str(doc.get("scientific_name") or "").strip()
        if vi_name and sci_name and vi_name.lower() != sci_name.lower():
            return f"{vi_name} (*{sci_name}*)"
        return vi_name or sci_name or "Không rõ tên"

    def _resolve_habitat(self, doc: dict[str, Any]) -> str:
        ecology = doc.get("ecology") or {}
        values = []
        for key in ("habitat", "habitat_tags"):
            value = ecology.get(key) or doc.get(key)
            values.extend(self._flatten_text_values(value))
        return ", ".join(self._dedupe_values(values))

    def _resolve_diet(self, doc: dict[str, Any]) -> str:
        ecology = doc.get("ecology") or {}
        values = []
        for key in ("diet", "food"):
            value = ecology.get(key) or doc.get(key)
            values.extend(self._flatten_text_values(value))
        return ", ".join(self._dedupe_values(values))

    def _flatten_text_values(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, dict):
            out: list[str] = []
            for item in value.values():
                out.extend(self._flatten_text_values(item))
            return out
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _dedupe_values(self, values: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            value = self._humanize_metadata_label(value)
            key = self._normalize_query_text(value)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    def _humanize_metadata_label(self, value: str) -> str:
        label_map = {
            "fruits": "quả",
            "fruit": "quả",
            "grasses": "cỏ",
            "grass": "cỏ",
            "leaves": "lá",
            "twigs": "cành non",
            "bark": "vỏ cây",
            "other": "khác/chưa phân loại",
            "unknown": "chưa rõ",
        }
        key = self._normalize_query_text(value)
        return label_map.get(key, value)

    def _format_conservation_fact(self, doc: dict[str, Any]) -> str:
        conservation = doc.get("conservation") or {}
        iucn = self._resolve_conservation_status(doc) or "không rõ"
        vn_red = conservation.get("vietnam_red_data") or {}
        vn_category = vn_red.get("category") or conservation.get("vietnam_red_data_category")
        vn_year = vn_red.get("year") or conservation.get("vietnam_red_data_year")
        cites = conservation.get("cites_appendix") or conservation.get("cites")
        parts = [f"IUCN: {iucn}"]
        if vn_category:
            suffix = f" ({vn_year})" if vn_year and str(vn_year) != "0" else ""
            parts.append(f"Sách đỏ Việt Nam: {vn_category}{suffix}")
        if cites:
            parts.append(f"CITES: Appendix {cites}")
        return "bảo tồn: " + "; ".join(parts)

    def _looks_like_general_query(self, normalized: str) -> bool:
        signals = [
            "cac loai",
            "nhung loai",
            "loai nao",
            "danh sach",
            "iucn",
            "thuoc ho",
            "family",
            "phan bo o",
            "phan bo tai",
            "song o",
            "dat ngap nuoc",
            "rung ngap man",
            "rung nhiet doi",
            "dong co",
            "vung nui",
            "an con trung",
            "an co",
            "an qua",
            "an thit",
            "an ca",
            "nguy cap nhat",
            "uu tien bao ton",
        ]
        return any(signal in normalized for signal in signals)

    def _is_top_threatened_query(self, normalized: str) -> bool:
        return ("top" in normalized or "uu tien bao ton" in normalized) and (
            "nguy cap" in normalized
            or "tuyet chung" in normalized
            or "uu tien bao ton" in normalized
        )

    def _extract_iucn_category(self, normalized: str) -> str | None:
        if "iucn" not in normalized and "muc bao ton" not in normalized:
            return None
        match = re.search(r"\b(cr|en|vu|nt|lc|dd)\b", normalized, flags=re.I)
        return match.group(1).upper() if match else None

    def _extract_family(self, question: str) -> str | None:
        match = re.search(
            r"(?:họ|ho|family)\s+([A-Za-z][A-Za-z0-9_-]+)",
            question or "",
            flags=re.I,
        )
        return match.group(1).strip(" .,:;!?") if match else None

    def _extract_regions(self, question: str) -> list[str]:
        normalized = self._normalize_query_text(question)
        region_map = {
            "bac bo": "Bắc Bộ",
            "trung bo": "Trung Bộ",
            "nam bo": "Nam Bộ",
            "tay nguyen": "Tây Nguyên",
        }
        regions: list[str] = []
        for key, label in region_map.items():
            if key in normalized and label not in regions:
                regions.append(label)
        return regions

    def _extract_region(self, question: str) -> str | None:
        regions = self._extract_regions(question)
        return regions[0] if regions else None

    def _extract_habitat(self, normalized: str) -> dict[str, Any] | None:
        habitat_map = [
            {
                "label": "đất ngập nước",
                "signals": ["dat ngap nuoc", "wetland"],
                "patterns": ["wetland", "đất ngập nước", "dat ngap nuoc"],
            },
            {
                "label": "rừng ngập mặn",
                "signals": ["rung ngap man", "mangrove"],
                "patterns": ["mangrove", "rừng ngập mặn", "rung ngap man"],
            },
            {
                "label": "rừng nhiệt đới",
                "signals": ["rung nhiet doi", "tropical forest"],
                "patterns": ["tropical forest", "rừng nhiệt đới", "rung nhiet doi"],
            },
            {
                "label": "đồng cỏ",
                "signals": ["dong co", "grassland"],
                "patterns": ["grassland", "đồng cỏ", "dong co"],
            },
            {
                "label": "vùng núi",
                "signals": ["vung nui", "mountain", "montane"],
                "patterns": ["mountain", "montane", "vùng núi", "vung nui"],
            },
        ]
        for item in habitat_map:
            if any(signal in normalized for signal in item["signals"]):
                return item
        return None

    def _extract_diet(self, normalized: str) -> dict[str, Any] | None:
        diet_map = [
            {
                "label": "côn trùng",
                "signals": ["an con trung", "con trung", "insects"],
                "patterns": ["insects", "côn trùng", "con trung"],
            },
            {
                "label": "cỏ",
                "signals": ["an co", "grass", "grasses"],
                "patterns": ["grass", "grasses", "cỏ"],
            },
            {
                "label": "quả",
                "signals": ["an qua", "qua", "fruits"],
                "patterns": ["fruits", "fruit", "quả", "qua"],
            },
            {
                "label": "thịt/động vật",
                "signals": ["an thit", "thit", "san moi"],
                "patterns": ["small mammals", "meat", "prey", "động vật", "dong vat", "thịt", "thit"],
            },
            {
                "label": "cá",
                "signals": ["an ca", "fish"],
                "patterns": ["fish", "cá", "ca"],
            },
        ]
        for item in diet_map:
            if any(signal in normalized for signal in item["signals"]):
                return item
        return None

    def _region_query(self, regions: list[str]) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = []
        for region in regions:
            escaped = re.escape(region)
            clauses.extend(
                [
                    {
                        "distribution.vietnam.regions": {
                            "$regex": f"^{escaped}$",
                            "$options": "i",
                        }
                    },
                    {
                        "distribution.regions": {
                            "$regex": f"^{escaped}$",
                            "$options": "i",
                        }
                    },
                    {
                        "distribution.regions_vi": {
                            "$regex": f"^{escaped}$",
                            "$options": "i",
                        }
                    },
                    {"region": {"$regex": f"^{escaped}$", "$options": "i"}},
                ]
            )
        return {"$or": clauses} if clauses else {}

    def _habitat_query(self, patterns: list[str]) -> dict[str, Any]:
        return self._metadata_text_query(
            [
                "ecology.habitat_tags",
                "ecology.habitat",
                "habitat",
                "habitat_tags",
                "distribution.habitat_tags",
                "raw_profile.ecology.habitat_tags",
                "description",
                "short_description",
            ],
            patterns,
        )

    def _diet_query(self, patterns: list[str]) -> dict[str, Any]:
        return self._metadata_text_query(
            [
                "ecology.diet",
                "ecology.food",
                "diet",
                "food",
                "raw_profile.ecology.diet",
                "description",
                "short_description",
            ],
            patterns,
        )

    def _metadata_text_query(self, fields: list[str], patterns: list[str]) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = []
        for field in fields:
            for pattern in patterns:
                if not pattern:
                    continue
                clauses.append({field: {"$regex": re.escape(pattern), "$options": "i"}})
        return {"$or": clauses} if clauses else {}

    def _build_top_threatened_answer(self, limit: int) -> str:
        projection = {
            "_id": 1,
            "scientific_name": 1,
            "common_name_vi": 1,
            "conservation": 1,
            "conservation_status": 1,
            "taxonomy": 1,
            "distribution": 1,
            "region": 1,
        }
        docs = list(self.collection.find({}, projection))
        priority = {"CR": 0, "EN": 1, "VU": 2, "NT": 3, "LC": 4, "DD": 5}

        def sort_key(doc: dict[str, Any]) -> tuple[int, str]:
            status = (self._resolve_conservation_status(doc) or "").upper()
            return priority.get(status, 99), str(
                doc.get("common_name_vi") or doc.get("scientific_name") or ""
            )

        ranked = [doc for doc in docs if (self._resolve_conservation_status(doc) or "").upper() in priority]
        ranked.sort(key=sort_key)
        limited = ranked[:limit]

        if not limited:
            return (
                "**Top các loài nguy cấp nhất trong dữ liệu hiện có:** Kho dữ liệu hiện chưa có metadata IUCN đủ để xếp hạng.\n\n"
                "**Giới hạn dữ liệu:** Sắp xếp dựa trên IUCN trong MongoDB, không thay thế đánh giá bảo tồn chính thức."
            )

        total = len(ranked)
        summary = (
            f"Tìm thấy {total} loài có mức IUCN có thể xếp hạng, hiển thị {len(limited)} loài đầu tiên."
            if total > len(limited)
            else f"Tìm thấy {total} loài có mức IUCN có thể xếp hạng."
        )
        lines = [f"**Top các loài nguy cấp nhất trong dữ liệu hiện có:** {summary}", ""]
        for index, doc in enumerate(limited, 1):
            lines.append(f"{index}. {self._format_species_list_item(doc)}")
        lines.extend(
            [
                "",
                "**Giới hạn dữ liệu:** Thứ tự xếp hạng dùng metadata IUCN trong MongoDB theo ưu tiên CR > EN > VU > NT > LC; cần kiểm tra nguồn hiện hành nếu dùng cho quyết định bảo tồn.",
            ]
        )
        return "\n".join(lines)

    def _build_species_list_answer(
        self, title: str, query: dict[str, Any], limit: int, note: str
    ) -> str:
        projection = {
            "_id": 1,
            "scientific_name": 1,
            "common_name_vi": 1,
            "conservation": 1,
            "conservation_status": 1,
            "taxonomy": 1,
            "distribution": 1,
            "ecology": 1,
            "region": 1,
        }
        total = self.collection.count_documents(query)
        docs = list(
            self.collection.find(query, projection)
            .sort([("common_name_vi", 1), ("scientific_name", 1)])
            .limit(limit)
        )

        if not docs:
            return (
                f"**{title}:** Kho dữ liệu hiện chưa có loài phù hợp với điều kiện này.\n\n"
                f"**Giới hạn dữ liệu:** {note}"
            )

        if total > len(docs):
            summary = f"Tìm thấy {total} loài trong kho dữ liệu, hiển thị {len(docs)} loài đầu tiên."
        else:
            summary = f"Tìm thấy {total} loài trong kho dữ liệu."

        lines = [f"**{title}:** {summary}", ""]
        for index, doc in enumerate(docs, 1):
            lines.append(f"{index}. {self._format_species_list_item(doc)}")

        lines.extend(["", f"**Giới hạn dữ liệu:** {note}"])
        return "\n".join(lines)

    def _format_species_list_item(self, doc: dict[str, Any]) -> str:
        vi_name = str(doc.get("common_name_vi") or "").strip()
        sci_name = str(doc.get("scientific_name") or "").strip()
        name = vi_name or sci_name or "Không rõ tên"
        sci_part = f" (*{sci_name}*)" if sci_name and sci_name != name else ""
        status = self._resolve_conservation_status(doc) or "không rõ"
        family = ((doc.get("taxonomy") or {}).get("family")) or "không rõ họ"
        regions = self._resolve_distribution_regions(doc)
        region_part = f"; phân bố: {regions}" if regions else ""
        return f"{name}{sci_part} - IUCN: {status}; họ: {family}{region_part}."

    def _resolve_distribution_regions(self, doc: dict[str, Any]) -> str:
        distribution = doc.get("distribution") or {}
        candidates = [
            ((distribution.get("vietnam") or {}).get("regions")),
            distribution.get("regions"),
            distribution.get("regions_vi"),
            doc.get("region"),
        ]
        values: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, list):
                values.extend(str(item).strip() for item in candidate if str(item).strip())
            elif isinstance(candidate, str) and candidate.strip():
                values.append(candidate.strip())
        deduped = []
        for value in values:
            label = self._normalize_region_label(value)
            if label and label not in deduped:
                deduped.append(label)
        return ", ".join(deduped)

    def _normalize_region_label(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        key = self._normalize_query_text(raw)
        region_map = {
            "north": "Bắc Bộ",
            "northern": "Bắc Bộ",
            "bac bo": "Bắc Bộ",
            "central": "Trung Bộ",
            "trung bo": "Trung Bộ",
            "south": "Nam Bộ",
            "southern": "Nam Bộ",
            "nam bo": "Nam Bộ",
            "tay nguyen": "Tây Nguyên",
        }
        return region_map.get(key, raw)

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
            url = asset.get("medium_url") or asset.get("blob_url") or asset.get("url")
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
                return asset.get("medium_url") or asset.get("blob_url") or asset.get("url")

        if assets:
            return assets[0].get("medium_url") or assets[0].get("blob_url") or assets[0].get("url")
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
                return self._normalize_region_label(value)

        countries = distribution.get("countries")
        if isinstance(countries, list) and countries:
            first_country = countries[0]
            if isinstance(first_country, str):
                return first_country
        return None
