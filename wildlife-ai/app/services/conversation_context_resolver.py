from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from app.core.config import settings
from app.services.session_store import ChatSessionState

try:
    from cerebras.cloud.sdk import Cerebras
except Exception:  # pragma: no cover - optional in lightweight test environments
    Cerebras = None


@dataclass
class ContextResolution:
    original_question: str
    resolved_question: str
    resolver: str = "none"
    is_follow_up: bool = False
    inherited_intents: list[str] = field(default_factory=list)
    resolved_entities: list[str] = field(default_factory=list)
    resolver_intent: str | None = None
    needs_clarification: bool = False
    clarification_message: str | None = None


class ConversationContextResolver:
    def __init__(self) -> None:
        self._client = (
            Cerebras(api_key=settings.cerebras_api_key)
            if Cerebras is not None and settings.cerebras_api_key
            else None
        )

    def resolve(
        self, question: str, state: ChatSessionState
    ) -> ContextResolution:
        original = (question or "").strip()
        normalized = self._normalize(original)
        names = self._focused_names(state)
        if not original or not names:
            return ContextResolution(original, original)

        topic = self._follow_up_topic(normalized)
        if topic:
            if state.focus_mode == "comparison" and len(names) >= 2:
                resolved = f"So sánh {' và '.join(names)} về {topic}."
            else:
                resolved = f"{topic.capitalize()} của {names[0]} như thế nào?"
            return ContextResolution(
                original,
                resolved,
                resolver="rule",
                is_follow_up=True,
                inherited_intents=list(state.last_intents),
            )

        ordinal = self._ordinal_reference(normalized)
        if ordinal is not None:
            if ordinal >= len(names):
                return self._clarification(
                    original, "Tôi chưa xác định được loài bạn đang nhắc tới trong ngữ cảnh hiện tại."
                )
            resolved = self._replace_ordinal_reference(original, names[ordinal])
            return ContextResolution(
                original,
                resolved,
                resolver="rule",
                is_follow_up=True,
                inherited_intents=list(state.last_intents),
            )

        if "loai con lai" in normalized or "loai kia" in normalized:
            comparison_names = self._entity_names(state.recent_multi_species_entities)
            if len(comparison_names) != 2:
                return self._clarification(
                    original, "Tôi chưa xác định được loài còn lại trong ngữ cảnh hiện tại."
                )
            last_names = {
                str(item.get("name") or "").strip()
                for item in (state.recent_turns[-1].entities if state.recent_turns else [])
                if item.get("name")
            }
            remaining = [name for name in comparison_names if name not in last_names]
            if len(remaining) != 1:
                return self._clarification(
                    original,
                    f"Bạn đang muốn hỏi loài nào: {', '.join(comparison_names)}?",
                )
            resolved = re.sub(
                r"loài\s+còn\s+lại|loai\s+con\s+lai|loài\s+kia|loai\s+kia",
                remaining[0],
                original,
                flags=re.IGNORECASE,
            )
            return ContextResolution(
                original,
                resolved,
                resolver="rule",
                is_follow_up=True,
                inherited_intents=list(state.last_intents),
            )

        if state.focus_mode == "comparison" and any(
            signal in normalized
            for signal in [
                "trong hai loai nay",
                "trong cac loai nay",
                "cac loai nay",
                "ca hai",
                "hai loai nay",
            ]
        ):
            return ContextResolution(
                original,
                f"Trong các loài {', '.join(names)}, {original}",
                resolver="rule",
                is_follow_up=True,
                inherited_intents=list(state.last_intents),
            )

        if "loai nay" in normalized:
            if state.focus_mode == "single" or len(names) == 1:
                resolved = re.sub(
                    r"loài\s+này|loai\s+nay",
                    names[0],
                    original,
                    flags=re.IGNORECASE,
                )
                return ContextResolution(
                    original,
                    resolved,
                    resolver="rule",
                    is_follow_up=True,
                    inherited_intents=list(state.last_intents),
                )
            return self._clarification(
                original,
                f"Bạn đang muốn hỏi loài nào: {', '.join(names)}?",
            )

        if normalized in {"tai sao", "vi sao", "tai sao vay", "vi sao vay"}:
            llm_result = self._resolve_with_llm(original, state, names)
            if llm_result:
                return llm_result
            subject = " và ".join(names)
            topic = ", ".join(state.last_intents) or "nội dung vừa trả lời"
            if state.focus_mode == "comparison" and len(names) >= 2:
                resolved = f"Giải thích vì sao {subject} có kết quả khác nhau về {topic}."
            else:
                resolved = f"Giải thích vì sao {subject} có kết quả vừa nêu về {topic}."
            return ContextResolution(
                original,
                resolved,
                resolver="rule_fallback",
                is_follow_up=True,
                inherited_intents=list(state.last_intents),
            )

        if re.search(r"\b(nó|no|con này|con nay|còn nó|con no)\b", original, re.I):
            llm_result = self._resolve_with_llm(original, state, names)
            if llm_result:
                return llm_result
            if len(names) == 1:
                resolved = re.sub(
                    r"\b(nó|no|con này|con nay)\b",
                    names[0],
                    original,
                    flags=re.IGNORECASE,
                )
                return ContextResolution(
                    original,
                    resolved,
                    resolver="rule_fallback",
                    is_follow_up=True,
                    inherited_intents=list(state.last_intents),
                )
            return self._clarification(
                original,
                f"Bạn đang nhắc đến loài nào: {', '.join(names)}?",
            )

        return ContextResolution(original, original)

    def _resolve_with_llm(
        self, question: str, state: ChatSessionState, names: list[str]
    ) -> ContextResolution | None:
        if self._client is None:
            return None
        prompt = f"""
Bạn là bộ giải quyết ngữ cảnh hội thoại. Chỉ viết lại câu hỏi hiện tại thành một câu độc lập.
Chỉ được dùng các loài trong danh sách: {json.dumps(names, ensure_ascii=False)}.
Câu hỏi trước: {state.last_question or ''}
Câu trả lời trước: {(state.last_answer or '')[:1200]}
Intent trước: {json.dumps(state.last_intents, ensure_ascii=False)}
Câu hỏi hiện tại: {question}

Trả đúng một JSON object, không markdown. Entity phải lấy nguyên văn từ danh sách loài.
Intent chỉ được là một trong: name, taxonomy, distribution, habitat, diet, conservation, threats, behavior, identification, reproduction, general.
{{"resolved_question":"...","entities":["..."],"intent":"...","needs_clarification":false,"clarification_message":null}}
Nếu không xác định được đối tượng, đặt needs_clarification=true và viết câu hỏi làm rõ.
""".strip()
        try:
            response = self._client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=settings.cerebras_model,
                temperature=0,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
            data = json.loads(raw)
            if data.get("needs_clarification"):
                return self._clarification(
                    question,
                    str(data.get("clarification_message") or "Bạn có thể nói rõ loài đang được hỏi không?"),
                    resolver="llm",
                )
            resolved = str(data.get("resolved_question") or "").strip()
            if not resolved:
                return None
            raw_entities = data.get("entities")
            resolver_intent = str(data.get("intent") or "").strip().lower()
            allowed_intents = {
                "name",
                "taxonomy",
                "distribution",
                "habitat",
                "diet",
                "conservation",
                "threats",
                "behavior",
                "identification",
                "reproduction",
                "general",
            }
            if not isinstance(raw_entities, list) or resolver_intent not in allowed_intents:
                return None
            entity_lookup = {self._normalize(name): name for name in names}
            resolved_entities = []
            for entity in raw_entities:
                matched_name = entity_lookup.get(self._normalize(str(entity)))
                if not matched_name:
                    return None
                if matched_name not in resolved_entities:
                    resolved_entities.append(matched_name)
            resolved_normalized = self._normalize(resolved)
            focused_names = [self._normalize(name) for name in names]
            mentioned_names = [
                name for name in focused_names if name and name in resolved_normalized
            ]
            required_count = (
                len(focused_names)
                if state.focus_mode == "comparison" and len(focused_names) >= 2
                else 1
            )
            if len(mentioned_names) < required_count:
                return None
            if len(resolved_entities) < required_count:
                return None
            return ContextResolution(
                question,
                resolved,
                resolver="llm",
                is_follow_up=True,
                inherited_intents=list(state.last_intents),
                resolved_entities=resolved_entities,
                resolver_intent=resolver_intent,
            )
        except Exception:
            return None

    def _focused_names(self, state: ChatSessionState) -> list[str]:
        names = self._entity_names(state.focused_entities)
        if not names and state.current_species_name:
            names.append(state.current_species_name)
        return names

    def _entity_names(self, entities: list[dict]) -> list[str]:
        names: list[str] = []
        for entity in entities:
            doc = entity.get("doc") if isinstance(entity, dict) else None
            if not isinstance(doc, dict):
                continue
            name = str(
                doc.get("common_name_vi") or doc.get("scientific_name") or ""
            ).strip()
            if name and name not in names:
                names.append(name)
        return names

    def _follow_up_topic(self, normalized: str) -> str | None:
        prefixes = ["con ", "the con ", "vay con "]
        remainder = ""
        for prefix in prefixes:
            if normalized.startswith(prefix):
                remainder = normalized[len(prefix) :].strip()
                break
        if not remainder:
            return None
        topic_map = [
            ("sinh san", "sinh sản"),
            ("sinh canh", "sinh cảnh"),
            ("moi truong", "môi trường sống"),
            ("thuc an", "thức ăn"),
            ("an gi", "thức ăn"),
            ("bao ton", "tình trạng bảo tồn"),
            ("phan bo", "phân bố"),
            ("tap tinh", "tập tính"),
        ]
        follow_up_suffixes = {
            "",
            "thi sao",
            "thi the nao",
            "nhu nao",
            "nhu the nao",
        }
        for signal, label in topic_map:
            suffix = remainder[len(signal) :].strip() if remainder.startswith(signal) else None
            if suffix in follow_up_suffixes:
                return label
        return None

    def _ordinal_reference(self, normalized: str) -> int | None:
        if any(signal in normalized for signal in ["loai thu nhat", "loai dau tien"]):
            return 0
        if any(signal in normalized for signal in ["loai thu hai", "loai 2"]):
            return 1
        return None

    def _replace_ordinal_reference(self, question: str, name: str) -> str:
        return re.sub(
            r"loài\s+(?:thứ\s+)?(?:nhất|hai|1|2)|loai\s+(?:thu\s+)?(?:nhat|hai|1|2)",
            name,
            question,
            count=1,
            flags=re.IGNORECASE,
        )

    def _clarification(
        self, original: str, message: str, resolver: str = "rule"
    ) -> ContextResolution:
        return ContextResolution(
            original,
            original,
            resolver=resolver,
            is_follow_up=True,
            needs_clarification=True,
            clarification_message=message,
        )

    def _normalize(self, value: str) -> str:
        text = (value or "").replace("đ", "d").replace("Đ", "D")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip().lower()
