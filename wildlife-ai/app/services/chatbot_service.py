from __future__ import annotations

import re

from app.models.schemas import (
    ChatQueryRequest,
    ChatQueryResponse,
    SpeciesCandidateResponse,
)
from app.core.config import settings
from app.services.image_recognition_service import ImageRecognitionService
from app.services.rag_pipeline_service import OUT_OF_SCOPE_MESSAGE, RagPipelineService
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
        state = self.sessions.setdefault(req.sessionId, ChatSessionState())
        has_image = bool(req.imageUrl and req.imageUrl.strip())
        has_question = bool(req.question and req.question.strip())

        if not has_image and not has_question:
            raise ValueError("Request must contain question or imageUrl")

        if has_image:
            return self._handle_image_flow(req, state, has_question)

        return self._handle_text_flow(req.question or "", state)

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
            answer = self._answer_with_context(state.pending_question, species)
            state.pending_question = None
            return ChatQueryResponse(
                status="ANSWERED",
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
        self, question: str, state: ChatSessionState
    ) -> ChatQueryResponse:
        if self._is_greeting(question):
            return ChatQueryResponse(
                status="ANSWERED",
                message="Đã gửi hướng dẫn sử dụng.",
                answer=GREETING_MESSAGE,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )

        mentioned = self.species_service.find_species_mentioned(question)
        active_species = None

        if mentioned:
            active_species = mentioned
            state.current_species_id = str(mentioned.get("_id"))
            state.current_species_name = mentioned.get(
                "common_name_vi"
            ) or mentioned.get("scientific_name")
            message = f"Tôi đang trả lời theo loài {state.current_species_name}."
        elif state.current_species_id:
            active_species = self.species_service.get_species_doc(
                state.current_species_id
            )
            state.current_species_name = active_species.get(
                "common_name_vi"
            ) or active_species.get("scientific_name")
            message = f"Tôi đang trả lời theo loài {state.current_species_name}."
        else:
            return ChatQueryResponse(
                status="NEED_SPECIES_CONTEXT",
                message=NO_SPECIES_CONTEXT_MESSAGE,
                answer=NO_SPECIES_CONTEXT_MESSAGE,
                activeSpeciesId=None,
                activeSpeciesName=None,
                candidates=[],
            )

        answer = self._answer_with_context(question, active_species)

        return ChatQueryResponse(
            status="ANSWERED",
            message=message,
            answer=answer,
            activeSpeciesId=state.current_species_id,
            activeSpeciesName=state.current_species_name,
            candidates=[],
        )

    def _answer_with_context(self, question: str, species: dict | None) -> str:
        scientific_name = ""
        if species:
            scientific_name = str(species.get("scientific_name") or "")
        # Detect intent keywords and add an explicit focus hint to the question
        q = (question or "").strip()
        normalized = q.lower()

        # Check if there are multiple questions (more than one "?")
        question_count = q.count("?")
        has_multiple_questions = question_count > 1

        focus = None
        if not has_multiple_questions:  # Only apply focus if single question
            if any(k in normalized for k in ["ăn gì", "ăn", "thức ăn", "chế độ ăn"]):
                focus = "diet"
            elif any(
                k in normalized
                for k in ["sống ở đâu", "sinh cảnh", "môi trường", "phân bố", "ở đâu"]
            ):
                focus = "habitat"
            elif any(
                k in normalized for k in ["bảo tồn", "iucn", "sách đỏ", "nguy cấp"]
            ):
                focus = "conservation"
            elif any(
                k in normalized
                for k in [
                    "tập tính",
                    "hành vi",
                    "hành vi",
                    "behavior",
                    "đặc điểm",
                    "hình dáng",
                ]
            ):
                focus = "behavior"

        if focus:
            focused_question = f"[FOCUS:{focus}] {q}"
        else:
            focused_question = q

        raw = self.rag_service.answer(focused_question, scientific_name)

        # Post-process to return only the focused section when possible
        # (only if single question and focus detected)
        if focus and not has_multiple_questions and isinstance(raw, str):
            # split into paragraphs and look for keywords related to focus
            paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
            keywords_map = {
                "diet": ["ăn ", "thức ăn", "chế độ ăn", "ăn gì", "diet"],
                "habitat": ["sinh cảnh", "môi trường", "phân bố", "độ cao", "habitat"],
                "conservation": ["iucn", "sách đỏ", "bảo tồn", "cites", "nguy cấp"],
                "behavior": ["tập tính", "hành vi", "behavior", "thói quen"],
            }
            kws = keywords_map.get(focus, [])
            for p in paras:
                low = p.lower()
                if any(k in low for k in kws):
                    return p

            # fallback: extract sentences containing keywords
            import re as _re

            sentences = _re.split(r"(?<=[\.\!\?])\s+", raw)
            found = [s.strip() for s in sentences if any(k in s.lower() for k in kws)]
            if found:
                return " ".join(found[:2])

        return raw

    def _is_greeting(self, question: str) -> bool:
        normalized = (question or "").strip().lower()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized in {
            "chào",
            "chao",
            "xin chào",
            "xin chao",
            "hello",
            "hi",
            "hey",
        }
