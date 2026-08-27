from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.session_store import ChatSessionState

try:
    from cerebras.cloud.sdk import Cerebras
except Exception:  # pragma: no cover - optional in lightweight environments
    Cerebras = None


ALLOWED_INTENTS = {
    "name",
    "scientific_name",
    "taxonomy",
    "group",
    "occurrence",
    "distribution",
    "diet",
    "habitat",
    "altitude",
    "activity_time",
    "conservation",
    "threats",
    "population_trend",
    "safety",
    "legal",
    "source",
    "data_quality",
    "reproduction",
    "identification",
    "behavior",
    "adaptation_explanation",
    "general",
}

FORBIDDEN_CANDIDATES = [
    "conservation",
    "threats",
    "taxonomy_detail",
    "behavior",
    "source",
]


def normalize_text(text: str) -> str:
    normalized = (text or "").replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def tokenize(text: str) -> set[str]:
    return {item for item in normalize_text(text).split() if item}


def lexical_score(query: str, document: str) -> float:
    query_tokens = tokenize(query)
    doc_tokens = tokenize(document)
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(doc_tokens))
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(query_tokens) * len(doc_tokens))


@dataclass(frozen=True)
class IntentDefinition:
    name: str
    description: str
    examples: tuple[str, ...]
    keywords: tuple[str, ...]

    @property
    def search_text(self) -> str:
        return " ".join([self.name, self.description, *self.examples, *self.keywords])


INTENT_DEFINITIONS: tuple[IntentDefinition, ...] = (
    IntentDefinition(
        "name",
        "hỏi tên tiếng Việt, tên thường gọi hoặc loài này gọi là gì",
        ("Tên loài này là gì?", "Nó tên gì?", "Tên tiếng Việt của Công lục"),
        ("ten gi", "ten loai", "goi la gi", "ten tieng viet", "ten thuong goi"),
    ),
    IntentDefinition(
        "scientific_name",
        "hỏi tên khoa học hoặc danh pháp khoa học",
        ("Tên khoa học của Công lục là gì?", "Danh pháp của loài này"),
        ("ten khoa hoc", "scientific name", "danh phap"),
    ),
    IntentDefinition(
        "taxonomy",
        "hỏi phân loại học, họ, bộ, lớp",
        ("Công lục thuộc họ nào?", "Phân loại của loài này"),
        ("thuoc ho", "family", "phan loai", "bo nao", "lop nao"),
    ),
    IntentDefinition(
        "group",
        "hỏi nhóm loài chim thú bò sát lưỡng cư cá",
        ("Công lục thuộc nhóm nào?", "Đây là chim hay thú?"),
        ("thuoc nhom", "nhom chim", "nhom thu", "bo sat", "luong cu", "ca dung khong"),
    ),
    IntentDefinition(
        "occurrence",
        "hỏi loài có ghi nhận ở Việt Nam không",
        ("Công lục có ở Việt Nam không?", "Loài này có tại Việt Nam không?"),
        ("co o viet nam", "co tai viet nam", "o viet nam khong", "ghi nhan o viet nam"),
    ),
    IntentDefinition(
        "distribution",
        "hỏi nơi phân bố, vùng phân bố, khu vực, tỉnh, quốc gia",
        ("Công lục phân bố ở đâu?", "Loài này sống ở vùng nào tại Việt Nam?"),
        ("song o dau", "phan bo", "o dau", "vung nao", "tinh nao", "tay nguyen", "nam bo", "trung bo"),
    ),
    IntentDefinition(
        "habitat",
        "hỏi sinh cảnh, môi trường sống, nơi ở, kiểu rừng, đồng cỏ, đất ngập nước",
        ("Công lục sống trong môi trường nào?", "Sinh cảnh của loài này là gì?"),
        ("moi truong song", "sinh canh", "noi song", "noi o", "rung", "dong co", "dat ngap nuoc"),
    ),
    IntentDefinition(
        "adaptation_explanation",
        "hỏi giải thích vì sao hoặc bằng cách nào loài thích nghi với sinh cảnh môi trường sống",
        (
            "Công lục thích nghi với môi trường sống như thế nào?",
            "Giải thích vì sao loài này phù hợp với sinh cảnh đó",
        ),
        ("thich nghi", "thich ung", "giai thich", "vi sao", "tai sao", "lap luan", "phan tich"),
    ),
    IntentDefinition(
        "diet",
        "hỏi thức ăn, chế độ ăn, con mồi, săn mồi",
        ("Công lục ăn gì?", "Thức ăn của loài này gồm những gì?"),
        ("an gi", "thuc an", "che do an", "san moi", "con moi", "an ca", "an con trung", "an co", "an qua", "an thit"),
    ),
    IntentDefinition(
        "altitude",
        "hỏi độ cao phân bố hoặc khoảng cao bao nhiêu mét",
        ("Loài này sống ở độ cao nào?", "Công lục gặp ở bao nhiêu mét?"),
        ("do cao", "bao nhieu met", "cao bao nhieu", "altitude", "elevation"),
    ),
    IntentDefinition(
        "activity_time",
        "hỏi hoạt động ban ngày ban đêm thời gian hoạt động",
        ("Loài này hoạt động ban ngày hay ban đêm?", "Hoạt động lúc nào?"),
        ("ban ngay", "ban dem", "hoat dong luc nao", "diurnal", "nocturnal"),
    ),
    IntentDefinition(
        "conservation",
        "hỏi tình trạng bảo tồn IUCN sách đỏ CITES nguy cấp tuyệt chủng",
        ("Công lục có nguy cấp không?", "Mức IUCN của loài này là gì?"),
        ("bao ton", "iucn", "sach do", "nguy cap", "cites", "tuyet chung"),
    ),
    IntentDefinition(
        "threats",
        "hỏi mối đe dọa nguy cơ bị đe dọa mất sinh cảnh săn bắt buôn bán",
        ("Công lục bị đe dọa bởi điều gì?", "Nguy cơ chính của loài này"),
        ("de doa", "bi de doa", "nguy co", "mat sinh canh", "san bat", "buon ban trai phep"),
    ),
    IntentDefinition(
        "population_trend",
        "hỏi xu hướng quần thể tăng giảm ổn định",
        ("Quần thể Công lục đang tăng hay giảm?", "Xu hướng quần thể ra sao?"),
        ("xu huong quan the", "tang hay giam", "quan the", "population trend"),
    ),
    IntentDefinition(
        "safety",
        "hỏi an toàn với con người nguy hiểm có độc tấn công xử lý khi gặp",
        ("Gặp loài này ngoài tự nhiên có nguy hiểm không?", "Có an toàn với con người không?"),
        ("an toan", "con nguoi", "nguy hiem", "gay hai", "tan cong", "co doc", "gap loai nay", "cuu ho"),
    ),
    IntentDefinition(
        "legal",
        "hỏi pháp lý mua bán vận chuyển nuôi nhốt giấy phép CITES nghị định",
        ("Có được nuôi Công lục không?", "Buôn bán loài này có hợp pháp không?"),
        ("phap ly", "hop phap", "duoc phep", "giay phep", "mua ban", "van chuyen", "cites", "nghi dinh"),
    ),
    IntentDefinition(
        "source",
        "hỏi danh sách nguồn dữ liệu link nguồn trích dẫn provenance citation",
        ("Nguồn dữ liệu của Công lục là gì?", "Thông tin này lấy từ đâu?"),
        ("nguon nao", "nguon du lieu", "nguon thong tin", "link nguon", "lay tu dau", "trich dan", "citation", "source"),
    ),
    IntentDefinition(
        "data_quality",
        "hỏi dữ liệu còn thiếu chưa rõ chắc chắn nhất chất lượng dữ liệu",
        ("Dữ liệu nào còn thiếu?", "Thông tin nào chắc chắn nhất?"),
        ("con thieu", "chua ro", "du lieu", "chac chan nhat", "data quality", "missing"),
    ),
    IntentDefinition(
        "reproduction",
        "hỏi sinh sản đẻ trứng đẻ con mùa sinh sản ấp trứng chăm sóc con non",
        ("Công lục sinh sản như thế nào?", "Mùa sinh sản của loài này"),
        ("sinh san", "mua sinh san", "de trung", "de con", "ap trung", "cham soc con non"),
    ),
    IntentDefinition(
        "identification",
        "hỏi nhận dạng hình thái dấu hiệu phân biệt con đực con cái",
        ("Nhận biết Công lục như thế nào?", "Dấu hiệu hình thái của loài này"),
        ("nhan biet", "hinh dang", "dau hieu", "con duc", "con cai", "duc cai", "identification"),
    ),
    IntentDefinition(
        "behavior",
        "hỏi tập tính hành vi hoạt động di cư tiếng kêu tuổi thọ đặc điểm",
        ("Tập tính của Công lục là gì?", "Loài này có hành vi gì đặc biệt?"),
        ("tap tinh", "hanh vi", "hoat dong", "di cu", "tieng keu", "tuoi tho", "dac diem"),
    ),
)

INTENT_LOOKUP = {item.name: item for item in INTENT_DEFINITIONS}


@dataclass
class RouterPlan:
    primaryTask: str = "species_qa"
    intents: list[str] = field(default_factory=lambda: ["general"])
    answerMode: str = "structured"
    sourceMode: str = "none"
    speciesMentions: list[str] = field(default_factory=list)
    requiresGeneration: bool = False
    confidence: float = 0.0
    router: str = "semantic"
    needsClarification: bool = False
    clarificationMessage: str | None = None
    routerTrace: list[dict[str, Any]] = field(default_factory=list)
    semanticScores: list[dict[str, Any]] = field(default_factory=list)
    llmRouterUsed: bool = False

    def normalized_intents(self) -> list[str]:
        clean: list[str] = []
        for intent in self.intents or ["general"]:
            name = str(intent or "").strip()
            if name in ALLOWED_INTENTS and name not in clean:
                clean.append(name)
        return clean or ["general"]

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "primaryTask": self.primaryTask,
            "intents": self.normalized_intents(),
            "answerMode": self.answerMode,
            "sourceMode": self.sourceMode,
            "speciesMentions": list(self.speciesMentions),
            "requiresGeneration": self.requiresGeneration,
            "confidence": round(float(self.confidence or 0.0), 4),
            "router": self.router,
            "needsClarification": self.needsClarification,
            "clarificationMessage": self.clarificationMessage,
        }

    def to_question_plan(self, question: str) -> dict[str, Any]:
        intents = self.normalized_intents()
        forbidden = [
            item
            for item in FORBIDDEN_CANDIDATES
            if item not in intents
            and not (item == "source" and self.sourceMode in {"cite_sources", "source_catalog"})
        ]
        answer_style = (
            "explanatory"
            if self.requiresGeneration or "adaptation_explanation" in intents
            else "focused" if intents != ["general"] else "general"
        )
        return {
            "species_required": self.primaryTask in {"species_qa", "comparison"},
            "intents": [{"name": intent, "user_question": question} for intent in intents],
            "forbidden_sections": forbidden,
            "answer_style": answer_style,
            "requires_generation": self.requiresGeneration,
            "primary_task": self.primaryTask,
            "answer_mode": self.answerMode,
            "source_mode": self.sourceMode,
            "router_plan": self.to_debug_dict(),
            "router_trace": list(self.routerTrace),
            "semantic_scores": list(self.semanticScores),
            "llm_router_used": self.llmRouterUsed,
        }


class RuleRouter:
    def classify_control(self, question: str) -> str | None:
        normalized = normalize_text(question)
        if normalized in {"chao", "xin chao", "hello", "hi", "hey"}:
            return "greeting"
        if any(
            signal in normalized
            for signal in [
                "xoa loai",
                "xoa ngu canh",
                "xoa context",
                "reset loai",
                "bo loai hien tai",
                "chuyen loai",
                "doi loai",
            ]
        ):
            return "clear_species"
        if any(
            signal in normalized
            for signal in [
                "gui anh khac",
                "anh khac",
                "nhan dien lai",
                "tai anh moi",
                "chon anh moi",
                "doi anh",
            ]
        ):
            return "help"
        return None

    def source_catalog_requested(self, question: str) -> bool:
        normalized = normalize_text(question)
        catalog_patterns = [
            "nguon nao",
            "nguon du lieu",
            "nguon thong tin",
            "link nguon",
            "lay tu dau",
            "lay o dau",
            "trich dan nao",
            "citation",
            "source",
        ]
        source_present = any(pattern in normalized for pattern in catalog_patterns)
        if not source_present:
            return False
        explanation_or_domain = self.explanation_requested(question) or any(
            signal in normalized
            for signal in [
                "thich nghi",
                "thich ung",
                "song o",
                "moi truong",
                "sinh canh",
                "an gi",
                "bao ton",
                "nguy cap",
                "de doa",
                "sinh san",
            ]
        )
        direct_source_question = any(
            signal in normalized
            for signal in [
                "danh sach nguon",
                "nguon du lieu cua",
                "nguon thong tin cua",
                "nguon nao",
                "link nguon",
                "lay tu dau",
                "lay o dau",
                "trich dan",
                "citation",
                "source",
            ]
        )
        return direct_source_question and not explanation_or_domain

    def source_cue_present(self, question: str) -> bool:
        normalized = normalize_text(question)
        return any(
            signal in normalized
            for signal in [
                "nguon",
                "du lieu hien co",
                "du kien hien co",
                "tham khao",
                "trich dan",
                "bang chung",
                "citation",
                "source",
                "evidence",
            ]
        )

    def explanation_requested(self, question: str) -> bool:
        normalized = normalize_text(question)
        return any(
            signal in normalized
            for signal in [
                "giai thich",
                "vi sao",
                "tai sao",
                "thich nghi",
                "thich ung",
                "lap luan",
                "phan tich",
                "chi tiet",
            ]
        )

    def context_is_ambiguous(
        self, question: str, state: ChatSessionState | None, species_mentions: list[str]
    ) -> bool:
        normalized = normalize_text(question)
        if species_mentions:
            return False
        markers = [
            " no ",
            " no?",
            " no.",
            "loai nay",
            "con nay",
            "loai kia",
            "loai con lai",
            "tai sao vay",
            "vi sao vay",
            "the nao",
            "thi sao",
        ]
        has_marker = normalized in {"no", "tai sao", "vi sao"} or any(
            marker.strip() in normalized for marker in markers
        )
        if not has_marker:
            return False
        if not state:
            return True
        focused_count = len(state.focused_entities or [])
        return state.focus_mode == "comparison" or focused_count > 1 or not state.current_species_name


class SemanticRouter:
    def __init__(self) -> None:
        self._model = None
        self._intent_embeddings = None
        self._load_error: str | None = None

    def score(self, question: str, top_k: int = 6) -> list[dict[str, Any]]:
        lexical_scores = self._lexical_scores(question)
        embedding_scores = self._embedding_scores(question)
        merged: list[dict[str, Any]] = []
        for definition in INTENT_DEFINITIONS:
            lexical = lexical_scores.get(definition.name, 0.0)
            semantic = embedding_scores.get(definition.name)
            score = lexical if semantic is None else max(lexical, semantic)
            merged.append(
                {
                    "intent": definition.name,
                    "score": round(float(score), 4),
                    "lexicalScore": round(float(lexical), 4),
                    "semanticScore": (
                        None if semantic is None else round(float(semantic), 4)
                    ),
                }
            )
        merged.sort(key=lambda item: item["score"], reverse=True)
        return merged[:top_k]

    def _lexical_scores(self, question: str) -> dict[str, float]:
        normalized = normalize_text(question)
        scores: dict[str, float] = {}
        for definition in INTENT_DEFINITIONS:
            score = lexical_score(normalized, definition.search_text)
            exact_boost = 0.0
            for keyword in definition.keywords:
                normalized_keyword = normalize_text(keyword)
                if normalized_keyword and normalized_keyword in normalized:
                    exact_boost += 0.28
            for example in definition.examples:
                example_score = lexical_score(normalized, example)
                score = max(score, example_score)
            scores[definition.name] = min(1.0, score + min(0.56, exact_boost))
        return scores

    def _embedding_scores(self, question: str) -> dict[str, float]:
        if not settings.router_embedding_enabled:
            return {}
        try:
            model = self._ensure_model()
            if model is None:
                return {}
            query_vec = model.encode([question], normalize_embeddings=True)
            if self._intent_embeddings is None:
                texts = [definition.search_text for definition in INTENT_DEFINITIONS]
                self._intent_embeddings = model.encode(texts, normalize_embeddings=True)
            scores = query_vec @ self._intent_embeddings.T
            return {
                definition.name: float(scores[0][index])
                for index, definition in enumerate(INTENT_DEFINITIONS)
            }
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._load_error = f"{type(exc).__name__}: {exc}"
            return {}

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(settings.router_embedding_model)
            return self._model
        except Exception as exc:  # pragma: no cover - depends on runtime cache/network
            self._load_error = f"{type(exc).__name__}: {exc}"
            return None


class LlmRouter:
    def __init__(self) -> None:
        self._client = (
            Cerebras(api_key=settings.cerebras_api_key)
            if Cerebras is not None
            and settings.cerebras_api_key
            and settings.router_llm_enabled
            else None
        )

    def route(
        self,
        question: str,
        semantic_plan: RouterPlan,
        state: ChatSessionState | None,
        species_mentions: list[str],
    ) -> RouterPlan | None:
        if self._client is None:
            return None
        prompt = self._build_prompt(question, semantic_plan, state, species_mentions)
        try:
            raw = self._call_with_timeout(prompt)
            data = self._parse_json(raw)
            if not isinstance(data, dict):
                return None
            plan = self._plan_from_data(data, semantic_plan)
            plan.llmRouterUsed = True
            plan.routerTrace = [
                *semantic_plan.routerTrace,
                {
                    "router": "llm",
                    "decision": "accepted",
                    "latencyMs": data.get("_latency_ms"),
                },
            ]
            plan.semanticScores = list(semantic_plan.semanticScores)
            return plan
        except Exception:
            return None

    def _build_prompt(
        self,
        question: str,
        semantic_plan: RouterPlan,
        state: ChatSessionState | None,
        species_mentions: list[str],
    ) -> str:
        focused = []
        if state:
            for entity in state.focused_entities or []:
                doc = entity.get("doc") if isinstance(entity, dict) else None
                if isinstance(doc, dict):
                    focused.append(doc.get("common_name_vi") or doc.get("scientific_name"))
        allowed_intents = sorted(ALLOWED_INTENTS)
        return f"""
Bạn là router intent cho chatbot WildlifeVN. Không trả lời câu hỏi, chỉ phân loại.

Câu hỏi hiện tại: {question}
Loài được nhắc trực tiếp: {json.dumps(species_mentions, ensure_ascii=False)}
Focus hiện tại: {json.dumps([item for item in focused if item], ensure_ascii=False)}
Intent semantic dự đoán: {json.dumps(semantic_plan.to_debug_dict(), ensure_ascii=False)}

Phân biệt kỹ:
- source_catalog: người dùng hỏi danh sách nguồn/link/trích dẫn.
- cite_sources: người dùng muốn câu trả lời dựa trên nguồn/dữ liệu hiện có, nhưng ý chính vẫn là câu hỏi sinh học/bảo tồn.
- adaptation_explanation: người dùng hỏi "vì sao", "giải thích", "thích nghi", "phân tích".

Trả đúng một JSON object, không markdown:
{{
  "primaryTask": "species_qa|comparison|source_catalog|control|clarification",
  "intents": ["{allowed_intents[0]}"],
  "answerMode": "structured|rag_generation|direct_control|clarify",
  "sourceMode": "none|cite_sources|source_catalog",
  "requiresGeneration": true,
  "confidence": 0.0,
  "needsClarification": false,
  "clarificationMessage": null
}}
Intent chỉ được thuộc danh sách: {json.dumps(allowed_intents, ensure_ascii=False)}.
Nếu câu có ý chính sinh học nhưng có cụm "dựa trên nguồn/dữ liệu", đặt sourceMode="cite_sources", không đặt primaryTask="source_catalog".
""".strip()

    def _call_with_timeout(self, prompt: str) -> str:
        timeout = max(0.1, float(settings.router_timeout_seconds))

        def call() -> str:
            response = self._client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=settings.router_model or settings.cerebras_model,
                temperature=0,
            )
            return response.choices[0].message.content.strip()

        started = time.perf_counter()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(call)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise TimeoutError(f"router exceeded {timeout:g}s")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._last_latency_ms = elapsed_ms

    def _parse_json(self, raw: str) -> dict[str, Any] | None:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
        return json.loads(cleaned)

    def _plan_from_data(self, data: dict[str, Any], fallback: RouterPlan) -> RouterPlan:
        intents = [
            str(item).strip()
            for item in data.get("intents") or []
            if str(item).strip() in ALLOWED_INTENTS
        ]
        if not intents:
            intents = fallback.normalized_intents()
        primary_task = str(data.get("primaryTask") or fallback.primaryTask).strip()
        if primary_task not in {
            "species_qa",
            "comparison",
            "source_catalog",
            "control",
            "clarification",
        }:
            primary_task = fallback.primaryTask
        source_mode = str(data.get("sourceMode") or fallback.sourceMode).strip()
        if source_mode not in {"none", "cite_sources", "source_catalog"}:
            source_mode = fallback.sourceMode
        answer_mode = str(data.get("answerMode") or fallback.answerMode).strip()
        if answer_mode not in {"structured", "rag_generation", "direct_control", "clarify"}:
            answer_mode = fallback.answerMode
        confidence = data.get("confidence")
        try:
            confidence_value = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = fallback.confidence
        return RouterPlan(
            primaryTask=primary_task,
            intents=intents,
            answerMode=answer_mode,
            sourceMode=source_mode,
            speciesMentions=list(fallback.speciesMentions),
            requiresGeneration=bool(
                data.get("requiresGeneration", fallback.requiresGeneration)
            ),
            confidence=confidence_value,
            router="llm",
            needsClarification=bool(
                data.get("needsClarification", fallback.needsClarification)
            ),
            clarificationMessage=data.get("clarificationMessage")
            or fallback.clarificationMessage,
        )


class HybridQuestionRouter:
    def __init__(self) -> None:
        self.rule_router = RuleRouter()
        self.semantic_router = SemanticRouter()
        self.llm_router = LlmRouter()

    def route(
        self,
        question: str,
        state: ChatSessionState | None = None,
        species_mentions: list[str] | None = None,
    ) -> RouterPlan:
        mentions = [str(item).strip() for item in (species_mentions or []) if str(item).strip()]
        control = self.rule_router.classify_control(question)
        if control:
            return RouterPlan(
                primaryTask="control",
                intents=["general"],
                answerMode="direct_control",
                sourceMode="none",
                speciesMentions=mentions,
                requiresGeneration=False,
                confidence=1.0,
                router="rule",
                routerTrace=[
                    {"router": "rule", "decision": "control", "control": control}
                ],
            )

        semantic_scores = self.semantic_router.score(question)
        semantic_plan = self._build_semantic_plan(question, mentions, semantic_scores)
        semantic_plan.routerTrace.append(
            {
                "router": "semantic",
                "decision": "candidate",
                "confidence": semantic_plan.confidence,
            }
        )

        if self._should_call_llm(question, semantic_plan, state, mentions):
            llm_plan = self.llm_router.route(question, semantic_plan, state, mentions)
            if llm_plan:
                return llm_plan
            semantic_plan.routerTrace.append(
                {"router": "llm", "decision": "fallback_to_semantic"}
            )
        return semantic_plan

    def _build_semantic_plan(
        self, question: str, species_mentions: list[str], scores: list[dict[str, Any]]
    ) -> RouterPlan:
        threshold = float(settings.router_confidence_threshold)
        top_score = float(scores[0]["score"]) if scores else 0.0
        exact_intents = self._exact_intent_matches(question)
        if exact_intents:
            selected = exact_intents
        elif self._looks_selection_or_followup_only(question):
            selected = ["general"]
        else:
            selected = [
                str(item["intent"])
                for item in scores
                if float(item["score"]) >= max(0.45, min(threshold, top_score - 0.08))
                and float(item["score"]) >= 0.35
            ][:3]
            if top_score < 0.18:
                selected = ["general"]
            elif not selected and scores:
                selected = [str(scores[0]["intent"])]
        selected = self._normalize_selected_intents(question, selected)
        if self._comparison_requested(question) and not self._comparison_has_domain_intent(question):
            selected = ["general"]

        source_mode = "none"
        if self.rule_router.source_catalog_requested(question):
            source_mode = "source_catalog"
            selected = ["source"]
        elif self.rule_router.source_cue_present(question):
            source_mode = "cite_sources"
            selected = [intent for intent in selected if intent != "source"] or ["general"]

        requires_generation = (
            self.rule_router.explanation_requested(question)
            or "adaptation_explanation" in selected
            or source_mode == "cite_sources"
        )
        answer_mode = "rag_generation" if requires_generation else "structured"
        primary_task = "source_catalog" if source_mode == "source_catalog" else "species_qa"
        if self._comparison_requested(question):
            primary_task = "comparison"

        return RouterPlan(
            primaryTask=primary_task,
            intents=selected or ["general"],
            answerMode=answer_mode,
            sourceMode=source_mode,
            speciesMentions=species_mentions,
            requiresGeneration=requires_generation,
            confidence=top_score,
            router="semantic",
            semanticScores=scores,
        )

    def _looks_selection_or_followup_only(self, question: str) -> bool:
        normalized = normalize_text(question)
        if self._has_exact_intent_signal(normalized):
            return False
        tokens = normalized.split()
        if len(tokens) <= 3:
            return True
        return len(tokens) <= 6 and any(
            signal in normalized
            for signal in [
                "thi sao",
                "the con",
                "vay con",
                "con ",
                "loai nay",
                "loai kia",
            ]
        )

    def _has_exact_intent_signal(self, normalized_question: str) -> bool:
        return bool(self._exact_intent_matches(normalized_question, already_normalized=True))

    def _exact_intent_matches(
        self, question: str, already_normalized: bool = False
    ) -> list[str]:
        normalized_question = question if already_normalized else normalize_text(question)
        matches: list[tuple[int, str]] = []
        for definition in INTENT_DEFINITIONS:
            for keyword in definition.keywords:
                normalized_keyword = normalize_text(keyword)
                if normalized_keyword and normalized_keyword in normalized_question:
                    matches.append((normalized_question.find(normalized_keyword), definition.name))
                    break
        clean: list[str] = []
        for _, intent in sorted(matches, key=lambda item: item[0]):
            if intent not in clean:
                clean.append(intent)
        return clean[:3]

    def _normalize_selected_intents(self, question: str, selected: list[str]) -> list[str]:
        normalized = normalize_text(question)
        clean: list[str] = []
        for intent in selected:
            if intent in ALLOWED_INTENTS and intent not in clean:
                clean.append(intent)

        if self.rule_router.explanation_requested(question):
            if "thich nghi" in normalized or "thich ung" in normalized:
                clean = [item for item in clean if item not in {"source", "habitat"}]
                clean.insert(0, "adaptation_explanation")
            elif "adaptation_explanation" not in clean:
                clean.insert(0, "adaptation_explanation")
        else:
            clean = [item for item in clean if item != "adaptation_explanation"]

        if "source" in clean and len(clean) > 1 and self.rule_router.source_cue_present(question):
            clean.remove("source")

        if not clean:
            clean = ["general"]
        if len(clean) > 1 and "general" in clean:
            clean.remove("general")
        return clean[:3]

    def _comparison_requested(self, question: str) -> bool:
        normalized = normalize_text(question)
        if any(signal in normalized for signal in ["duc va cai", "con duc va con cai"]):
            return False
        return any(
            signal in normalized
            for signal in [
                "so sanh",
                "phan biet",
                "khac nhau",
                "giong nhau",
                "trong hai loai",
                "trong cac loai",
            ]
        )

    def _comparison_has_domain_intent(self, question: str) -> bool:
        normalized = normalize_text(question)
        if re.search(r"\b(?:ve|theo)\b", normalized):
            return True
        return any(
            signal in normalized
            for signal in [
                "bao ton",
                "iucn",
                "sach do",
                "nguy cap",
                "sinh canh",
                "moi truong",
                "song o dau",
                "phan bo",
                "an gi",
                "an ca",
                "an co",
                "an qua",
                "an thit",
                "an con trung",
                "thuc an",
                "sinh san",
                "de doa",
                "nhan biet",
                "tap tinh",
            ]
        )

    def _should_call_llm(
        self,
        question: str,
        plan: RouterPlan,
        state: ChatSessionState | None,
        species_mentions: list[str],
    ) -> bool:
        if not settings.router_llm_enabled:
            return False
        if plan.confidence < float(settings.router_confidence_threshold):
            return True
        if self.rule_router.context_is_ambiguous(question, state, species_mentions):
            return True
        source_conflict = (
            self.rule_router.source_cue_present(question)
            and plan.sourceMode != "source_catalog"
            and (
                plan.requiresGeneration
                or any(intent not in {"source", "data_quality", "general"} for intent in plan.intents)
            )
        )
        if source_conflict:
            return True
        close_scores = [
            item
            for item in plan.semanticScores[:4]
            if float(item.get("score") or 0.0) >= plan.confidence - 0.05
        ]
        return len(close_scores) >= 3 and plan.confidence < 0.78
