from __future__ import annotations

import os
import unittest

os.environ["CEREBRAS_API_KEY"] = ""
os.environ["ROUTER_EMBEDDING_ENABLED"] = "false"
os.environ["ROUTER_LLM_ENABLED"] = "false"

from app.core.config import settings  # noqa: E402
from app.services.chatbot_router import (  # noqa: E402
    HybridQuestionRouter,
    RouterPlan,
)


GOLDEN_CASES = [
    ("Nguồn dữ liệu của Công lục là gì?", ["source"], "source_catalog", False, "source_catalog"),
    ("Nguồn thông tin của Cá sấu Xiêm là gì?", ["source"], "source_catalog", False, "source_catalog"),
    ("Thông tin này lấy từ đâu?", ["source"], "source_catalog", False, "source_catalog"),
    ("Link nguồn của Công lục đâu?", ["source"], "source_catalog", False, "source_catalog"),
    ("Cho tôi citation của Pavo muticus", ["source"], "source_catalog", False, "source_catalog"),
    ("Có những nguồn nào cho loài này?", ["source"], "source_catalog", False, "source_catalog"),
    ("Trích dẫn nào dùng cho Bò tót?", ["source"], "source_catalog", False, "source_catalog"),
    ("source của Green Peafowl là gì?", ["source"], "source_catalog", False, "source_catalog"),
    ("Danh sách nguồn dữ liệu cho Công lục", ["source"], "source_catalog", False, "source_catalog"),
    ("Nguồn nào chứng minh thông tin Công lục?", ["source"], "source_catalog", False, "source_catalog"),
    ("Dựa trên nguồn hiện có, Công lục thích nghi như thế nào?", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Dựa trên nguồn dữ liệu hiện có, giải thích Công lục thích nghi với môi trường sống.", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Hãy giải thích dựa trên dữ liệu hiện có vì sao Công lục sống ở rừng thưa.", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Dùng bằng chứng hiện có để phân tích sinh cảnh của Công lục.", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Theo dữ liệu hiện có, tại sao Công lục phù hợp với môi trường sống đó?", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Giải thích chi tiết từ nguồn hiện có về môi trường sống của Cá sấu Xiêm.", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Dựa trên trích dẫn, vì sao Bò tót cần rừng?", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Có bằng chứng nào cho thấy Công lục thích ứng với đồng cỏ không?", ["adaptation_explanation"], "cite_sources", True, "species_qa"),
    ("Công lục thích nghi với môi trường sống như thế nào?", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Công lục thích ứng với sinh cảnh ra sao?", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Vì sao Công lục sống được ở rừng thưa?", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Tại sao Cá sấu Xiêm gắn với đất ngập nước?", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Giải thích mối liên hệ giữa sinh cảnh và bảo tồn của Công lục.", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Phân tích cách Bò tót thích nghi với rừng.", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Hãy lập luận vì sao loài này cần môi trường sống phù hợp.", ["adaptation_explanation"], "none", True, "species_qa"),
    ("Công lục sống ở môi trường nào?", ["habitat"], "none", False, "species_qa"),
    ("Sinh cảnh của Công lục là gì?", ["habitat"], "none", False, "species_qa"),
    ("Loài này sống ở kiểu sinh cảnh nào?", ["habitat"], "none", False, "species_qa"),
    ("Cá sấu Xiêm sống ở đất ngập nước không?", ["habitat"], "none", False, "species_qa"),
    ("Bò tót sống trong rừng hay đồng cỏ?", ["habitat"], "none", False, "species_qa"),
    ("Môi trường sống của Công lục như thế nào?", ["habitat"], "none", False, "species_qa"),
    ("Nơi ở của Cá sấu Xiêm là gì?", ["habitat"], "none", False, "species_qa"),
    ("Công lục phân bố ở đâu?", ["distribution"], "none", False, "species_qa"),
    ("Loài này sống ở vùng nào?", ["distribution"], "none", False, "species_qa"),
    ("Cá sấu Xiêm có ở Nam Bộ không?", ["distribution"], "none", False, "species_qa"),
    ("Công lục có tại Việt Nam không?", ["occurrence"], "none", False, "species_qa"),
    ("Bò tót ghi nhận ở vùng nào tại Việt Nam?", ["distribution"], "none", False, "species_qa"),
    ("Công lục có ở Tây Nguyên không?", ["distribution"], "none", False, "species_qa"),
    ("Loài này xuất hiện ở tỉnh nào?", ["distribution"], "none", False, "species_qa"),
    ("Công lục ăn gì?", ["diet"], "none", False, "species_qa"),
    ("Thức ăn của Công lục gồm những gì?", ["diet"], "none", False, "species_qa"),
    ("Cá sấu Xiêm săn mồi gì?", ["diet"], "none", False, "species_qa"),
    ("Bò tót ăn cỏ không?", ["diet"], "none", False, "species_qa"),
    ("Chế độ ăn của loài này là gì?", ["diet"], "none", False, "species_qa"),
    ("Con mồi chính của Cá sấu Xiêm?", ["diet"], "none", False, "species_qa"),
    ("Công lục có nguy cấp không?", ["conservation"], "none", False, "species_qa"),
    ("Mức IUCN của Công lục là gì?", ["conservation"], "none", False, "species_qa"),
    ("Công lục nằm trong sách đỏ không?", ["conservation"], "none", False, "species_qa"),
    ("Tình trạng bảo tồn của Bò tót?", ["conservation"], "none", False, "species_qa"),
    ("Loài này có trong CITES không?", ["conservation"], "none", False, "species_qa"),
    ("Cá sấu Xiêm có nguy cơ tuyệt chủng không?", ["conservation"], "none", False, "species_qa"),
    ("Công lục bị đe dọa bởi điều gì?", ["threats"], "none", False, "species_qa"),
    ("Mối đe dọa chính với Bò tót là gì?", ["threats"], "none", False, "species_qa"),
    ("Nguy cơ lớn nhất của Cá sấu Xiêm?", ["threats"], "none", False, "species_qa"),
    ("Công lục có bị mất sinh cảnh không?", ["threats"], "none", False, "species_qa"),
    ("Quần thể Công lục đang tăng hay giảm?", ["population_trend"], "none", False, "species_qa"),
    ("Xu hướng quần thể của Bò tót?", ["population_trend"], "none", False, "species_qa"),
    ("Công lục sinh sản như thế nào?", ["reproduction"], "none", False, "species_qa"),
    ("Mùa sinh sản của Công lục là khi nào?", ["reproduction"], "none", False, "species_qa"),
    ("Loài này đẻ trứng hay đẻ con?", ["reproduction"], "none", False, "species_qa"),
    ("Cá sấu Xiêm ấp trứng bao lâu?", ["reproduction"], "none", False, "species_qa"),
    ("Công lục chăm sóc con non không?", ["reproduction"], "none", False, "species_qa"),
    ("Nhận biết Công lục như thế nào?", ["identification"], "none", False, "species_qa"),
    ("Dấu hiệu nhận dạng của Cá sấu Xiêm?", ["identification"], "none", False, "species_qa"),
    ("Hình dạng của Bò tót ra sao?", ["identification"], "none", False, "species_qa"),
    ("Công lục đực và cái khác nhau thế nào?", ["identification"], "none", False, "species_qa"),
    ("Tập tính của Công lục là gì?", ["behavior"], "none", False, "species_qa"),
    ("Loài này hoạt động ban ngày hay ban đêm?", ["activity_time"], "none", False, "species_qa"),
    ("Công lục có di cư không?", ["behavior"], "none", False, "species_qa"),
    ("Tiếng kêu của loài này như thế nào?", ["behavior"], "none", False, "species_qa"),
    ("Công lục có an toàn với con người không?", ["safety"], "none", False, "species_qa"),
    ("Gặp Cá sấu Xiêm ngoài tự nhiên thì xử lý thế nào?", ["safety"], "none", False, "species_qa"),
    ("Loài này có độc không?", ["safety"], "none", False, "species_qa"),
    ("Có được nuôi Công lục không?", ["legal"], "none", False, "species_qa"),
    ("Mua bán Bò tót có hợp pháp không?", ["legal"], "none", False, "species_qa"),
    ("Vận chuyển Cá sấu Xiêm cần giấy phép không?", ["legal"], "none", False, "species_qa"),
    ("Tên khoa học của Công lục là gì?", ["scientific_name"], "none", False, "species_qa"),
    ("Công lục thuộc họ nào?", ["taxonomy"], "none", False, "species_qa"),
    ("Công lục thuộc nhóm chim đúng không?", ["group"], "none", False, "species_qa"),
    ("Loài này sống ở độ cao bao nhiêu mét?", ["altitude"], "none", False, "species_qa"),
    ("Dữ liệu nào của Công lục còn thiếu?", ["data_quality"], "none", False, "species_qa"),
    ("Thông tin nào chắc chắn nhất về Công lục?", ["data_quality"], "none", False, "species_qa"),
    ("So sánh Công lục với Cá sấu Xiêm về bảo tồn", ["conservation"], "none", False, "comparison"),
    ("Phân biệt Bò tót và Công lục", ["general"], "none", False, "comparison"),
    ("Trong hai loài này, loài nào nguy cấp hơn?", ["conservation"], "none", False, "comparison"),
    ("Công lục và Cá sấu Xiêm khác nhau thế nào?", ["general"], "none", False, "comparison"),
    ("Còn Công lục thì sao?", ["general"], "none", False, "species_qa"),
    ("Bò tót", ["general"], "none", False, "species_qa"),
    ("Loài kia thì sao?", ["general"], "none", False, "species_qa"),
    ("Xin chào", ["general"], "none", False, "control"),
    ("Xóa loài hiện tại", ["general"], "none", False, "control"),
    ("Tôi muốn gửi ảnh khác", ["general"], "none", False, "control"),
]


class RouterGoldenTest(unittest.TestCase):
    def test_golden_router_cases(self):
        router = HybridQuestionRouter()
        self.assertGreaterEqual(len(GOLDEN_CASES), 80)

        for question, expected_intents, source_mode, requires_generation, primary_task in GOLDEN_CASES:
            with self.subTest(question=question):
                plan = router.route(question)
                self.assertEqual(plan.sourceMode, source_mode)
                self.assertEqual(plan.requiresGeneration, requires_generation)
                self.assertEqual(plan.primaryTask, primary_task)
                for intent in expected_intents:
                    self.assertIn(intent, plan.normalized_intents())

    def test_clear_rule_does_not_need_semantic_or_llm_router(self):
        plan = HybridQuestionRouter().route("Xóa loài hiện tại")

        self.assertEqual(plan.router, "rule")
        self.assertEqual(plan.primaryTask, "control")
        self.assertFalse(plan.llmRouterUsed)
        self.assertEqual(plan.routerTrace[0]["decision"], "control")

    def test_semantic_router_high_confidence_for_clear_question(self):
        plan = HybridQuestionRouter().route("Công lục ăn gì?")

        self.assertEqual(plan.router, "semantic")
        self.assertIn("diet", plan.normalized_intents())
        self.assertGreaterEqual(plan.confidence, settings.router_confidence_threshold)

    def test_llm_router_fallback_can_override_semantic_plan(self):
        old_enabled = settings.router_llm_enabled
        old_threshold = settings.router_confidence_threshold
        settings.router_llm_enabled = True
        settings.router_confidence_threshold = 0.99

        class FakeLlmRouter:
            called = False

            def route(self, *_args, **_kwargs):
                self.called = True
                return RouterPlan(
                    primaryTask="species_qa",
                    intents=["adaptation_explanation"],
                    answerMode="rag_generation",
                    sourceMode="cite_sources",
                    requiresGeneration=True,
                    confidence=0.95,
                    router="llm",
                    llmRouterUsed=True,
                )

        try:
            router = HybridQuestionRouter()
            fake_llm = FakeLlmRouter()
            router.llm_router = fake_llm
            plan = router.route(
                "Dựa trên nguồn hiện có, Công lục thích nghi thế nào?",
                species_mentions=["Công lục"],
            )
        finally:
            settings.router_llm_enabled = old_enabled
            settings.router_confidence_threshold = old_threshold

        self.assertTrue(fake_llm.called)
        self.assertEqual(plan.router, "llm")
        self.assertTrue(plan.llmRouterUsed)
        self.assertEqual(plan.sourceMode, "cite_sources")

    def test_invalid_llm_router_falls_back_to_semantic_plan(self):
        old_enabled = settings.router_llm_enabled
        old_threshold = settings.router_confidence_threshold
        settings.router_llm_enabled = True
        settings.router_confidence_threshold = 0.99

        class EmptyLlmRouter:
            called = False

            def route(self, *_args, **_kwargs):
                self.called = True
                return None

        try:
            router = HybridQuestionRouter()
            empty_llm = EmptyLlmRouter()
            router.llm_router = empty_llm
            plan = router.route(
                "Dựa trên nguồn hiện có, Công lục thích nghi thế nào?",
                species_mentions=["Công lục"],
            )
        finally:
            settings.router_llm_enabled = old_enabled
            settings.router_confidence_threshold = old_threshold

        self.assertTrue(empty_llm.called)
        self.assertEqual(plan.router, "semantic")
        self.assertEqual(plan.sourceMode, "cite_sources")
        self.assertIn(
            {"router": "llm", "decision": "fallback_to_semantic"},
            plan.routerTrace,
        )


if __name__ == "__main__":
    unittest.main()
