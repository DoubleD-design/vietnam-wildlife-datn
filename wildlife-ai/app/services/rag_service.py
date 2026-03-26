from __future__ import annotations

import time
from typing import Any

import requests

from app.core.config import settings
from app.services.species_service import SpeciesService

OUT_OF_SCOPE_MESSAGE = "Mình chưa thể trả lời câu hỏi này vì nội dung vượt ngoài phạm vi dữ liệu hiện có của mình."


class RagService:
    def __init__(self, species_service: SpeciesService) -> None:
        self.species_service = species_service

    def answer(self, question: str, active_species: dict[str, Any] | None) -> str:
        contexts = self._retrieve_contexts(question, active_species)
        if not contexts:
            return OUT_OF_SCOPE_MESSAGE

        prompt = self._build_prompt(question, contexts)
        generated = self._call_cerebras(prompt)
        return generated or OUT_OF_SCOPE_MESSAGE

    def _retrieve_contexts(
        self, question: str, active_species: dict[str, Any] | None
    ) -> list[str]:
        query = (question or "").strip()
        if not query:
            return []

        contexts: list[str] = []

        if active_species:
            active_context = self._doc_to_context(active_species)
            if active_context:
                contexts.append(active_context)

        keyword_query = {
            "$or": [
                {"scientific_name": {"$regex": query, "$options": "i"}},
                {"common_name_vi": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
                {"search_keywords": {"$elemMatch": {"$regex": query, "$options": "i"}}},
            ]
        }

        docs = list(
            self.species_service.collection.find(keyword_query).limit(
                settings.rag_top_k
            )
        )

        for doc in docs:
            context = self._doc_to_context(doc)
            if context and context not in contexts:
                contexts.append(context)

        return contexts[: settings.rag_top_k]

    def _doc_to_context(self, doc: dict[str, Any]) -> str:
        if not doc:
            return ""

        scientific_name = doc.get("scientific_name") or ""
        common_vi = doc.get("common_name_vi") or ""
        rank = doc.get("rank") or ""
        taxonomy = doc.get("taxonomy") or {}
        conservation = doc.get("conservation") or {}
        iucn = (conservation.get("iucn") or {}).get("category", "unknown")
        description = (doc.get("description") or "").strip()

        if not description:
            return ""

        return (
            f"Loai: {common_vi} ({scientific_name}). "
            f"Rank: {rank}. IUCN: {iucn}. Taxonomy: {taxonomy}. "
            f"Mo ta: {description}"
        )

    def _build_prompt(self, question: str, contexts: list[str]) -> str:
        context_block = "\n\n".join(
            f"[{idx + 1}] {ctx}" for idx, ctx in enumerate(contexts)
        )
        return (
            "Ban la tro ly ve dong vat hoang da Viet Nam. "
            "Chi duoc tra loi dua tren ngữ cảnh cung cap. "
            "Neu khong du thong tin, phai noi ro khong du co so de ket luan.\n\n"
            f"NGU CANH:\n{context_block}\n\n"
            f"CAU HOI: {question}\n\n"
            "TRA LOI NGAN GON, CHINH XAC, BANG TIENG VIET."
        )

    def _call_cerebras(self, prompt: str) -> str | None:
        if not settings.cerebras_api_key:
            return None

        headers = {
            "Authorization": f"Bearer {settings.cerebras_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.cerebras_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise wildlife RAG assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        for attempt in range(settings.rag_max_api_retries):
            try:
                response = requests.post(
                    settings.cerebras_api_url,
                    headers=headers,
                    json=payload,
                    timeout=45,
                )
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    return None
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                return None
            except Exception:
                if attempt == settings.rag_max_api_retries - 1:
                    return None
                time.sleep(min(settings.rag_max_retry_wait_seconds, attempt + 1))

        return None
