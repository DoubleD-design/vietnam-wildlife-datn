from __future__ import annotations

import re
from typing import Any

from app.models.schemas import (
    ChatQueryRequest,
    ChatQueryResponse,
    SpeciesCandidateResponse,
)
from app.core.config import settings
from app.services.image_recognition_service import ImageRecognitionService
from app.services.rag_pipeline_service import RagPipelineService
from app.services.session_store import ChatSessionState
from app.services.species_service import SpeciesService

UNKNOWN_IMAGE_MESSAGE = "Xin lỗi, tôi chưa nhận diện được loài này trong cơ sở dữ liệu hiện tại. Vui lòng thử ảnh khác rõ hơn."
GREETING_MESSAGE = (
    "Xin chào! Bạn có thể dán ảnh bằng Ctrl+V, kéo thả ảnh vào ô chat, hoặc bấm Chọn ảnh để tải lên. "
    "Nếu muốn hỏi bằng chữ, hãy nêu tên loài cụ thể hoặc hỏi sau khi đã chọn đúng loài. "
    "Ví dụ: 'Loài này ăn gì?', 'Loài này có nguy cấp không?', 'Phân bố ở đâu?'"
)

NO_SPECIES_CONTEXT_MESSAGE = (
    "Mình chưa có loài đang trao đổi nên chưa thể suy ra loài từ câu hỏi này. "
    "Bạn hãy gửi ảnh, dán ảnh bằng Ctrl+V, hoặc nhập đúng tên loài để mình trả lời chính xác hơn."
)


class ChatbotService:
    def __init__(self, species_service: SpeciesService) -> None:
        self.species_service = species_service
        self.rag_service = RagPipelineService()
        self.image_recognition = ImageRecognitionService()
        self.sessions: dict[str, ChatSessionState] = {}

    def query(self, req: ChatQueryRequest) -> ChatQueryResponse:
        response, _ = self._query_internal(req, include_debug=False)
        return response

    def query_debug(self, req: ChatQueryRequest) -> dict[str, Any]:
        response, debug = self._query_internal(req, include_debug=True)
        data = response.model_dump()
        data["debug"] = debug or {}
        return data

    def _query_internal(
        self, req: ChatQueryRequest, include_debug: bool = False
    ) -> tuple[ChatQueryResponse, dict[str, Any] | None]:
        state = self.sessions.setdefault(req.sessionId, ChatSessionState())
        has_image = bool(req.imageUrl and req.imageUrl.strip())
        has_question = bool(req.question and req.question.strip())

        if not has_image and not has_question:
            raise ValueError("Request must contain question or imageUrl")

        if has_image:
            response = self._handle_image_flow(req, state, has_question)
            debug = (
                {"flow": "image", "debugAvailable": False}
                if include_debug
                else None
            )
            return response, debug

        return self._handle_text_flow(req.question or "", state, include_debug)

    def rag_health(self, load: bool = False) -> dict:
        return self.rag_service.health(load=load)

    def confirm_species(self, session_id: str, species_id: str) -> ChatQueryResponse:
        state = self.sessions.setdefault(session_id, ChatSessionState())
        species = self.species_service.get_species_doc(species_id)
        previous_name = state.current_species_name

        state.current_species_id = str(species.get("_id"))
        state.current_species_name = species.get("common_name_vi") or species.get(
            "scientific_name"
        )
        state.awaiting_confirmation = False
        state.pending_candidates = []

        current_label = (
            state.current_species_name or species.get("scientific_name") or "loài này"
        )
        updated_message = f"Loài đang được hỏi là {current_label}."

        if state.pending_question:
            answer, answer_status, _ = self._answer_with_context(
                state.pending_question, species
            )
            state.pending_question = None
            return ChatQueryResponse(
                status=answer_status,
                message=f"{updated_message} Tôi cũng đã trả lời câu hỏi của bạn.",
                answer=answer,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )

        return ChatQueryResponse(
            status="SPECIES_CONFIRMED",
            message=updated_message,
            activeSpeciesId=state.current_species_id,
            activeSpeciesName=state.current_species_name,
            candidates=[],
        )

    def clear_species(self, session_id: str) -> ChatQueryResponse:
        state = self.sessions.setdefault(session_id, ChatSessionState())
        previous_name = state.current_species_name
        state.current_species_id = None
        state.current_species_name = None
        state.pending_question = None
        state.awaiting_confirmation = False
        state.pending_candidates = []
        state.recent_multi_species_entities = []

        return ChatQueryResponse(
            status="CLEARED",
            message=(
                f"Đã xóa ngữ cảnh loài đang chọn ({previous_name}). Bạn có thể hỏi chung hoặc gửi ảnh mới."
                if previous_name
                else "Đã xóa ngữ cảnh loài đang chọn. Bạn có thể hỏi chung hoặc gửi ảnh mới."
            ),
            candidates=[],
        )

    def _handle_image_flow(
        self, req: ChatQueryRequest, state: ChatSessionState, has_question: bool
    ) -> ChatQueryResponse:
        if req.imageRejected:
            return ChatQueryResponse(
                status="UNKNOWN_SPECIES",
                message=UNKNOWN_IMAGE_MESSAGE,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )

        predictions: list[tuple[str, float]] = []
        try:
            predictions = self.image_recognition.predict(
                req.imageUrl or "", top_k=settings.vision_top_k
            )
        except Exception:
            predictions = []

        cards = self.species_service.candidates_from_predicted_names(
            predictions, limit=6
        )

        if len(cards) < 6:
            existing_ids = {card.id for card in cards}
            for card in self.species_service.top_candidates(6):
                if card.id in existing_ids:
                    continue
                cards.append(card)
                existing_ids.add(card.id)
                if len(cards) >= 6:
                    break

        if not cards and predictions:
            cards = self.species_service.candidates_from_predicted_names(
                predictions, limit=6
            )

        candidates = [
            SpeciesCandidateResponse(
                speciesId=card.id,
                scientificName=card.scientificName,
                vietnameseName=card.vietnameseName,
                heroImageUrl=card.heroImageUrl,
                thumbnailUrl=card.thumbnailUrl,
            )
            for card in cards
        ]

        if not candidates:
            return ChatQueryResponse(
                status="UNKNOWN_SPECIES",
                message=UNKNOWN_IMAGE_MESSAGE,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )

        state.awaiting_confirmation = True
        state.pending_candidates = candidates
        state.pending_question = req.question if has_question else None

        message = (
            "Vui lòng chọn đúng loài trong danh sách, hệ thống sẽ tự động trả lời câu hỏi ngay sau khi bạn xác nhận."
            if has_question
            else "Vui lòng chọn loài phù hợp trong danh sách để tiếp tục."
        )

        return ChatQueryResponse(
            status="NEED_SPECIES_CONFIRM",
            message=message,
            activeSpeciesId=None,
            activeSpeciesName=None,
            candidates=candidates,
        )

    def _handle_text_flow(
        self,
        question: str,
        state: ChatSessionState,
        include_debug: bool = False,
    ) -> tuple[ChatQueryResponse, dict[str, Any] | None]:
        normalized = self._normalize_text(question)

        if self._is_greeting(question):
            response = ChatQueryResponse(
                status="ANSWERED",
                message="Đã gửi hướng dẫn sử dụng.",
                answer=GREETING_MESSAGE,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )
            return response, {"flow": "greeting"} if include_debug else None

        if self._is_clear_command(normalized):
            previous_name = state.current_species_name
            state.current_species_id = None
            state.current_species_name = None
            state.pending_question = None
            state.awaiting_confirmation = False
            state.pending_candidates = []
            state.recent_multi_species_entities = []
            response = ChatQueryResponse(
                status="CLEARED",
                message=(
                    f"Đã xóa ngữ cảnh loài đang chọn ({previous_name}). Bạn có thể hỏi chung hoặc gửi ảnh mới."
                    if previous_name
                    else "Đã xóa ngữ cảnh loài đang chọn. Bạn có thể hỏi chung hoặc gửi ảnh mới."
                ),
                answer="Đã xóa loài hiện tại. Bạn có thể gửi ảnh mới, nhập tên loài khác, hoặc hỏi các câu tổng quát như danh sách loài theo IUCN/họ/vùng phân bố.",
                activeSpeciesId=None,
                activeSpeciesName=None,
                candidates=[],
            )
            debug = self._basic_debug("control_clear", question)
            return response, debug if include_debug else None

        if self._is_control_help_question(normalized):
            response = ChatQueryResponse(
                status="ANSWERED",
                message="Đã gửi hướng dẫn sử dụng.",
                answer=(
                    "Có. Bạn có thể gửi ảnh khác để hệ thống nhận diện lại từ đầu. "
                    "Nếu đang hỏi về một loài cũ và muốn chuyển loài, hãy gửi ảnh mới hoặc nhập tên loài mới; "
                    "nếu muốn xóa ngữ cảnh hiện tại, hãy nhắn 'xóa loài hiện tại'."
                ),
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )
            debug = self._basic_debug("control_help", question)
            return response, debug if include_debug else None

        if self._is_context_multi_species_question(normalized):
            if state.recent_multi_species_entities:
                answer = self.species_service.answer_priority_within_entities(
                    state.recent_multi_species_entities
                )
                response = ChatQueryResponse(
                    status="ANSWERED",
                    message="Tôi đang trả lời trong tập loài/entity vừa được so sánh.",
                    answer=answer,
                    activeSpeciesId=state.current_species_id,
                    activeSpeciesName=state.current_species_name,
                    candidates=[],
                )
                debug = self._multi_species_debug(
                    "multi_species_context",
                    question,
                    state.recent_multi_species_entities,
                )
                return response, debug if include_debug else None

        comparison_labels = self._extract_comparison_labels(question)
        if len(comparison_labels) >= 2:
            entities = self.species_service.resolve_named_entities(comparison_labels)
            state.recent_multi_species_entities = entities
            answer = self.species_service.answer_multi_species_comparison(
                question, entities
            )
            response = ChatQueryResponse(
                status="ANSWERED",
                message="Tôi đang so sánh các loài/entity được nêu trong câu hỏi.",
                answer=answer,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )
            debug = self._multi_species_debug(
                "multi_species_structured", question, entities
            )
            return response, debug if include_debug else None

        mentioned = self.species_service.find_species_mentioned(question)
        active_species = None
        message = ""

        if mentioned:
            active_species = mentioned
            state.current_species_id = str(mentioned.get("_id"))
            state.current_species_name = mentioned.get(
                "common_name_vi"
            ) or mentioned.get("scientific_name")
            message = f"Tôi đang trả lời theo loài {state.current_species_name}."
        elif self._is_many_species_query(normalized):
            general_answer = self.species_service.answer_general_query(question)
            if general_answer:
                response = ChatQueryResponse(
                    status="ANSWERED",
                    message="Tôi đang trả lời câu hỏi tổng quát từ metadata loài.",
                    answer=general_answer,
                    activeSpeciesId=state.current_species_id,
                    activeSpeciesName=state.current_species_name,
                    candidates=[],
                )
                debug = {
                    "flow": "general_metadata",
                    "questionPlan": self._analyze_question(question),
                    "sources": ["MongoDB species metadata"],
                    "chunks": [],
                    "evidence": [],
                    "fallback": False,
                    "dataWarnings": [],
                    "sourceQuality": [],
                    "retrievalWarnings": [],
                    "coverageWarnings": [],
                    "timingsMs": {},
                    "errors": [],
                }
                return response, debug if include_debug else None

        if not active_species and state.current_species_id:
            active_species = self.species_service.get_species_doc(
                state.current_species_id
            )
            state.current_species_name = active_species.get(
                "common_name_vi"
            ) or active_species.get("scientific_name")
            message = f"Tôi đang trả lời theo loài {state.current_species_name}."

        if not active_species:
            response = ChatQueryResponse(
                status="NEED_SPECIES_CONTEXT",
                message=NO_SPECIES_CONTEXT_MESSAGE,
                answer=NO_SPECIES_CONTEXT_MESSAGE,
                activeSpeciesId=None,
                activeSpeciesName=None,
                candidates=[],
            )
            debug = {
                "flow": "need_species_context",
                "questionPlan": self._analyze_question(question),
                "sources": [],
                "chunks": [],
                "evidence": [],
                "fallback": False,
                "dataWarnings": [],
                "sourceQuality": [],
                "retrievalWarnings": [],
                "coverageWarnings": [],
                "timingsMs": {},
                "errors": [],
            }
            return response, debug if include_debug else None

        answer, answer_status, debug = self._answer_with_context(
            question, active_species, include_debug=include_debug
        )

        response = ChatQueryResponse(
            status=answer_status,
            message=message,
            answer=answer,
            activeSpeciesId=state.current_species_id,
            activeSpeciesName=state.current_species_name,
            candidates=[],
        )
        return response, debug if include_debug else None

    def _answer_with_context(
        self,
        question: str,
        species: dict | None,
        include_debug: bool = False,
    ) -> tuple[str, str, dict[str, Any] | None]:
        scientific_name = ""
        if species:
            scientific_name = str(species.get("scientific_name") or "")
        q = (question or "").strip()
        question_plan = self._analyze_question(q)
        result = self.rag_service.answer_result(
            q, scientific_name, question_plan=question_plan
        )
        debug = (
            self._build_rag_debug(result.raw, question_plan, result.error)
            if include_debug
            else None
        )
        return result.answer, result.status, debug

    def _build_rag_debug(
        self,
        raw: dict[str, Any] | None,
        question_plan: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any]:
        raw = raw or {}
        errors = []
        if error:
            errors.append(error)
        generation_error = raw.get("generation_error")
        if generation_error:
            errors.append(str(generation_error))
        flow = raw.get("flow") or "rag"

        return {
            "flow": flow,
            "questionPlan": question_plan,
            "retrievalProfile": raw.get("retrieval_profile"),
            "retrievalAlpha": raw.get("retrieval_alpha"),
            "sources": raw.get("sources") or [],
            "sourceQuality": raw.get("source_quality") or [],
            "chunks": self._preview_chunks(raw.get("chunks") or []),
            "evidence": self._preview_evidence(raw.get("evidence") or []),
            "fallback": bool(raw.get("fallback")),
            "directAnswer": bool(raw.get("direct_answer")),
            "dataWarnings": raw.get("data_warnings") or [],
            "retrievalWarnings": raw.get("retrieval_warnings") or [],
            "coverageWarnings": raw.get("coverage_warnings") or [],
            "timingsMs": raw.get("timings_ms") or {},
            "errors": errors,
        }

    def _preview_chunks(self, chunks: list[Any], limit: int = 6) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks[:limit], 1):
            if not isinstance(chunk, dict):
                continue
            text = " ".join(str(chunk.get("text") or "").split())
            previews.append(
                {
                    "rank": index,
                    "retrievalRank": chunk.get("retrieval_rank"),
                    "source": chunk.get("source"),
                    "url": chunk.get("url"),
                    "sciName": chunk.get("sci_name"),
                    "commonName": chunk.get("common_name"),
                    "score": chunk.get("score"),
                    "semanticScore": chunk.get("semantic_score"),
                    "lexicalScore": chunk.get("lexical_score"),
                    "rerankScore": chunk.get("rerank_score"),
                    "rerankBoost": chunk.get("rerank_boost"),
                    "textPreview": text[:500],
                }
            )
        return previews

    def _preview_evidence(
        self, evidence: list[Any], limit: int = 8
    ) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        for index, item in enumerate(evidence[:limit], 1):
            if not isinstance(item, dict):
                continue
            previews.append(
                {
                    "rank": index,
                    "claimType": item.get("claim_type"),
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "chunkId": item.get("chunk_id"),
                    "score": item.get("score"),
                    "textPreview": str(item.get("text_preview") or "")[:320],
                }
            )
        return previews

    def _is_greeting(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        exact_greetings = {"chao", "xin chao", "hello", "hi", "hey"}
        if normalized in exact_greetings:
            return True
        help_signals = [
            "ban co the giup gi",
            "ban giup duoc gi",
            "ban lam duoc gi",
            "huong dan su dung",
            "cach dung",
            "cach su dung",
            "chatbot lam duoc gi",
        ]
        if any(signal in normalized for signal in help_signals):
            return True
        starts_with_greeting = normalized.startswith("xin chao") or normalized in {
            "hello",
            "hi",
            "hey",
        }
        return starts_with_greeting and any(signal in normalized for signal in help_signals)

    def _basic_debug(self, flow: str, question: str) -> dict[str, Any]:
        return {
            "flow": flow,
            "questionPlan": self._analyze_question(question),
            "sources": [],
            "chunks": [],
            "evidence": [],
            "fallback": False,
            "dataWarnings": [],
            "sourceQuality": [],
            "retrievalWarnings": [],
            "coverageWarnings": [],
            "timingsMs": {},
            "errors": [],
        }

    def _multi_species_debug(
        self, flow: str, question: str, entities: list[dict[str, Any]]
    ) -> dict[str, Any]:
        debug = self._basic_debug(flow, question)
        debug["entities"] = [
            {
                "label": entity.get("label"),
                "status": entity.get("status"),
                "displayName": entity.get("display_name"),
                "scientificName": (
                    (entity.get("doc") or {}).get("scientific_name")
                    if isinstance(entity.get("doc"), dict)
                    else None
                ),
                "candidates": entity.get("candidates") or [],
            }
            for entity in entities
        ]
        debug["sources"] = ["MongoDB species metadata"]
        return debug

    def _is_many_species_query(self, normalized: str) -> bool:
        signals = [
            "cac loai",
            "nhung loai",
            "liet ke",
            "danh sach",
            "top",
            "loai nao",
            "nhung con nao",
            "cac con nao",
        ]
        return any(signal in normalized for signal in signals)

    def _is_context_multi_species_question(self, normalized: str) -> bool:
        signals = [
            "trong cac loai nay",
            "cac loai nay",
            "nhung loai nay",
            "trong nhom nay",
            "trong cac con nay",
        ]
        return any(signal in normalized for signal in signals)

    def _extract_comparison_labels(self, question: str) -> list[str]:
        text = re.sub(r"\s+", " ", question or "").strip()
        if not text:
            return []
        match = re.search(
            r"(?:so\s*sánh|so\s*sanh)\s+(.+?)(?:\s+(?:về|ve|theo|giữa|giua)\s+|[.?]|$)",
            text,
            flags=re.I,
        )
        if not match:
            return []
        raw_entities = match.group(1).strip()
        parts = re.split(r"\s+(?:và|va|với|voi)\s+|[,/;]+", raw_entities, flags=re.I)
        labels: list[str] = []
        for part in parts:
            label = part.strip(" .,:;!?")
            if label and label.lower() not in {"va", "và", "voi", "với"}:
                labels.append(label)
        return labels

    def _is_clear_command(self, normalized: str) -> bool:
        clear_signals = [
            "xoa loai",
            "xoa ngu canh",
            "xoa context",
            "reset loai",
            "bo loai hien tai",
            "cho minh hoi loai khac",
            "hoi loai khac",
            "chuyen loai",
            "doi loai",
        ]
        return any(signal in normalized for signal in clear_signals)

    def _is_control_help_question(self, normalized: str) -> bool:
        help_signals = [
            "gui anh khac",
            "anh khac",
            "nhan dien lai",
            "tai anh moi",
            "chon anh moi",
            "doi anh",
        ]
        return any(signal in normalized for signal in help_signals)

    def _analyze_question(self, question: str) -> dict:
        normalized = self._normalize_text(question)
        keyword_map = {
            "name": [
                "ten gi",
                "ten cua loai nay",
                "goi la gi",
            ],
            "scientific_name": [
                "ten khoa hoc",
                "scientific name",
                "danh phap",
            ],
            "taxonomy": [
                "thuoc ho nao",
                "thuoc ho",
                "family",
                "phan loai",
            ],
            "group": [
                "thuoc nhom",
                "nhom chim",
                "nhom thu",
                "bo sat",
                "luong cu",
                "ca dung khong",
            ],
            "occurrence": [
                "co o viet nam",
                "co tai viet nam",
                "o viet nam khong",
            ],
            "distribution": [
                "song o dau",
                "phan bo",
                "o dau",
                "vung nao",
                "tinh nao",
                "tai viet nam",
                "tay nguyen",
                "bac bo",
                "trung bo",
                "nam bo",
            ],
            "diet": ["an gi", "thuc an", "che do an", "san moi", "con moi"],
            "habitat": [
                "moi truong song",
                "sinh canh",
                "noi song",
                "kieu moi truong",
                "rung ngap man",
                "dat ngap nuoc",
                "rung nhiet doi",
                "dong co",
                "vung nui",
            ],
            "altitude": [
                "do cao",
                "bao nhieu met",
                "cao bao nhieu",
            ],
            "activity_time": [
                "ban ngay",
                "ban dem",
                "hoat dong luc nao",
            ],
            "conservation": [
                "bao ton",
                "iucn",
                "sach do",
                "nguy cap",
                "cites",
                "tuyet chung",
            ],
            "threats": [
                "de doa",
                "bi de doa",
                "nguy co",
            ],
            "population_trend": [
                "xu huong quan the",
                "tang hay giam",
                "quan the",
            ],
            "safety": [
                "nguy hiem",
                "co doc",
                "gap loai nay",
                "ngoai tu nhien",
                "bi thuong",
                "mac bay",
                "cuu ho",
                "cap cuu",
                "thu cung",
                "nuoi",
            ],
            "legal": [
                "buon ban",
                "mua ban",
                "trao doi",
                "van chuyen",
                "giay phep",
                "hop phap",
                "phap ly",
                "duoc phep",
            ],
            "source": [
                "nguon nao",
                "nguon thong tin",
                "link nguon",
                "lay tu dau",
                "lay tu dau",
                "trich dan",
                "bang chung",
                "tham khao",
                "source",
                "citation",
            ],
            "data_quality": [
                "chac chan nhat",
                "con thieu",
                "chua ro",
                "du lieu",
                "phan nao",
            ],
            "behavior": [
                "tap tinh",
                "hanh vi",
                "sinh san",
                "hoat dong",
                "dac diem",
                "hinh dang",
                "ke thu",
                "mua nao",
                "moi lua",
                "de bao nhieu",
                "tuoi tho",
                "phan biet",
                "nhan biet",
                "con duc",
                "con cai",
                "di cu",
                "tieng keu",
            ],
        }

        matches: list[tuple[int, str]] = []
        for intent, keywords in keyword_map.items():
            positions = [
                normalized.find(keyword)
                for keyword in keywords
                if normalized.find(keyword) >= 0
            ]
            if positions:
                matches.append((min(positions), intent))

        intents: list[str] = []
        for _, intent in sorted(matches, key=lambda item: item[0]):
            if intent not in intents:
                intents.append(intent)

        if not intents:
            intents = ["general"]

        forbidden = [
            item
            for item in ["conservation", "threats", "taxonomy_detail", "behavior", "source"]
            if item not in intents
        ]
        return {
            "species_required": True,
            "intents": [
                {"name": intent, "user_question": question} for intent in intents
            ],
            "forbidden_sections": forbidden,
            "answer_style": "focused" if intents != ["general"] else "general",
        }

    def _normalize_text(self, text: str) -> str:
        import unicodedata

        normalized = (text or "").replace("đ", "d").replace("Đ", "D")
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = "".join(
            ch for ch in normalized if not unicodedata.combining(ch)
        )
        normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        return normalized
