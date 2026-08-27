from __future__ import annotations

import re
from typing import Any

from app.models.schemas import (
    ChatQueryRequest,
    ChatQueryResponse,
    SpeciesCandidateResponse,
)
from app.core.config import settings
from app.services.conversation_context_resolver import (
    ContextResolution,
    ConversationContextResolver,
)
from app.services.chatbot_router import HybridQuestionRouter
from app.services.image_recognition_service import ImageRecognitionService
from app.services.rag_pipeline_service import RagPipelineService
from app.services.session_store import (
    ChatSessionState,
    ConversationTurn,
    InMemoryChatSessionStore,
    SessionLockManager,
)
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
        self.context_resolver = ConversationContextResolver()
        self.question_router = HybridQuestionRouter()
        self.session_store = InMemoryChatSessionStore(
            ttl_seconds=settings.chat_session_ttl_seconds
        )
        self.session_locks = SessionLockManager()

    def query(self, req: ChatQueryRequest) -> ChatQueryResponse:
        with self.session_locks.lock(req.sessionId):
            state = self.session_store.get(req.sessionId)
            response, _ = self._query_internal(req, state, include_debug=False)
            self.session_store.save(req.sessionId, state)
            return response

    def query_debug(self, req: ChatQueryRequest) -> dict[str, Any]:
        with self.session_locks.lock(req.sessionId):
            state = self.session_store.get(req.sessionId)
            response, debug = self._query_internal(req, state, include_debug=True)
            self.session_store.save(req.sessionId, state)
            data = response.model_dump()
            data["debug"] = debug or {}
            return data

    def _query_internal(
        self,
        req: ChatQueryRequest,
        state: ChatSessionState,
        include_debug: bool = False,
    ) -> tuple[ChatQueryResponse, dict[str, Any] | None]:
        has_image = bool(req.imageUrl and req.imageUrl.strip())
        has_question = bool(req.question and req.question.strip())

        if not has_image and not has_question:
            raise ValueError("Request must contain question or imageUrl")

        if has_image and has_question and self._should_route_image_question_to_text(
            req.question or ""
        ):
            return self._handle_text_flow(req.question or "", state, include_debug)

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
        health = self.rag_service.health(load=load)
        health.update(
            {
                "preloadRagOnStartup": settings.preload_rag_on_startup,
                "preloadVisionOnStartup": settings.preload_vision_on_startup,
                "startupFailFast": settings.startup_fail_fast,
                "visionLoaded": self.image_recognition.is_ready,
                "sessionStore": "memory",
                "sessionsResetOnRestart": True,
            }
        )
        return health

    def preload_runtime(self) -> dict[str, Any]:
        errors: list[str] = []
        rag_health: dict[str, Any] | None = None
        vision_loaded = self.image_recognition.is_ready

        if settings.preload_rag_on_startup:
            rag_health = self.rag_service.health(load=True)
            if not rag_health.get("loaded"):
                errors.append(str(rag_health.get("loadError") or "RAG preload failed"))

        if settings.preload_vision_on_startup:
            try:
                self.image_recognition.preload()
                vision_loaded = True
            except Exception as exc:
                errors.append(f"BioCLIP preload failed: {type(exc).__name__}: {exc}")

        result = {
            "rag": rag_health or self.rag_service.health(load=False),
            "visionLoaded": vision_loaded,
            "errors": errors,
        }
        if errors and settings.startup_fail_fast:
            raise RuntimeError("; ".join(errors))
        return result

    def confirm_species(self, session_id: str, species_id: str) -> ChatQueryResponse:
        with self.session_locks.lock(session_id):
            state = self.session_store.get(session_id)
            species = self.species_service.get_species_doc(species_id)

            if state.pending_action == "comparison":
                allowed_ids = {item.speciesId for item in state.pending_candidates}
                if allowed_ids and species_id not in allowed_ids:
                    raise ValueError("Species is not one of the pending candidates")
                index = state.pending_entity_index
                if index is None or index >= len(state.pending_entities):
                    raise ValueError("Comparison confirmation context is no longer valid")
                entity = state.pending_entities[index]
                entity.update(
                    {
                        "status": "matched",
                        "doc": species,
                        "display_name": self.species_service.display_species_name(
                            species
                        ),
                        "candidate_docs": [],
                    }
                )
                next_index = self._next_pending_entity_index(state.pending_entities)
                if next_index is not None:
                    state.pending_entity_index = next_index
                    candidates = self._candidate_responses(
                        state.pending_entities[next_index].get("candidate_docs") or []
                    )
                    state.pending_candidates = candidates
                    response = ChatQueryResponse(
                        status="NEED_SPECIES_CONFIRM",
                        message=f"Vui lòng xác nhận loài cho tên '{state.pending_entities[next_index].get('label')}'.",
                        activeSpeciesId=None,
                        activeSpeciesName=None,
                        candidates=candidates,
                    )
                    self.session_store.save(session_id, state)
                    return response

                question = state.pending_question or ""
                entities = list(state.pending_entities)
                self._clear_pending(state)
                answer, debug = self._answer_comparison(question, entities)
                intents = self._intent_names(self._analyze_question(question))
                self._set_comparison_focus(state, entities)
                self._record_turn(state, question, question, intents, entities, answer, debug)
                response = ChatQueryResponse(
                    status="ANSWERED",
                    message="Đã xác nhận các loài và hoàn tất so sánh.",
                    answer=answer,
                    activeSpeciesId=None,
                    activeSpeciesName=None,
                    candidates=[],
                )
                self.session_store.save(session_id, state)
                return response

            self._set_single_focus(state, species)
            state.awaiting_confirmation = False
            state.pending_candidates = []
            state.pending_action = None

            current_label = (
                state.current_species_name
                or species.get("scientific_name")
                or "loài này"
            )
            updated_message = f"Loài đang được hỏi là {current_label}."

            if state.pending_question:
                pending_question = state.pending_question
                answer, answer_status, _ = self._answer_with_context(
                    pending_question, species
                )
                state.pending_question = None
                if answer_status == "ANSWERED":
                    intents = self._intent_names(
                        self._analyze_question(pending_question)
                    )
                    self._record_turn(
                        state,
                        pending_question,
                        pending_question,
                        intents,
                        state.focused_entities,
                        answer,
                        None,
                    )
                response = ChatQueryResponse(
                    status=answer_status,
                    message=f"{updated_message} Tôi cũng đã trả lời câu hỏi của bạn.",
                    answer=answer,
                    activeSpeciesId=state.current_species_id,
                    activeSpeciesName=state.current_species_name,
                    candidates=[],
                )
                self.session_store.save(session_id, state)
                return response

            response = ChatQueryResponse(
                status="SPECIES_CONFIRMED",
                message=updated_message,
                activeSpeciesId=state.current_species_id,
                activeSpeciesName=state.current_species_name,
                candidates=[],
            )
            self.session_store.save(session_id, state)
            return response

    def clear_species(self, session_id: str) -> ChatQueryResponse:
        with self.session_locks.lock(session_id):
            state = self.session_store.get(session_id)
            previous_name = state.current_species_name
            self._reset_conversation_state(state)
            response = ChatQueryResponse(
                status="CLEARED",
                message=(
                    f"Đã xóa ngữ cảnh loài đang chọn ({previous_name}). Bạn có thể hỏi chung hoặc gửi ảnh mới."
                    if previous_name
                    else "Đã xóa ngữ cảnh loài đang chọn. Bạn có thể hỏi chung hoặc gửi ảnh mới."
                ),
                candidates=[],
            )
            self.session_store.save(session_id, state)
            return response

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
        state.pending_action = "image"

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
        original_question = (question or "").strip()
        normalized = self._normalize_text(original_question)

        if self._is_greeting(original_question):
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
            self._reset_conversation_state(state)
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
            debug = self._basic_debug("control_clear", original_question)
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
            debug = self._basic_debug("control_help", original_question)
            return response, debug if include_debug else None

        resolution = self._resume_context_clarification(original_question, state)
        if resolution is None:
            resolution = self._resolve_explicit_entity_follow_up(
                original_question, state
            )
        if resolution is None:
            resolution = self._resolve_explicit_entity_correction(
                original_question, state
            )
        if resolution is None:
            explicit_mentions = self.species_service.find_species_mentions(
                original_question
            )
            if explicit_mentions and not self._question_needs_focused_context(
                original_question
            ):
                resolution = ContextResolution(
                    original_question=original_question,
                    resolved_question=original_question,
                    resolver="explicit_species",
                    resolved_entities=[
                        str(
                            doc.get("common_name_vi")
                            or doc.get("scientific_name")
                            or ""
                        )
                        for doc in explicit_mentions
                    ],
                )
            else:
                resolution = self.context_resolver.resolve(original_question, state)
        if resolution.needs_clarification:
            state.pending_clarification_question = original_question
            state.pending_clarification_entities = list(state.focused_entities)
            response = ChatQueryResponse(
                status="NEED_CLARIFICATION",
                message=resolution.clarification_message or "Bạn có thể nói rõ loài đang được hỏi không?",
                answer=resolution.clarification_message,
                activeSpeciesId=self._active_species_id(state),
                activeSpeciesName=self._active_species_name(state),
                candidates=[],
            )
            debug = self._context_debug(
                self._basic_debug("need_clarification", original_question), resolution, state
            )
            return response, debug if include_debug else None

        resolved_question = resolution.resolved_question
        mentioned_docs = self.species_service.find_species_mentions(resolved_question)
        plan = self._analyze_question(
            resolved_question,
            state=state,
            mentioned_docs=mentioned_docs,
        )
        intents = self._intent_names(plan)
        comparison_labels = self._extract_comparison_labels(resolved_question)
        comparison_requested = len(mentioned_docs) >= 2 or len(comparison_labels) >= 2

        if comparison_requested:
            if len(mentioned_docs) > 4 or len(comparison_labels) > 4:
                message = "Bạn hãy chọn tối đa 4 loài cho mỗi lần so sánh."
                response = ChatQueryResponse(
                    status="NEED_CLARIFICATION",
                    message=message,
                    answer=message,
                    activeSpeciesId=self._active_species_id(state),
                    activeSpeciesName=self._active_species_name(state),
                    candidates=[],
                )
                debug = self._context_debug(
                    self._basic_debug("comparison_too_many_entities", resolved_question),
                    resolution,
                    state,
                )
                return response, debug if include_debug else None

            if len(mentioned_docs) >= 2:
                entities = [self._entity_from_doc(doc) for doc in mentioned_docs]
            else:
                entities = self.species_service.resolve_named_entities(
                    comparison_labels
                )

            unresolved_without_candidates = [
                entity
                for entity in entities
                if not entity.get("doc") and not entity.get("candidate_docs")
            ]
            if unresolved_without_candidates:
                labels = ", ".join(
                    str(entity.get("label") or "loài chưa rõ")
                    for entity in unresolved_without_candidates
                )
                message = f"Tôi chưa tìm thấy loài phù hợp cho: {labels}. Bạn hãy nhập tên Việt hoặc tên khoa học đầy đủ."
                response = ChatQueryResponse(
                    status="NEED_CLARIFICATION",
                    message=message,
                    answer=message,
                    activeSpeciesId=self._active_species_id(state),
                    activeSpeciesName=self._active_species_name(state),
                    candidates=[],
                )
                debug = self._context_debug(
                    self._multi_species_debug(
                        "comparison_unresolved", resolved_question, entities
                    ),
                    resolution,
                    state,
                )
                return response, debug if include_debug else None

            pending_index = self._next_pending_entity_index(entities)
            if pending_index is not None:
                candidates = self._candidate_responses(
                    entities[pending_index].get("candidate_docs") or []
                )
                state.awaiting_confirmation = True
                state.pending_action = "comparison"
                state.pending_question = resolved_question
                state.pending_entities = entities
                state.pending_entity_index = pending_index
                state.pending_candidates = candidates
                message = f"Vui lòng xác nhận loài cho tên '{entities[pending_index].get('label')}'."
                response = ChatQueryResponse(
                    status="NEED_SPECIES_CONFIRM",
                    message=message,
                    answer=message,
                    activeSpeciesId=None,
                    activeSpeciesName=None,
                    candidates=candidates,
                )
                debug = self._context_debug(
                    self._multi_species_debug(
                        "comparison_needs_confirmation", resolved_question, entities
                    ),
                    resolution,
                    state,
                )
                return response, debug if include_debug else None

            answer, comparison_debug = self._answer_comparison(
                resolved_question, entities, question_plan=plan
            )
            self._set_comparison_focus(state, entities)
            self._record_turn(
                state,
                original_question,
                resolved_question,
                intents,
                entities,
                answer,
                comparison_debug,
            )
            response = ChatQueryResponse(
                status="ANSWERED",
                message="Tôi đang so sánh các loài được nêu trong câu hỏi.",
                answer=answer,
                activeSpeciesId=None,
                activeSpeciesName=None,
                candidates=[],
            )
            debug = self._context_debug(
                self._multi_species_debug(
                    "multi_species_structured", resolved_question, entities
                ),
                resolution,
                state,
            )
            if comparison_debug:
                debug.update(comparison_debug)
            return response, debug if include_debug else None

        mentioned = mentioned_docs[0] if mentioned_docs else None
        active_species = None
        message = ""

        if mentioned:
            active_species = mentioned
            display_name = mentioned.get("common_name_vi") or mentioned.get(
                "scientific_name"
            )
            message = f"Tôi đang trả lời theo loài {display_name}."
        elif self._is_many_species_query(self._normalize_text(resolved_question)):
            general_answer = self.species_service.answer_general_query(resolved_question)
            if general_answer:
                self._record_turn(
                    state,
                    original_question,
                    resolved_question,
                    intents,
                    [],
                    general_answer,
                    None,
                )
                response = ChatQueryResponse(
                    status="ANSWERED",
                    message="Tôi đang trả lời câu hỏi tổng quát từ metadata loài.",
                    answer=general_answer,
                    activeSpeciesId=self._active_species_id(state),
                    activeSpeciesName=self._active_species_name(state),
                    candidates=[],
                )
                debug = {
                    "flow": "general_metadata",
                    "questionPlan": plan,
                    "routerPlan": plan.get("router_plan") or {},
                    "routerTrace": plan.get("router_trace") or [],
                    "semanticScores": plan.get("semantic_scores") or [],
                    "llmRouterUsed": bool(plan.get("llm_router_used")),
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
                debug = self._context_debug(debug, resolution, state)
                return response, debug if include_debug else None

        if not active_species and state.focus_mode == "single" and state.current_species_id:
            active_species = self.species_service.get_species_doc(state.current_species_id)
            display_name = active_species.get("common_name_vi") or active_species.get(
                "scientific_name"
            )
            message = f"Tôi đang trả lời theo loài {display_name}."

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
                "questionPlan": plan,
                "routerPlan": plan.get("router_plan") or {},
                "routerTrace": plan.get("router_trace") or [],
                "semanticScores": plan.get("semantic_scores") or [],
                "llmRouterUsed": bool(plan.get("llm_router_used")),
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
            debug = self._context_debug(debug, resolution, state)
            return response, debug if include_debug else None

        answer, answer_status, debug = self._answer_with_context(
            resolved_question,
            active_species,
            include_debug=include_debug,
            question_plan=plan,
        )

        if answer_status == "ANSWERED":
            self._set_single_focus(state, active_species)
            self._record_turn(
                state,
                original_question,
                resolved_question,
                intents,
                state.focused_entities,
                answer,
                debug,
            )

        response = ChatQueryResponse(
            status=answer_status,
            message=message,
            answer=answer,
            activeSpeciesId=self._active_species_id(state),
            activeSpeciesName=self._active_species_name(state),
            candidates=[],
        )
        debug = self._context_debug(
            debug or self._basic_debug("rag", resolved_question), resolution, state
        )
        return response, debug if include_debug else None

    def _answer_with_context(
        self,
        question: str,
        species: dict | None,
        include_debug: bool = False,
        question_plan: dict[str, Any] | None = None,
    ) -> tuple[str, str, dict[str, Any] | None]:
        scientific_name = ""
        if species:
            scientific_name = str(species.get("scientific_name") or "")
        q = (question or "").strip()
        question_plan = question_plan or self._analyze_question(q)
        result = self.rag_service.answer_result(
            q, scientific_name, question_plan=question_plan
        )
        answer = result.answer
        if "reproduction" in self._intent_names(question_plan):
            answer = self._sanitize_reproduction_answer(answer)
        answer = self._append_source_catalog(
            answer,
            result.raw,
            force="reproduction" in self._intent_names(question_plan),
        )
        debug = (
            self._build_rag_debug(result.raw, question_plan, result.error)
            if include_debug
            else None
        )
        return answer, result.status, debug

    def _answer_comparison(
        self,
        question: str,
        entities: list[dict[str, Any]],
        question_plan: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        plan = question_plan or self._analyze_question(question)
        intents = self._intent_names(plan)
        overrides: dict[str, dict[str, str]] = {}
        evidence: list[dict[str, Any]] = []
        errors: list[str] = []

        if "reproduction" in intents:
            for entity in entities:
                doc = entity.get("doc") or {}
                scientific_name = str(doc.get("scientific_name") or "").strip()
                if not scientific_name:
                    continue
                reproduction_plan = {
                    "species_required": True,
                    "intents": [
                        {"name": "reproduction", "user_question": question}
                    ],
                    "forbidden_sections": [
                        "conservation",
                        "threats",
                        "taxonomy_detail",
                        "source",
                    ],
                    "answer_style": "focused",
                }
                result = self.rag_service.answer_result(
                    f"Trả lời về sinh sản của {scientific_name}. {question}",
                    scientific_name,
                    question_plan=reproduction_plan,
                )
                if result.status == "ANSWERED":
                    overrides.setdefault(str(doc.get("_id")), {})[
                        "reproduction"
                    ] = self._compact_comparison_cell(
                        self._sanitize_reproduction_answer(result.answer)
                    )
                    raw = result.raw or {}
                    evidence.extend(raw.get("evidence") or [])
                else:
                    overrides.setdefault(str(doc.get("_id")), {})[
                        "reproduction"
                    ] = "Không thể tổng hợp thông tin sinh sản lúc này."
                    if result.error:
                        errors.append(result.error)

        answer = self.species_service.answer_multi_species_comparison(
            question,
            entities,
            intents=intents,
            fact_overrides=overrides,
        )
        return answer, {
            "questionPlan": plan,
            "evidence": self._preview_evidence(evidence),
            "errors": errors,
        }

    def _compact_comparison_cell(self, answer: str, limit: int = 700) -> str:
        text = re.sub(r"[#*_`]+", "", answer or "")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit] + ("..." if len(text) > limit else "")

    def _sanitize_reproduction_answer(self, answer: str) -> str:
        lines = []
        for line in (answer or "").splitlines():
            normalized = self._normalize_text(line)
            if normalized.startswith("do chac chan") or normalized.startswith(
                "muc do chac chan"
            ):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _append_source_catalog(
        self,
        answer: str,
        raw: dict[str, Any] | None,
        force: bool = False,
    ) -> str:
        if not answer or "**Nguồn tham khảo**" in answer:
            return answer
        if not force and not re.search(r"[\[(]Nguồn\s+\d+", answer, re.IGNORECASE):
            return answer

        chunks = (raw or {}).get("chunks") or []
        lines: list[str] = []
        for index, chunk in enumerate(chunks, 1):
            if not isinstance(chunk, dict):
                continue
            source = self._display_source_label(str(chunk.get("source") or "Nguồn truy xuất"))
            species = str(
                chunk.get("sci_name") or chunk.get("common_name") or ""
            ).strip()
            url = str(chunk.get("url") or "").strip()
            detail = f" - {species}" if species else ""
            if re.match(r"^https?://", url, re.IGNORECASE):
                lines.append(
                    f"{index}. **Nguồn {index} - {source}**{detail}: [Mở nguồn]({url})"
                )
            else:
                lines.append(f"{index}. **Nguồn {index} - {source}**{detail}")

        if not lines:
            return answer
        return f"{answer.rstrip()}\n\n**Nguồn tham khảo**\n" + "\n".join(lines)

    def _display_source_label(self, source: str) -> str:
        normalized = self._normalize_text(source)
        aliases = {
            "iucn": "IUCN Red List",
            "iucn red list": "IUCN Red List",
            "birdlife datazone": "BirdLife DataZone",
            "birdlife": "BirdLife DataZone",
            "cites": "CITES",
            "cites gaur gallery": "CITES - Gaur species gallery",
            "gbif": "GBIF",
            "wikidata": "Wikidata",
            "wikipedia vi": "Wikipedia tiếng Việt",
            "wikipedia en": "Wikipedia tiếng Anh",
            "inaturalist observations": "iNaturalist",
            "inaturalist": "iNaturalist",
        }
        if normalized in aliases:
            return aliases[normalized]
        return re.sub(r"[_-]+", " ", source).strip() or "Nguồn truy xuất"

    def _resume_context_clarification(
        self, question: str, state: ChatSessionState
    ) -> ContextResolution | None:
        pending_question = state.pending_clarification_question
        pending_entities = state.pending_clarification_entities
        if not pending_question or not pending_entities:
            return None

        selected_doc = self._select_pending_entity(question, pending_entities)
        if not selected_doc:
            # A full new question cancels the clarification; a short reply leaves it pending.
            if len(self._normalize_text(question).split()) > 8:
                self._clear_context_clarification(state)
            return None

        selected_name = str(
            selected_doc.get("common_name_vi")
            or selected_doc.get("scientific_name")
            or "loài đã chọn"
        )
        current_plan = self._analyze_question(question)
        current_intents = self._intent_names(current_plan)
        selection_only = current_intents == ["general"] or self._is_entity_correction(
            self._normalize_text(question)
        )
        base_question = pending_question if selection_only else question
        resolved_question = re.sub(
            r"loài\s+này|loai\s+nay|loài\s+kia|loai\s+kia|con\s+này|con\s+nay|\bnó\b|\bno\b",
            selected_name,
            base_question,
            flags=re.IGNORECASE,
        )
        if resolved_question == base_question and selection_only:
            pending_intents = self._intent_names(self._analyze_question(pending_question))
            topic = self._intent_topic(pending_intents)
            resolved_question = (
                f"{topic.capitalize()} của {selected_name} như thế nào?"
                if topic
                else f"Thông tin về {selected_name}."
            )

        self._clear_context_clarification(state)
        return ContextResolution(
            original_question=question,
            resolved_question=resolved_question,
            resolver="clarification_resume",
            is_follow_up=True,
            inherited_intents=list(state.last_intents),
            resolved_entities=[selected_name],
        )

    def _select_pending_entity(
        self, question: str, entities: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        docs = [entity.get("doc") or {} for entity in entities]
        allowed = {str(doc.get("_id")): doc for doc in docs if doc.get("_id")}
        mentions = self.species_service.find_species_mentions(question)
        matched = [doc for doc in mentions if str(doc.get("_id")) in allowed]
        if len(matched) == 1:
            return matched[0]

        normalized = self._normalize_text(question)
        if any(signal in normalized for signal in ["loai thu nhat", "loai dau tien"]):
            return docs[0] if docs else None
        if any(signal in normalized for signal in ["loai thu hai", "loai 2"]):
            return docs[1] if len(docs) > 1 else None
        return None

    def _resolve_explicit_entity_correction(
        self, question: str, state: ChatSessionState
    ) -> ContextResolution | None:
        normalized = self._normalize_text(question)
        if not self._is_entity_correction(normalized):
            return None
        mentions = self.species_service.find_species_mentions(question)
        if len(mentions) != 1:
            return None
        topic = self._intent_topic(state.last_intents)
        if not topic:
            return None
        name = str(
            mentions[0].get("common_name_vi")
            or mentions[0].get("scientific_name")
            or ""
        )
        return ContextResolution(
            original_question=question,
            resolved_question=f"{topic.capitalize()} của {name} như thế nào?",
            resolver="entity_correction",
            is_follow_up=True,
            inherited_intents=list(state.last_intents),
            resolved_entities=[name],
        )

    def _resolve_explicit_entity_follow_up(
        self, question: str, state: ChatSessionState
    ) -> ContextResolution | None:
        normalized = self._normalize_text(question)
        if not any(
            normalized.startswith(prefix)
            for prefix in ["con ", "the con ", "vay con "]
        ):
            return None
        if self._intent_names(self._analyze_question(question)) != ["general"]:
            return None

        mentions = self.species_service.find_species_mentions(question)
        if len(mentions) != 1:
            return None
        topic = self._intent_topic(state.last_intents)
        if not topic:
            return None
        name = str(
            mentions[0].get("common_name_vi")
            or mentions[0].get("scientific_name")
            or ""
        )
        return ContextResolution(
            original_question=question,
            resolved_question=f"{topic.capitalize()} của {name} như thế nào?",
            resolver="explicit_entity_follow_up",
            is_follow_up=True,
            inherited_intents=list(state.last_intents),
            resolved_entities=[name],
        )

    def _is_entity_correction(self, normalized: str) -> bool:
        return any(
            signal in normalized
            for signal in [
                "toi dang hoi ve",
                "toi hoi ve",
                "y toi la",
                "toi muon hoi",
            ]
        )

    def _intent_topic(self, intents: list[str]) -> str | None:
        labels = {
            "reproduction": "sinh sản",
            "diet": "thức ăn",
            "habitat": "sinh cảnh",
            "distribution": "phân bố",
            "conservation": "tình trạng bảo tồn",
            "threats": "các mối đe dọa",
            "identification": "đặc điểm nhận dạng",
            "behavior": "tập tính",
            "name": "tên loài",
            "taxonomy": "phân loại",
        }
        for intent in intents:
            if intent in labels:
                return labels[intent]
        return None

    def _clear_context_clarification(self, state: ChatSessionState) -> None:
        state.pending_clarification_question = None
        state.pending_clarification_entities = []

    def _entity_from_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "label": doc.get("common_name_vi") or doc.get("scientific_name"),
            "status": "matched",
            "doc": doc,
            "display_name": self.species_service.display_species_name(doc),
            "candidate_docs": [],
        }

    def _candidate_responses(
        self, docs: list[dict[str, Any]]
    ) -> list[SpeciesCandidateResponse]:
        responses: list[SpeciesCandidateResponse] = []
        for doc in docs[:6]:
            responses.append(
                SpeciesCandidateResponse(
                    speciesId=str(doc.get("_id")),
                    scientificName=doc.get("scientific_name"),
                    vietnameseName=doc.get("common_name_vi"),
                    heroImageUrl=self.species_service.resolve_hero_image(doc),
                    thumbnailUrl=self.species_service.resolve_thumbnail_image(doc),
                )
            )
        return responses

    def _next_pending_entity_index(
        self, entities: list[dict[str, Any]]
    ) -> int | None:
        for index, entity in enumerate(entities):
            if entity.get("doc"):
                continue
            if entity.get("candidate_docs"):
                return index
        return None

    def _set_single_focus(
        self, state: ChatSessionState, species: dict[str, Any]
    ) -> None:
        state.focus_mode = "single"
        state.current_species_id = str(species.get("_id"))
        state.current_species_name = species.get("common_name_vi") or species.get(
            "scientific_name"
        )
        state.focused_entities = [self._entity_from_doc(species)]

    def _set_comparison_focus(
        self, state: ChatSessionState, entities: list[dict[str, Any]]
    ) -> None:
        state.focus_mode = "comparison"
        state.focused_entities = list(entities)
        state.recent_multi_species_entities = list(entities)
        state.current_species_id = None
        state.current_species_name = None

    def _record_turn(
        self,
        state: ChatSessionState,
        question: str,
        resolved_question: str,
        intents: list[str],
        entities: list[dict[str, Any]],
        answer: str,
        debug: dict[str, Any] | None,
    ) -> None:
        entity_summaries = []
        for entity in entities:
            doc = entity.get("doc") or {}
            entity_summaries.append(
                {
                    "id": str(doc.get("_id") or ""),
                    "name": doc.get("common_name_vi") or doc.get("scientific_name"),
                }
            )
        evidence = (debug or {}).get("evidence") or []
        state.add_turn(
            ConversationTurn(
                question=question,
                resolved_question=resolved_question,
                intents=list(intents),
                entities=entity_summaries,
                answer=answer,
                evidence=list(evidence),
            ),
            limit=settings.chat_history_turn_limit,
        )

    def _clear_pending(self, state: ChatSessionState) -> None:
        state.pending_question = None
        state.awaiting_confirmation = False
        state.pending_candidates = []
        state.pending_action = None
        state.pending_entities = []
        state.pending_entity_index = None
        self._clear_context_clarification(state)

    def _reset_conversation_state(self, state: ChatSessionState) -> None:
        state.current_species_id = None
        state.current_species_name = None
        state.focus_mode = "none"
        state.focused_entities = []
        state.recent_multi_species_entities = []
        state.last_intents = []
        state.last_question = None
        state.last_answer = None
        state.last_evidence = []
        state.recent_turns = []
        self._clear_pending(state)

    def _active_species_id(self, state: ChatSessionState) -> str | None:
        return state.current_species_id if state.focus_mode == "single" else None

    def _active_species_name(self, state: ChatSessionState) -> str | None:
        return state.current_species_name if state.focus_mode == "single" else None

    def _intent_names(self, plan: dict[str, Any]) -> list[str]:
        return [
            str(item.get("name"))
            for item in plan.get("intents") or []
            if isinstance(item, dict) and item.get("name")
        ]

    def _context_debug(
        self,
        debug: dict[str, Any],
        resolution: ContextResolution,
        state: ChatSessionState | None = None,
    ) -> dict[str, Any]:
        debug.update(
            {
                "originalQuestion": resolution.original_question,
                "resolvedQuestion": resolution.resolved_question,
                "contextResolver": resolution.resolver,
                "isFollowUp": resolution.is_follow_up,
                "inheritedIntents": resolution.inherited_intents,
                "resolverEntities": resolution.resolved_entities,
                "resolverIntent": resolution.resolver_intent,
                "focusMode": state.focus_mode if state else None,
                "focusedEntities": [
                    {
                        "id": str((entity.get("doc") or {}).get("_id") or ""),
                        "name": (entity.get("doc") or {}).get("common_name_vi")
                        or (entity.get("doc") or {}).get("scientific_name"),
                    }
                    for entity in (state.focused_entities if state else [])
                ],
            }
        )
        return debug

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
            "routerPlan": question_plan.get("router_plan") or {},
            "routerTrace": question_plan.get("router_trace") or [],
            "semanticScores": question_plan.get("semantic_scores") or [],
            "llmRouterUsed": bool(question_plan.get("llm_router_used")),
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
        question_plan = self._analyze_question(question)
        return {
            "flow": flow,
            "questionPlan": question_plan,
            "routerPlan": question_plan.get("router_plan") or {},
            "routerTrace": question_plan.get("router_trace") or [],
            "semanticScores": question_plan.get("semantic_scores") or [],
            "llmRouterUsed": bool(question_plan.get("llm_router_used")),
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

    def _extract_comparison_labels(self, question: str) -> list[str]:
        text = re.sub(r"\s+", " ", question or "").strip()
        if not text:
            return []
        raw_entities = ""
        patterns = [
            r"(?:so\s*sánh|so\s*sanh)\s+(?:giữa|giua\s+)?(.+?)(?:\s+(?:về|ve|theo)\s+|[.?]|$)",
            r"(?:phân\s*biệt|phan\s*biet)\s+(.+?)(?:\s+(?:về|ve|theo)\s+|[.?]|$)",
            r"(?:sự\s+khác\s+nhau\s+giữa|su\s+khac\s+nhau\s+giua)\s+(.+?)(?:\s+(?:về|ve|theo)\s+|[.?]|$)",
            r"^(.+?\s+(?:và|va|với|voi)\s+.+?)\s+(?:khác\s+nhau|khac\s+nhau).*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                raw_entities = match.group(1).strip()
                break
        if not raw_entities:
            match = re.search(
                r"^(.+?)\s+(?:so\s+với|so\s+voi)\s+(.+?)(?:\s+thì\s+sao|\s+thi\s+sao|[.?]|$)",
                text,
                flags=re.I,
            )
            if match:
                raw_entities = f"{match.group(1)} và {match.group(2)}"
        if not raw_entities:
            return []
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

    def _should_route_image_question_to_text(self, question: str) -> bool:
        if not self.species_service.find_species_mentions(question):
            return False
        intents = self._intent_names(self._analyze_question(question))
        if any(intent not in {"general", "name"} for intent in intents):
            return True
        normalized = self._normalize_text(question)
        image_identity_signals = [
            "co phai",
            "dung la",
            "nhan dien",
            "xac dinh loai",
            "anh nay la",
            "hinh nay la",
            "trong anh la",
            "trong hinh la",
            "anh nay la gi",
            "hinh nay la gi",
            "trong anh la gi",
            "trong hinh la gi",
            "day la loai gi",
            "day la con gi",
            "con nay la gi",
            "loai nay la gi",
            "ten con nay",
            "ten loai nay",
        ]
        return not any(signal in normalized for signal in image_identity_signals)

    def _analyze_question(
        self,
        question: str,
        state: ChatSessionState | None = None,
        mentioned_docs: list[dict[str, Any]] | None = None,
    ) -> dict:
        mention_names = [
            str(doc.get("common_name_vi") or doc.get("scientific_name") or "")
            for doc in (mentioned_docs or [])
            if isinstance(doc, dict)
        ]
        router_plan = self.question_router.route(
            question,
            state=state,
            species_mentions=mention_names,
        )
        return router_plan.to_question_plan(question)

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

    def _question_needs_focused_context(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        context_markers = [
            "loai nay",
            "con nay",
            "loai kia",
            "loai con lai",
            "loai thu nhat",
            "loai thu hai",
            "con thu nhat",
            "con thu hai",
            "trong hai loai nay",
            "trong cac loai nay",
            "cac loai nay",
            "hai loai nay",
            "ca hai",
        ]
        return any(marker in normalized for marker in context_markers)
