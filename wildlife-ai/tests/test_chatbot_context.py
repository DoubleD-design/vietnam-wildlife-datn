from __future__ import annotations

import os
import sys
import time
import types
import unittest

os.environ["CEREBRAS_API_KEY"] = ""

fake_image_module = types.ModuleType("app.services.image_recognition_service")


class FakeImageRecognitionService:
    is_ready = False

    def predict(self, *_args, **_kwargs):
        return []


fake_image_module.ImageRecognitionService = FakeImageRecognitionService
sys.modules["app.services.image_recognition_service"] = fake_image_module

from app.services.chatbot_service import ChatbotService  # noqa: E402
from app.services.rag_pipeline_service import RagAnswerResult  # noqa: E402
from app.models.schemas import ChatQueryRequest  # noqa: E402
from app.services.session_store import (  # noqa: E402
    ChatSessionState,
    ConversationTurn,
    InMemoryChatSessionStore,
)
from app.services.species_service import SpeciesService  # noqa: E402


CONG_LUC = {
    "_id": "cong-luc",
    "scientific_name": "Pavo muticus",
    "common_name_vi": "Công lục",
    "common_name_en": "Green Peafowl",
    "search_keywords": ["cong luc", "green peafowl"],
    "taxonomy": {"class": "Aves", "order": "Galliformes", "family": "Phasianidae"},
    "distribution": {"vietnam": {"regions": ["Nam Bộ"]}},
    "ecology": {"habitat_tags": ["rừng"], "diet": ["hạt", "côn trùng"]},
    "conservation": {"iucn": {"category": "EN", "population_trend": "decreasing"}},
}

CA_SAU_XIEM = {
    "_id": "ca-sau-xiem",
    "scientific_name": "Crocodylus siamensis",
    "common_name_vi": "Cá sấu Xiêm",
    "common_name_en": "Siamese Crocodile",
    "search_keywords": ["ca sau xiem", "siamese crocodile"],
    "taxonomy": {"class": "Reptilia", "order": "Crocodylia", "family": "Crocodylidae"},
    "distribution": {"vietnam": {"regions": ["Nam Bộ"]}},
    "ecology": {"habitat_tags": ["đất ngập nước"], "diet": ["fish"]},
    "conservation": {"iucn": {"category": "CR", "population_trend": "decreasing"}},
}

BO_TOT = {
    "_id": "bo-tot",
    "scientific_name": "Bos gaurus",
    "common_name_vi": "Bò tót",
    "search_keywords": ["bo tot", "gaur"],
    "taxonomy": {"class": "Mammalia", "family": "Bovidae"},
    "ecology": {"habitat_tags": ["rừng"], "diet": ["cỏ"]},
    "conservation": {"iucn": {"category": "VU"}},
}


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, *_args, **_kwargs):
        return list(self.docs)

    def find_one(self, query, *_args, **_kwargs):
        target = query.get("_id") if isinstance(query, dict) else None
        for doc in self.docs:
            if str(doc.get("_id")) == str(target):
                return doc
        return None


class FakeRagService:
    def answer_result(self, question, species_scientific_name="", question_plan=None):
        intents = [item.get("name") for item in (question_plan or {}).get("intents", [])]
        if "reproduction" in intents:
            answer = (
                f"**Thông tin sinh sản:** {species_scientific_name} sinh sản theo dữ liệu tham khảo.\n\n"
                "**Căn cứ:** Dữ kiện sinh sản liên quan [Nguồn 1].\n\n"
                "**Lập luận:** Tổng hợp các dữ kiện trên."
            )
        else:
            answer = f"Trả lời cho {species_scientific_name}: {question}"
        return RagAnswerResult(
            status="ANSWERED",
            answer=answer,
            raw={
                "evidence": [],
                "chunks": [
                    {
                        "source": "birdlife_datazone",
                        "sci_name": species_scientific_name,
                        "url": "https://datazone.birdlife.org/species/factsheet/example",
                    }
                ],
            },
        )


class FakeCerebrasClient:
    def __init__(self, content):
        message = types.SimpleNamespace(content=content)
        choice = types.SimpleNamespace(message=message)
        response = types.SimpleNamespace(choices=[choice])
        completions = types.SimpleNamespace(create=lambda **_kwargs: response)
        self.chat = types.SimpleNamespace(completions=completions)


class FailingCerebrasClient:
    def __init__(self):
        def fail(**_kwargs):
            raise TimeoutError("simulated timeout")

        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=fail)
        )


def build_species_service():
    service = SpeciesService.__new__(SpeciesService)
    service.collection = FakeCollection([CONG_LUC, CA_SAU_XIEM, BO_TOT])
    return service


def build_chatbot():
    service = ChatbotService(build_species_service())
    service.rag_service = FakeRagService()
    service.context_resolver._client = None
    return service


class SessionStateTest(unittest.TestCase):
    def test_history_is_rolling_and_session_expires(self):
        state = ChatSessionState()
        for index in range(8):
            state.add_turn(
                ConversationTurn(
                    question=str(index),
                    resolved_question=str(index),
                    answer=str(index),
                ),
                limit=6,
            )
        self.assertEqual([turn.question for turn in state.recent_turns], ["2", "3", "4", "5", "6", "7"])

        store = InMemoryChatSessionStore(ttl_seconds=1)
        stored = store.get("session")
        stored.current_species_name = "Công lục"
        stored.last_activity_at = time.time() - 2
        store.get("another-session")
        self.assertNotIn("session", store._sessions)
        refreshed = store.get("session")
        self.assertIsNot(stored, refreshed)
        self.assertIsNone(refreshed.current_species_name)


class EntityResolverTest(unittest.TestCase):
    def test_finds_all_species_without_requiring_accents(self):
        service = build_species_service()
        docs = service.find_species_mentions("Phan biet Cong luc va Ca sau Xiem")
        self.assertEqual(
            [str(doc["_id"]) for doc in docs], ["cong-luc", "ca-sau-xiem"]
        )


class ConversationFlowTest(unittest.TestCase):
    def test_reproduction_clarification_resumes_the_pending_question(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_comparison_focus(
            state,
            [
                chatbot._entity_from_doc(BO_TOT),
                chatbot._entity_from_doc(CONG_LUC),
            ],
        )

        response, _ = chatbot._handle_text_flow(
            "Loài này sinh sản như nào?", state, True
        )
        self.assertEqual(response.status, "NEED_CLARIFICATION")
        self.assertEqual(state.focus_mode, "comparison")
        self.assertEqual(
            state.pending_clarification_question, "Loài này sinh sản như nào?"
        )

        response, debug = chatbot._handle_text_flow("Bò tót", state, True)

        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Bò tót")
        self.assertIn("Bos gaurus", response.answer)
        self.assertIn("Thông tin sinh sản", response.answer)
        self.assertEqual(debug["contextResolver"], "clarification_resume")
        self.assertIn("sinh sản", debug["resolvedQuestion"].lower())
        self.assertIsNone(state.pending_clarification_question)

    def test_explicit_species_in_vay_con_overrides_previous_focus(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_single_focus(state, BO_TOT)
        state.last_intents = ["reproduction"]

        response, debug = chatbot._handle_text_flow(
            "Vậy còn Công lục sinh sản như nào?", state, True
        )

        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Công lục")
        self.assertIn("Pavo muticus", response.answer)
        self.assertNotIn("Bos gaurus", response.answer)
        self.assertEqual(debug["resolvedQuestion"], "Vậy còn Công lục sinh sản như nào?")

    def test_elliptical_species_follow_up_inherits_reproduction_intent(self):
        chatbot = build_chatbot()
        state = ChatSessionState()

        response, _ = chatbot._handle_text_flow(
            "Phân biệt Bò tót và Công lục", state, True
        )
        self.assertEqual(response.status, "ANSWERED")

        response, _ = chatbot._handle_text_flow(
            "Loài này sinh sản như nào?", state, True
        )
        self.assertEqual(response.status, "NEED_CLARIFICATION")

        response, _ = chatbot._handle_text_flow("Bò tót", state, True)
        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Bò tót")
        self.assertIn("Bos gaurus", response.answer)

        response, debug = chatbot._handle_text_flow(
            "Còn Công lục thì sao?", state, True
        )

        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Công lục")
        self.assertIn("Pavo muticus", response.answer)
        self.assertIn("Thông tin sinh sản", response.answer)
        self.assertEqual(debug["contextResolver"], "explicit_entity_follow_up")
        self.assertEqual(debug["resolvedQuestion"], "Sinh sản của Công lục như thế nào?")
        self.assertEqual(
            [item["name"] for item in debug["questionPlan"]["intents"]],
            ["reproduction"],
        )

    def test_entity_correction_inherits_previous_reproduction_intent(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_single_focus(state, BO_TOT)
        state.last_intents = ["reproduction"]

        response, debug = chatbot._handle_text_flow(
            "Tôi đang hỏi về Công lục mà", state, True
        )

        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Công lục")
        self.assertIn("Pavo muticus", response.answer)
        self.assertIn("Thông tin sinh sản", response.answer)
        self.assertEqual(debug["contextResolver"], "entity_correction")

    def test_image_with_explicit_text_species_uses_text_species(self):
        chatbot = build_chatbot()

        response = chatbot.query(
            ChatQueryRequest(
                sessionId="image-text-conflict",
                question="Bò tót ăn gì?",
                imageUrl="data:image/jpeg;base64,AA==",
            )
        )

        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Bò tót")
        self.assertIn("Bos gaurus", response.answer)
        self.assertEqual(response.candidates, [])
        state = chatbot.session_store.get("image-text-conflict")
        self.assertFalse(state.awaiting_confirmation)

        self.assertTrue(
            chatbot._should_route_image_question_to_text("Ảnh này là Bò tót ăn gì?")
        )
        self.assertFalse(
            chatbot._should_route_image_question_to_text("Ảnh này là Bò tót đúng không?")
        )

    def test_numbered_citations_include_source_name_and_url(self):
        chatbot = build_chatbot()
        answer, status, _ = chatbot._answer_with_context(
            "Công lục sinh sản như nào?", CONG_LUC
        )

        self.assertEqual(status, "ANSWERED")
        self.assertIn("**Nguồn tham khảo**", answer)
        self.assertIn("Nguồn 1 - BirdLife DataZone", answer)
        self.assertIn("https://datazone.birdlife.org/species/factsheet/example", answer)

    def test_context_llm_cannot_replace_comparison_entities(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_comparison_focus(
            state,
            [
                chatbot._entity_from_doc(CONG_LUC),
                chatbot._entity_from_doc(CA_SAU_XIEM),
            ],
        )
        state.last_intents = ["conservation"]
        chatbot.context_resolver._client = FakeCerebrasClient(
            '{"resolved_question":"Tại sao Bò tót nguy cấp?",'
            '"entities":["Bò tót"],"intent":"conservation",'
            '"needs_clarification":false,"clarification_message":null}'
        )

        resolution = chatbot.context_resolver.resolve("Tại sao?", state)

        self.assertEqual(resolution.resolver, "rule_fallback")
        self.assertIn("Công lục", resolution.resolved_question)
        self.assertIn("Cá sấu Xiêm", resolution.resolved_question)

    def test_context_llm_invalid_json_and_timeout_use_rule_fallback(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_single_focus(state, CONG_LUC)
        state.last_intents = ["habitat"]

        for client in [FakeCerebrasClient("not-json"), FailingCerebrasClient()]:
            with self.subTest(client=type(client).__name__):
                chatbot.context_resolver._client = client
                resolution = chatbot.context_resolver.resolve("Tại sao?", state)
                self.assertEqual(resolution.resolver, "rule_fallback")
                self.assertIn("Công lục", resolution.resolved_question)

    def test_loai_kia_uses_the_other_species_from_recent_comparison(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        comparison_entities = [
            chatbot._entity_from_doc(CONG_LUC),
            chatbot._entity_from_doc(CA_SAU_XIEM),
        ]
        chatbot._set_comparison_focus(state, comparison_entities)
        state.recent_turns.append(
            ConversationTurn(
                question="Loài thứ nhất sống ở đâu?",
                resolved_question="Công lục sống ở đâu?",
                entities=[{"id": "cong-luc", "name": "Công lục"}],
            )
        )

        resolution = chatbot.context_resolver.resolve("Còn loài kia?", state)

        self.assertEqual(resolution.resolver, "rule")
        self.assertIn("Cá sấu Xiêm", resolution.resolved_question)

    def test_parser_supports_natural_comparison_phrases(self):
        chatbot = build_chatbot()
        cases = [
            "So sánh Công lục với Cá sấu Xiêm về bảo tồn",
            "So sánh giữa Công lục và Cá sấu Xiêm về bảo tồn",
            "Phân biệt Công lục và Cá sấu Xiêm",
            "Công lục và Cá sấu Xiêm khác nhau thế nào?",
            "Công lục so với Cá sấu Xiêm thì sao?",
        ]
        for question in cases:
            with self.subTest(question=question):
                self.assertGreaterEqual(
                    len(chatbot._extract_comparison_labels(question)), 2
                )

    def test_multi_turn_context_keeps_the_correct_comparison_set(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_single_focus(state, CONG_LUC)

        response, _ = chatbot._handle_text_flow(
            "So sánh loài này với Cá sấu Xiêm về bảo tồn", state, True
        )
        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(state.focus_mode, "comparison")
        self.assertIsNone(response.activeSpeciesId)
        self.assertIn("Bảng so sánh", response.answer)

        response, debug = chatbot._handle_text_flow(
            "Trong hai loài này, loài nào nguy cấp hơn?", state, True
        )
        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(debug["flow"], "multi_species_structured")
        self.assertIn("Cá sấu Xiêm", response.answer)

        response, debug = chatbot._handle_text_flow("Tại sao?", state, True)
        self.assertEqual(response.status, "ANSWERED")
        self.assertTrue(debug["isFollowUp"])
        self.assertEqual(state.focus_mode, "comparison")

        response, debug = chatbot._handle_text_flow(
            "Trong các loài này, loài nào ăn cá?", state, True
        )
        intents = [item["name"] for item in debug["questionPlan"]["intents"]]
        self.assertIn("diet", intents)
        self.assertNotIn("Ưu tiên bảo tồn", response.answer)
        self.assertIn("Theo dữ liệu thức ăn, Cá sấu Xiêm", response.answer)
        self.assertIn("ăn cá", response.answer)

        response, _ = chatbot._handle_text_flow("Còn sinh sản thì sao?", state, True)
        self.assertEqual(response.status, "ANSWERED")
        self.assertIn("Sinh sản", response.answer)
        self.assertNotIn("độ chắc chắn", response.answer.lower())

        response, _ = chatbot._handle_text_flow("Loài thứ hai sống ở đâu?", state, True)
        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(response.activeSpeciesName, "Cá sấu Xiêm")

    def test_failed_comparison_does_not_replace_single_focus(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_single_focus(state, CONG_LUC)

        response, _ = chatbot._handle_text_flow(
            "So sánh Công lục với loài không tồn tại", state, True
        )
        self.assertEqual(response.status, "NEED_CLARIFICATION")
        self.assertEqual(state.focus_mode, "single")
        self.assertEqual(state.current_species_name, "Công lục")

    def test_phan_biet_does_not_fall_back_to_one_species(self):
        chatbot = build_chatbot()
        state = ChatSessionState()
        chatbot._set_single_focus(state, CONG_LUC)

        response, debug = chatbot._handle_text_flow(
            "Phân biệt Bò tót và Công lục", state, True
        )
        self.assertEqual(response.status, "ANSWERED")
        self.assertEqual(debug["flow"], "multi_species_structured")
        self.assertEqual(state.focus_mode, "comparison")
        self.assertIsNone(state.current_species_name)

    def test_nearest_entity_must_be_confirmed_before_comparison(self):
        chatbot = build_chatbot()
        state = chatbot.session_store.get("confirm-session")
        chatbot._set_single_focus(state, CONG_LUC)
        chatbot.session_store.save("confirm-session", state)

        response = chatbot.query(
            ChatQueryRequest(
                sessionId="confirm-session",
                question="So sánh Công lục với Cá sấu về bảo tồn",
            )
        )
        self.assertEqual(response.status, "NEED_SPECIES_CONFIRM")
        self.assertEqual(len(response.candidates), 1)
        self.assertEqual(response.candidates[0].speciesId, "ca-sau-xiem")

        response = chatbot.confirm_species("confirm-session", "ca-sau-xiem")
        self.assertEqual(response.status, "ANSWERED")
        self.assertIsNone(response.activeSpeciesId)
        confirmed_state = chatbot.session_store.get("confirm-session")
        self.assertEqual(confirmed_state.focus_mode, "comparison")


if __name__ == "__main__":
    unittest.main()
