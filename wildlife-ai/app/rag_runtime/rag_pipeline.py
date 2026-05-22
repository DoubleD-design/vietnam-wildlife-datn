# rag_pipeline.py
import json
import os
import re
import time
import argparse
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest
import numpy as np
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError as exc:
    raise SystemExit("Thiếu thư viện 'pymongo'. Hãy cài: pip install pymongo") from exc

try:
    from sentence_transformers import SentenceTransformer
except ImportError as exc:
    raise SystemExit(
        "Thiếu thư viện 'sentence-transformers'. Hãy cài: pip install sentence-transformers"
    ) from exc

try:
    import faiss
except ImportError as exc:
    raise SystemExit("Thiếu thư viện 'faiss'. Hãy cài: pip install faiss-cpu") from exc

try:
    from cerebras.cloud.sdk import Cerebras
except ImportError as exc:
    raise SystemExit(
        "Thiếu thư viện 'cerebras_cloud_sdk'. Hãy cài: pip install cerebras_cloud_sdk"
    ) from exc


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


_load_dotenv(Path(__file__).with_name(".env"))

# ============================================================
# CONFIG
# ============================================================
KB_DIR = Path("knowledge_base")
TOP_K = max(1, int(os.getenv("RAG_TOP_K", "4")))
MIN_SCORE = 0.45
MIN_HYBRID_SCORE = float(os.getenv("RAG_MIN_HYBRID_SCORE", "0.2"))
# Retrieval profiles tuned from offline benchmark.
ALPHA_ENTITY = float(os.getenv("RAG_ALPHA_ENTITY", "0.5"))
ALPHA_FACET = float(os.getenv("RAG_ALPHA_FACET", "0.3"))
ANSWER_STYLE = os.getenv("RAG_ANSWER_STYLE", "detailed").strip().lower()
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b").strip()
CEREBRAS_API_URL = os.getenv(
    "CEREBRAS_API_URL", "https://api.cerebras.ai/v1/chat/completions"
).strip()
MAX_API_RETRIES = int(os.getenv("RAG_MAX_API_RETRIES", "0"))
MAX_RETRY_WAIT_SECONDS = int(os.getenv("RAG_MAX_RETRY_WAIT_SECONDS", "3"))
GENERATION_TIMEOUT_SECONDS = float(os.getenv("RAG_GENERATION_TIMEOUT_SECONDS", "20"))
RAG_MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip()
RAG_MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "wildlife_library").strip()
RAG_SPECIES_RAW_COLLECTION = os.getenv(
    "MONGODB_SPECIES_RAW_COLLECTION", "species_raw"
).strip()


def _normalize_sci_name(name: str) -> str:
    return " ".join((name or "").replace("_", " ").strip().lower().split())


def _normalize_search_text(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _tokenize_search(text: str) -> set[str]:
    normalized = _normalize_search_text(text)
    return {tok for tok in normalized.split(" ") if tok}


def _build_chunk_search_text(chunk: dict[str, Any]) -> str:
    fields = [
        str(chunk.get("sci_name") or ""),
        str(chunk.get("common_name") or ""),
        str(chunk.get("source") or ""),
        str(chunk.get("text") or ""),
    ]
    return " ".join(fields)


def _lexical_score(query_tokens: set[str], doc_tokens: set[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(doc_tokens))
    if overlap == 0:
        return 0.0
    return overlap / np.sqrt(len(query_tokens) * len(doc_tokens))


def _detect_facet_query(question: str) -> bool:
    q = _normalize_search_text(question)
    facet_signals = [
        "cac loai",
        "nhung loai",
        "danh sach",
        "iucn",
        "thuoc ho",
        "muc bao ton",
        "nhom",
    ]
    return any(sig in q for sig in facet_signals)


def _list_to_text(items: list[str], sep: str = ", ", empty: str = "khong ro") -> str:
    clean = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not clean:
        return empty
    return sep.join(clean)


REGION_LABELS = {
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

FACT_VALUE_LABELS = {
    "unknown": "chưa rõ",
    "illegal_trade": "buôn bán trái phép",
    "illegal trade": "buôn bán trái phép",
    "agricultural": "khu vực nông nghiệp",
    "grassland": "đồng cỏ",
    "mountain": "vùng núi",
    "tropical forest": "rừng nhiệt đới",
    "urban": "ven khu dân cư",
    "urban_edge": "ven khu dân cư",
    "wetland": "đất ngập nước",
    "insects": "côn trùng",
    "small mammals": "động vật có vú nhỏ",
    "leaves": "lá",
    "fruits": "quả",
    "grass": "cỏ",
    "grasses": "cỏ",
    "bark": "vỏ cây",
    "twigs": "cành cây",
    "montane": "vùng núi",
    "habitat_loss": "mất/suy thoái sinh cảnh",
    "habitat loss": "mất/suy thoái sinh cảnh",
    "other": "khác/chưa phân loại",
    "hunting": "săn bắt",
}


def _normalize_region_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    key = _normalize_search_text(raw)
    return REGION_LABELS.get(key, raw)


def _normalize_region_values(values: Any) -> list[str]:
    if isinstance(values, str):
        candidates = [values]
    elif isinstance(values, list):
        candidates = values
    else:
        candidates = []

    normalized: list[str] = []
    for item in candidates:
        label = _normalize_region_label(item)
        if label and label not in normalized:
            normalized.append(label)
    return normalized


def _fact_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    key = _normalize_search_text(raw)
    return FACT_VALUE_LABELS.get(key, raw)


def _fact_values(values: Any) -> list[str]:
    if isinstance(values, str):
        candidates = [values]
    elif isinstance(values, list):
        candidates = values
    else:
        candidates = []

    labels: list[str] = []
    for item in candidates:
        label = _fact_label(item)
        if label and label not in labels:
            labels.append(label)
    return labels


def _has_unknown_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "0", "unknown", "khong ro", "không rõ", "none", "null", "n/a"}


def _detect_source_query(question: str) -> bool:
    q = _normalize_search_text(question)
    signals = [
        "nguon",
        "nguon nao",
        "nguon thong tin",
        "link nguon",
        "lay tu dau",
        "lay o dau",
        "tham khao",
        "trich dan",
        "bang chung",
        "citation",
        "source",
        "evidence",
    ]
    return any(signal in q for signal in signals)


def _data_warnings_from_profile(
    profile: dict[str, Any], intents: list[str] | None = None
) -> list[str]:
    if not profile:
        return ["Không tìm thấy raw profile cấu trúc cho loài này."]

    warnings: list[str] = []
    intent_set = set(intents or [])
    include_all = bool(intent_set.intersection({"source", "data_quality"}))
    conservation = profile.get("conservation") or {}
    iucn = conservation.get("iucn") or {}
    vn_red = conservation.get("vietnam_red_data") or {}
    distribution = profile.get("distribution") or {}
    distribution_vn = distribution.get("vietnam") or {}
    ecology = profile.get("ecology") or {}
    provenance = profile.get("provenance") or {}

    conservation_related = include_all or bool(
        intent_set.intersection({"conservation", "threats", "population_trend", "legal", "safety"})
    )
    diet_related = include_all or "diet" in intent_set
    habitat_related = include_all or bool(
        intent_set.intersection({"habitat", "distribution", "occurrence", "altitude"})
    )
    source_related = include_all or "source" in intent_set

    if conservation_related and _has_unknown_value(iucn.get("year")):
        warnings.append("Năm đánh giá IUCN đang thiếu hoặc bằng 0.")
    if conservation_related and _has_unknown_value(iucn.get("population_trend")):
        warnings.append("Xu hướng quần thể IUCN chưa rõ.")
    if conservation_related and _has_unknown_value(vn_red.get("year")):
        warnings.append("Năm Sách đỏ Việt Nam đang thiếu hoặc bằng 0.")
    if diet_related and not ecology.get("diet"):
        warnings.append("Dữ liệu thức ăn/chế độ ăn chưa đủ trong structured facts.")
    if habitat_related and not ecology.get("habitat_tags"):
        warnings.append("Dữ liệu sinh cảnh chưa đủ trong structured facts.")
    if source_related and not provenance.get("sources"):
        warnings.append("Raw profile chưa có danh sách nguồn provenance.")

    raw_regions: list[str] = []
    for candidate in (
        distribution_vn.get("regions"),
        distribution.get("regions"),
        distribution.get("regions_vi"),
    ):
        if isinstance(candidate, list):
            raw_regions.extend(str(item).strip() for item in candidate)
        elif isinstance(candidate, str):
            raw_regions.append(candidate.strip())
    if habitat_related and any(_normalize_search_text(region) in {"north", "central", "south"} for region in raw_regions):
        warnings.append("Một số vùng phân bố còn ở dạng tiếng Anh và đã được chuẩn hóa khi hiển thị.")

    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)
    return deduped


SOURCE_QUALITY_PRIORITY = {
    "official": 0,
    "biodiversity_db": 1,
    "community": 2,
    "generated": 3,
    "unknown": 4,
}


def _source_quality(name: str, url: str = "", category: str = "") -> str:
    source_label = _normalize_search_text(" ".join([name or "", category or ""]))
    if any(signal in source_label for signal in ["gemini", "llm", "generated", "seed from bioclip", "bioclip"]):
        return "generated"

    text = _normalize_search_text(" ".join([name or "", url or "", category or ""]))
    if any(
        signal in text
        for signal in [
            "iucn",
            "cites",
            "sach do",
            "red data",
            "red_data",
            "red list",
            "red_list",
            "official",
            "government_scientific",
        ]
    ):
        return "official"
    if any(signal in text for signal in ["gbif", "wikidata", "catalogue of life", "col"]):
        return "biodiversity_db"
    if any(
        signal in text
        for signal in [
            "wikipedia",
            "inaturalist",
            "wwf",
            "conservation_ngo",
            "thiennhien",
            "wildlife_at_risk",
        ]
    ):
        return "community"
    if any(signal in text for signal in ["gemini", "llm", "generated", "seed from bioclip", "bioclip"]):
        return "generated"
    return "unknown"


def _source_quality_summary(source_names: list[str], profile: dict[str, Any]) -> list[dict[str, str]]:
    known = {item["name"]: item for item in _provenance_sources(profile)}
    summary: list[dict[str, str]] = []
    for source in source_names:
        name = str(source or "").strip()
        if not name:
            continue
        known_item = known.get(name, {})
        quality = known_item.get("quality") or _source_quality(
            name,
            known_item.get("url", ""),
            known_item.get("category", ""),
        )
        summary.append(
            {
                "name": name,
                "quality": quality,
                "url": known_item.get("url", ""),
                "category": known_item.get("category", ""),
            }
        )
    return summary


def _retrieval_warnings(chunks: list[dict[str, Any]], species_name: str = "") -> list[str]:
    if not chunks or not species_name:
        return []
    target = _normalize_sci_name(species_name)
    warnings: list[str] = []
    noisy: list[str] = []
    for chunk in chunks[:4]:
        chunk_sci = _normalize_sci_name(chunk.get("sci_name", ""))
        source = str(chunk.get("source") or chunk.get("common_name") or "unknown").strip()
        if not chunk_sci:
            noisy.append(source)
        elif target and chunk_sci != target:
            noisy.append(f"{source}:{chunk.get('sci_name')}")
    if noisy:
        warnings.append(
            "Retrieval noise: top chunks có nguồn tổng quát hoặc khác loài: "
            + ", ".join(noisy[:4])
        )
    return warnings


def _coverage_warnings(answer: str) -> list[str]:
    normalized = _normalize_search_text(answer)
    signals = [
        "chua co thong tin du",
        "chua co truong cau truc du",
        "chua tach rieng",
        "kho du lieu hien chua co",
    ]
    if any(signal in normalized for signal in signals):
        return ["Coverage gap: answer nêu rõ dữ liệu cấu trúc còn thiếu/chưa đủ."]
    return []


def _provenance_sources(profile: dict[str, Any]) -> list[dict[str, str]]:
    provenance = profile.get("provenance") or {}
    sources: list[dict[str, str]] = []
    for src in provenance.get("sources") or []:
        if not isinstance(src, dict):
            continue
        name = str(src.get("name") or src.get("source") or "").strip()
        url = str(src.get("url") or src.get("source_url") or "").strip()
        category = str(src.get("category") or src.get("type") or "").strip()
        if not name and not url:
            continue
        item = {
            "name": name or url,
            "url": url,
            "category": category,
            "quality": _source_quality(name or url, url, category),
        }
        if item not in sources:
            sources.append(item)
    sources.sort(
        key=lambda item: (
            SOURCE_QUALITY_PRIORITY.get(item.get("quality", "unknown"), 99),
            item.get("name", ""),
        )
    )
    return sources


def _build_source_answer(species_name: str, profile: dict[str, Any], data_warnings: list[str]) -> str:
    accepted = profile.get("accepted_name") or {}
    names = ((profile.get("names") or {}).get("common") or {}).get("vi") or []
    label = _list_to_text(names, empty="") or accepted.get("scientific") or species_name
    sources = _provenance_sources(profile)

    lines = [f"**Nguồn dữ liệu cho {label}:**"]
    if sources:
        for index, src in enumerate(sources, 1):
            suffix = f" - {src['url']}" if src.get("url") else ""
            quality = src.get("quality") or "unknown"
            category = src.get("category") or quality
            category_text = f" ({category})" if category else ""
            lines.append(f"{index}. {src['name']}{category_text}{suffix}")
    else:
        lines.append("- Kho dữ liệu hiện chưa có URL/provenance chi tiết cho từng fact của loài này.")

    lines.extend(
        [
            "",
            "**Phạm vi nguồn:** taxonomy/tên loài, bảo tồn, phân bố, sinh cảnh và các fact cấu trúc được lấy từ raw profile nội bộ nếu có.",
        ]
    )
    if data_warnings:
        lines.append(
            "**Giới hạn dữ liệu:** "
            + " ".join(data_warnings)
        )
    else:
        lines.append("**Giới hạn dữ liệu:** Chưa có citation theo từng câu/fact ở response public.")
    return "\n".join(lines)


def _build_evidence_items(
    chunks: list[dict[str, Any]],
    question_plan: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    intents = _question_plan_intents(question_plan)
    claim_type = intents[0] if len(intents) == 1 else ("multi_intent" if intents else "general")

    evidence: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks[:limit], 1):
        text = " ".join(str(chunk.get("text") or "").split())
        evidence.append(
            {
                "claim_type": claim_type,
                "source": chunk.get("source") or "",
                "url": chunk.get("url") or "",
                "chunk_id": f"retrieval:{chunk.get('retrieval_rank') or idx}",
                "text_preview": text[:280],
                "score": chunk.get("rerank_score")
                or chunk.get("score")
                or chunk.get("semantic_score"),
            }
        )

    profile = profile or {}
    for src in _provenance_sources(profile):
        if len(evidence) >= limit:
            break
        evidence.append(
            {
                "claim_type": "source",
                "source": src.get("name") or "",
                "url": src.get("url") or "",
                "chunk_id": None,
                "text_preview": "",
                "score": None,
            }
        )

    return evidence


def _species_display_label(profile: dict[str, Any], species_name: str) -> str:
    accepted = profile.get("accepted_name") or {}
    names = ((profile.get("names") or {}).get("common") or {}).get("vi") or []
    return _list_to_text(names, empty="") or accepted.get("scientific") or species_name


def _profile_sources_text(profile: dict[str, Any]) -> str:
    names = [item["name"] for item in _provenance_sources(profile) if item.get("name")]
    return _list_to_text(names, empty="chưa có provenance chi tiết")


def _question_text_from_plan(question_plan: dict[str, Any] | None) -> str:
    if not isinstance(question_plan, dict):
        return ""
    for item in question_plan.get("intents") or []:
        if isinstance(item, dict) and item.get("user_question"):
            return str(item.get("user_question") or "")
    return ""


def _profile_scientific_name(profile: dict[str, Any], species_name: str) -> str:
    accepted = profile.get("accepted_name") or {}
    return str(accepted.get("scientific") or species_name or "").strip()


def _profile_common_vi(profile: dict[str, Any]) -> str:
    names = ((profile.get("names") or {}).get("common") or {}).get("vi") or []
    return _list_to_text(names, empty="")


def _profile_group_label(profile: dict[str, Any]) -> str:
    taxonomy = profile.get("taxonomy") or {}
    tax_class = _normalize_search_text(taxonomy.get("class") or "")
    if "aves" in tax_class or "bird" in tax_class:
        return "chim"
    if "mammalia" in tax_class or "mammal" in tax_class:
        return "thú"
    if "reptilia" in tax_class or "reptile" in tax_class:
        return "bò sát"
    if "amphibia" in tax_class or "amphib" in tax_class:
        return "lưỡng cư"
    if "actinopterygii" in tax_class or "fish" in tax_class or "pisces" in tax_class:
        return "cá"
    return taxonomy.get("class") or "chưa rõ nhóm"


def _profile_regions(profile: dict[str, Any]) -> list[str]:
    distribution = profile.get("distribution") or {}
    distribution_vn = distribution.get("vietnam") or {}
    values: list[str] = []
    for candidate in (
        distribution_vn.get("regions"),
        distribution.get("regions"),
        distribution.get("regions_vi"),
    ):
        values.extend(_normalize_region_values(candidate))
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def _profile_localities(profile: dict[str, Any]) -> list[str]:
    distribution = profile.get("distribution") or {}
    distribution_vn = distribution.get("vietnam") or {}
    values: list[str] = []
    for key in ("provinces", "localities", "areas"):
        candidate = distribution_vn.get(key)
        if isinstance(candidate, list):
            values.extend(str(item).strip() for item in candidate if str(item).strip())
        elif isinstance(candidate, str) and candidate.strip():
            values.append(candidate.strip())
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def _profile_countries(profile: dict[str, Any]) -> list[str]:
    distribution = profile.get("distribution") or {}
    values = distribution.get("countries") or []
    if isinstance(values, str):
        return [values] if values.strip() else []
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip()]
    return []


def _format_cites_appendix(value: Any, empty: str = "không rõ") -> str:
    raw = str(value or "").strip()
    if not raw:
        return empty
    if _normalize_search_text(raw).startswith("appendix"):
        return raw
    return f"Appendix {raw}"


def _target_region(question: str) -> str | None:
    normalized = _normalize_search_text(question)
    region_map = {
        "bac bo": "Bắc Bộ",
        "trung bo": "Trung Bộ",
        "nam bo": "Nam Bộ",
        "tay nguyen": "Tây Nguyên",
    }
    for key, label in region_map.items():
        if key in normalized:
            return label
    return None


def _target_habitat(question: str) -> str | None:
    normalized = _normalize_search_text(question)
    habitat_map = {
        "dat ngap nuoc": "đất ngập nước",
        "wetland": "đất ngập nước",
        "rung ngap man": "rừng ngập mặn",
        "mangrove": "rừng ngập mặn",
        "rung nhiet doi": "rừng nhiệt đới",
        "tropical forest": "rừng nhiệt đới",
        "dong co": "đồng cỏ",
        "grassland": "đồng cỏ",
        "vung nui": "vùng núi",
        "mountain": "vùng núi",
        "montane": "vùng núi",
    }
    for key, label in habitat_map.items():
        if key in normalized:
            return label
    return None


def _matches_normalized(label: str, values: list[str]) -> bool:
    target = _normalize_search_text(label)
    for value in values:
        normalized = _normalize_search_text(value)
        if target and (target == normalized or target in normalized or normalized in target):
            return True
    return False


def _missing_answer(label: str, topic: str) -> str:
    return (
        f"**{topic}:** Kho dữ liệu hiện chưa có thông tin đủ về {topic.lower()} của {label}."
    )


def _append_limit(lines: list[str], data_warnings: list[str]) -> None:
    if data_warnings:
        lines.append("**Giới hạn dữ liệu:** " + " ".join(data_warnings))


def _build_data_quality_answer(label: str, data_warnings: list[str]) -> str:
    if not data_warnings:
        return (
            f"**Chất lượng dữ liệu:** Các trường cấu trúc chính của {label} hiện không có cảnh báo tự động đáng kể.\n\n"
            "**Giới hạn dữ liệu:** Response public vẫn chưa có citation theo từng fact, nên nên kiểm tra nguồn gốc khi dùng cho báo cáo chính thức."
        )
    lines = [f"**Phần dữ liệu còn thiếu/chưa rõ của {label}:**"]
    for warning in data_warnings:
        lines.append(f"- {warning}")
    lines.append("")
    lines.append("**Giới hạn dữ liệu:** Đây là cảnh báo tự động từ raw profile/metadata, chưa phải đánh giá khoa học cuối cùng.")
    return "\n".join(lines)


def _build_confidence_answer(label: str, profile: dict[str, Any], data_warnings: list[str]) -> str:
    scientific = _profile_scientific_name(profile, "")
    taxonomy = profile.get("taxonomy") or {}
    regions = _profile_regions(profile)
    conservation = profile.get("conservation") or {}
    iucn = conservation.get("iucn") or {}
    lines = [f"**Thông tin chắc chắn nhất về {label}:**"]
    if scientific:
        lines.append(f"- Tên khoa học: *{scientific}*.")
    if taxonomy.get("family"):
        lines.append(f"- Họ: {taxonomy.get('family')}.")
    if regions:
        lines.append(f"- Vùng phân bố tại Việt Nam: {_list_to_text(regions)}.")
    if iucn.get("category"):
        lines.append(f"- Mức IUCN trong dữ liệu: {iucn.get('category')}.")
    lines.append("")
    if data_warnings:
        lines.append("**Điểm cần kiểm tra thêm:** " + " ".join(data_warnings))
    else:
        lines.append("**Điểm cần kiểm tra thêm:** Chưa có citation theo từng fact ở response public.")
    return "\n".join(lines)


def _build_safety_legal_answer(
    question: str,
    label: str,
    profile: dict[str, Any],
    data_warnings: list[str],
) -> str:
    normalized = _normalize_search_text(question)
    conservation = profile.get("conservation") or {}
    iucn = conservation.get("iucn") or {}
    vn_red = conservation.get("vietnam_red_data") or {}
    ecology = profile.get("ecology") or {}
    safety = profile.get("safety") or {}
    legal = profile.get("legal") or {}
    cites = _format_cites_appendix(conservation.get("cites_appendix"))
    iucn_category = iucn.get("category") or "chưa rõ"
    vn_category = vn_red.get("category") or "chưa rõ"
    threats = _list_to_text(
        _fact_values(conservation.get("major_threats", [])),
        empty="chưa rõ",
    )
    venomous = ecology.get("venomous")
    if _has_unknown_value(venomous):
        venom_text = "kho dữ liệu chưa có trường species-specific để khẳng định có độc hay không"
    else:
        venom_norm = _normalize_search_text(venomous)
        if venom_norm in {"true", "yes", "co", "có"}:
            venom_text = "dữ liệu cấu trúc ghi nhận có độc/độc tố"
        elif venom_norm in {"false", "no", "khong", "không"}:
            venom_text = "dữ liệu cấu trúc ghi nhận không độc"
        else:
            venom_text = _fact_label(venomous)

    safety_note = ""
    safety_guidance = ""
    safety_risk = ""
    if isinstance(safety, dict):
        safety_note = _list_to_text(
            _fact_values(
                safety.get("notes")
                or safety.get("human_risk")
                or safety.get("danger_to_humans")
                or safety.get("risk")
            ),
            empty="",
        )
        safety_guidance = _list_to_text(
            _fact_values(safety.get("encounter_guidance") or safety.get("field_guidance")),
            empty="",
        )
        safety_risk = _fact_label(safety.get("risk_level") or "")
    elif safety:
        safety_note = _fact_label(safety)

    legal_note = ""
    trade_warning = ""
    legal_restrictions = ""
    vietnam_status_text = ""
    legal_basis = ""
    if isinstance(legal, dict):
        vietnam_status = legal.get("vietnam_status") or {}
        if isinstance(vietnam_status, dict):
            if vietnam_status.get("exact_match"):
                vietnam_status_text = _fact_label(vietnam_status.get("status") or "đã có exact match pháp lý Việt Nam")
            else:
                vietnam_status_text = _fact_label(
                    vietnam_status.get("status")
                    or "chưa có exact match pháp lý Việt Nam theo tên khoa học trong kho dữ liệu"
                )
        trade_warning = _fact_label(legal.get("trade_warning") or "")
        legal_restrictions = _list_to_text(
            _fact_values(
                legal.get("restrictions")
                or legal.get("vietnam_protection")
                or legal.get("legal_advice_disclaimer")
            ),
            empty="",
        )
        legal_basis = _fact_label(legal.get("basis") or "")
        legal_note = _list_to_text(
            _fact_values(
                legal.get("notes")
                or legal.get("status")
                or legal.get("restrictions")
                or legal.get("vietnam_protection")
                or legal.get("pet_suitability")
                or legal.get("legal_advice_disclaimer")
            ),
            empty="",
        )
    elif legal:
        legal_note = _fact_label(legal)

    legal_note = legal_restrictions or legal_note
    if not vietnam_status_text:
        vietnam_status_text = "chưa có exact match pháp lý Việt Nam theo tên khoa học trong kho dữ liệu"
    if not trade_warning:
        trade_warning = "Không nên suy ra giao dịch là hợp pháp nếu chưa kiểm tra văn bản hiện hành, nguồn gốc cá thể và giấy phép."
    if not safety_guidance:
        safety_guidance = "giữ khoảng cách, không tiếp xúc trực tiếp và báo kiểm lâm/đơn vị cứu hộ nếu cần xử lý"

    if (
        "buon ban" in normalized
        or "mua ban" in normalized
        or "trao doi" in normalized
        or "van chuyen" in normalized
        or "giay phep" in normalized
        or "hop phap" in normalized
        or "phap ly" in normalized
    ):
        lines = [
            f"**Pháp lý/buôn bán:** Mình không thể xem đây là tư vấn pháp lý. Với {label}, dữ liệu có thể kiểm tra hiện ghi IUCN: {iucn_category}, Sách đỏ Việt Nam: {vn_category}, CITES: {cites}.",
            f"Pháp lý Việt Nam theo loài: {vietnam_status_text}.",
            f"Cảnh báo giao dịch: {trade_warning}",
            f"Căn cứ cảnh báo trong kho: {legal_basis or f'IUCN {iucn_category}; Sách đỏ Việt Nam {vn_category}; CITES {cites}'}.",
            f"Nguyên tắc an toàn pháp lý: {legal_note or 'không khẳng định hợp pháp/không hợp pháp nếu chưa có exact match văn bản và giấy phép liên quan'}.",
            "Bạn nên kiểm tra văn bản pháp luật mới nhất và hỏi cơ quan kiểm lâm/cơ quan quản lý trước khi thực hiện bất kỳ giao dịch nào.",
        ]
    elif "thu cung" in normalized or "nuoi" in normalized:
        lines = [
            f"**Nuôi làm thú cưng:** Không nên xem {label} là thú cưng nếu đó là cá thể hoang dã hoặc loài có quản lý bảo tồn.",
            f"Dữ liệu bảo tồn hiện có: IUCN {iucn_category}, Sách đỏ Việt Nam {vn_category}, CITES {cites}; đe dọa chính: {threats}.",
            f"Pháp lý Việt Nam theo loài: {vietnam_status_text}.",
            f"Dữ liệu an toàn species-specific: {safety_note or venom_text}. Hướng dẫn thận trọng: {safety_guidance}.",
            "Nếu cần chăm sóc cá thể bị thương hoặc bị tịch thu, nên liên hệ trung tâm cứu hộ/cơ quan kiểm lâm thay vì tự nuôi.",
        ]
    elif "co doc" in normalized:
        lines = [
            f"**Độc/nguy hiểm:** Với {label}, {venom_text}.",
            f"Dữ liệu an toàn bổ sung: {safety_note or 'chưa có nguồn species-specific riêng về mức nguy hiểm với con người'}.",
            "Không nên chạm, bắt hoặc kích động cá thể ngoài tự nhiên; hãy giữ khoảng cách an toàn và liên hệ cơ quan chuyên môn nếu cần xử lý.",
        ]
    elif "gap" in normalized or "ngoai tu nhien" in normalized:
        lines = [
            f"**Khi gặp ngoài tự nhiên:** Hãy quan sát {label} từ xa, không đuổi bắt, không cho ăn, không đưa về nuôi và không đăng vị trí nhạy cảm nếu có nguy cơ săn bắt.",
            f"Dữ liệu bảo tồn để cảnh báo: IUCN {iucn_category}, Sách đỏ Việt Nam {vn_category}, CITES {cites}; đe dọa chính: {threats}.",
            f"Hướng dẫn an toàn: {safety_guidance}.",
            "Nếu cá thể bị thương, mắc bẫy hoặc xuất hiện trong khu dân cư, nên báo kiểm lâm/đơn vị cứu hộ địa phương.",
        ]
    else:
        lines = [
            f"**An toàn với con người:** Với {label}, {safety_note or venom_text}.",
            f"Mức cảnh báo trong kho: {safety_risk or 'thận trọng chung'}. Cách xử lý an toàn là {safety_guidance}.",
        ]

    _append_limit(lines, data_warnings)
    if not data_warnings:
        lines.append("**Giới hạn dữ liệu:** Câu trả lời này chỉ dùng dữ liệu có provenance trong kho; không thay thế tư vấn pháp lý/y tế hoặc hướng dẫn xử lý hiện trường.")
    return "\n\n".join(lines)


def _build_structured_focus_answer(
    species_name: str,
    profile: dict[str, Any],
    question_plan: dict[str, Any] | None,
    data_warnings: list[str],
) -> str | None:
    intents = _question_plan_intents(question_plan)
    if not profile or not intents or intents == ["general"]:
        return None

    label = _species_display_label(profile, species_name)
    question = _question_text_from_plan(question_plan)
    distribution = profile.get("distribution") or {}
    conservation = profile.get("conservation") or {}
    iucn = conservation.get("iucn") or {}
    vn_red = conservation.get("vietnam_red_data") or {}
    ecology = profile.get("ecology") or {}
    taxonomy = profile.get("taxonomy") or {}

    lines: list[str] = []
    for intent in intents:
        if intent == "name":
            common = _profile_common_vi(profile)
            scientific = _profile_scientific_name(profile, species_name)
            if common:
                lines.append(f"**Tên loài:** {label} có tên Việt là {common}; tên khoa học là *{scientific}*.")
            else:
                lines.append(f"**Tên loài:** Kho dữ liệu hiện chưa có tên Việt; tên khoa học là *{scientific}*.")
        elif intent == "scientific_name":
            scientific = _profile_scientific_name(profile, species_name)
            lines.append(f"**Tên khoa học:** *{scientific}*.")
        elif intent == "taxonomy":
            family = taxonomy.get("family") or "chưa rõ"
            order = taxonomy.get("order") or "chưa rõ"
            tax_class = taxonomy.get("class") or "chưa rõ"
            lines.append(f"**Phân loại:** {label} thuộc họ {family}; bộ {order}; lớp {tax_class}.")
        elif intent == "group":
            group = _profile_group_label(profile)
            lines.append(f"**Nhóm loài:** {label} thuộc nhóm {group}.")
        elif intent == "occurrence":
            countries = _profile_countries(profile)
            in_vietnam = any(_normalize_search_text(country) in {"viet nam", "vietnam"} for country in countries)
            if in_vietnam:
                lines.append(f"**Có ở Việt Nam:** Có. Dữ liệu ghi nhận {label} có phân bố tại Việt Nam.")
            elif countries:
                lines.append(f"**Có ở Việt Nam:** Chưa thấy dữ liệu ghi nhận Việt Nam; các quốc gia/khu vực trong dữ liệu: {_list_to_text(countries)}.")
            else:
                lines.append(_missing_answer(label, "Phân bố tại Việt Nam"))
        elif intent == "distribution":
            target = _target_region(question)
            countries = _list_to_text(_profile_countries(profile), empty="chưa rõ quốc gia")
            regions_list = _profile_regions(profile)
            localities_list = _profile_localities(profile)
            if target:
                if _matches_normalized(target, regions_list):
                    lines.append(f"**Phân bố:** Có. Dữ liệu ghi nhận {label} ở {target}.")
                elif regions_list:
                    lines.append(f"**Phân bố:** Chưa thấy dữ liệu ghi nhận {label} ở {target}. Vùng ghi nhận hiện có: {_list_to_text(regions_list)}.")
                else:
                    lines.append(_missing_answer(label, "Phân bố theo vùng"))
            else:
                regions = _list_to_text(regions_list, empty="chưa rõ vùng tại Việt Nam")
                localities = _list_to_text(localities_list, empty="chưa rõ tỉnh/khu vực cụ thể")
                lines.append(
                    f"**Phân bố:** {label} được ghi nhận ở {countries}. "
                    f"Tại Việt Nam, vùng ghi nhận gồm {regions}; khu vực/tỉnh dữ liệu đề cập: {localities}."
                )
        elif intent == "diet":
            diet_values = _fact_values(ecology.get("diet", []))
            diet = _list_to_text(
                diet_values,
                empty="kho dữ liệu hiện chưa có thông tin đủ về thức ăn",
            )
            if "con non" in _normalize_search_text(question) and diet_values:
                lines.append(f"**Thức ăn con non:** Kho dữ liệu hiện chưa tách riêng thức ăn con non; dữ liệu chung về thức ăn của loài là {diet}.")
            elif "san moi" in _normalize_search_text(question):
                if any(_normalize_search_text(item) in {"insects", "small mammals", "fish", "thit", "dong vat"} for item in diet_values):
                    lines.append(f"**Săn mồi/thức ăn:** Dữ liệu thức ăn có ghi nhận nhóm động vật/con mồi: {diet}.")
                elif diet_values:
                    lines.append(f"**Săn mồi/thức ăn:** Dữ liệu hiện ghi thức ăn chính là {diet}; chưa có bằng chứng cấu trúc rằng loài này săn mồi.")
                else:
                    lines.append(_missing_answer(label, "Tập tính săn mồi"))
            else:
                lines.append(f"**Thức ăn:** {diet}.")
        elif intent == "habitat":
            target = _target_habitat(question)
            habitat_values = _fact_values(ecology.get("habitat_tags", []))
            if target:
                if _matches_normalized(target, habitat_values):
                    lines.append(f"**Môi trường sống:** Có. Dữ liệu sinh cảnh của {label} có ghi {target}.")
                elif habitat_values:
                    lines.append(f"**Môi trường sống:** Chưa thấy dữ liệu ghi {label} sống ở {target}. Sinh cảnh hiện có: {_list_to_text(habitat_values)}.")
                else:
                    lines.append(_missing_answer(label, "Sinh cảnh"))
            else:
                habitats = _list_to_text(
                    habitat_values,
                    empty="kho dữ liệu hiện chưa có thông tin đủ về sinh cảnh",
                )
                lines.append(f"**Môi trường sống:** {habitats}.")
        elif intent == "altitude":
            altitude = ecology.get("elevation_m") or ecology.get("altitude_m") or ecology.get("elevation_range")
            if altitude:
                lines.append(f"**Độ cao:** Dữ liệu ghi nhận khoảng độ cao: {altitude}.")
            else:
                lines.append(_missing_answer(label, "Độ cao phân bố"))
        elif intent == "activity_time":
            activity = ecology.get("activity_time") or ecology.get("activity_pattern")
            if activity:
                lines.append(f"**Thời gian hoạt động:** {_fact_label(activity)}.")
            else:
                lines.append(_missing_answer(label, "Thời gian hoạt động"))
        elif intent == "conservation":
            question_norm = _normalize_search_text(question)
            category = iucn.get("category") or "không rõ"
            trend = _fact_label(iucn.get("population_trend")) or "chưa rõ"
            vn_category = vn_red.get("category") or "không rõ"
            cites = _format_cites_appendix(conservation.get("cites_appendix"))
            if "sach do" in question_norm:
                lines.append(f"**Sách đỏ Việt Nam:** {vn_category}.")
            elif "cites" in question_norm:
                lines.append(f"**CITES:** {cites}.")
            elif "tuyet chung" in question_norm or "nguy cap" in question_norm:
                lines.append(f"**Nguy cấp/bảo tồn:** IUCN: {category}; Sách đỏ Việt Nam: {vn_category}; CITES: {cites}.")
            else:
                threats = _list_to_text(
                    _fact_values(conservation.get("major_threats", [])),
                    empty="chưa rõ",
                )
                lines.append(
                    f"**Bảo tồn:** IUCN: {category}; xu hướng quần thể: {trend}. "
                    f"Sách đỏ Việt Nam: {vn_category}; CITES: {cites}. "
                    f"Đe dọa chính: {threats}."
                )
        elif intent == "threats":
            threats = _list_to_text(
                _fact_values(conservation.get("major_threats", [])),
                empty="kho dữ liệu hiện chưa có thông tin đủ về mối đe dọa",
            )
            lines.append(f"**Đe dọa chính:** {threats}.")
        elif intent == "population_trend":
            trend = _fact_label(iucn.get("population_trend")) or "chưa rõ"
            lines.append(f"**Xu hướng quần thể:** {trend}.")
        elif intent in {"safety", "legal"}:
            return _build_safety_legal_answer(question, label, profile, data_warnings)
        elif intent == "source":
            return _build_source_answer(species_name, profile, data_warnings)
        elif intent == "data_quality":
            if "chac chan nhat" in _normalize_search_text(question):
                return _build_confidence_answer(label, profile, data_warnings)
            return _build_data_quality_answer(label, data_warnings)
        elif intent == "behavior":
            lines.append(_missing_answer(label, "Tập tính/đặc điểm hành vi"))
        else:
            return None

    if "source" in intents:
        lines.append(f"**Nguồn dữ liệu:** {_profile_sources_text(profile)}.")
    _append_limit(lines, data_warnings)
    return "\n\n".join(lines)


def _build_species_raw_collection():
    try:
        client = MongoClient(RAG_MONGODB_URI, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client[RAG_MONGODB_DATABASE][RAG_SPECIES_RAW_COLLECTION]
    except Exception as exc:
        print(f"⚠️  Không thể kết nối MongoDB species_raw: {exc}")
        return None


def _find_raw_profile_by_species(species_name: str) -> dict[str, Any]:
    if SPECIES_RAW_COLLECTION is None:
        return {}

    target = (species_name or "").strip()
    if not target:
        return {}

    escaped = re.escape(target)
    query = {
        "$or": [
            {"scientific_name": {"$regex": f"^{escaped}$", "$options": "i"}},
            {
                "raw_profile.accepted_name.scientific": {
                    "$regex": f"^{escaped}$",
                    "$options": "i",
                }
            },
        ]
    }
    doc = SPECIES_RAW_COLLECTION.find_one(query, {"raw_profile": 1})
    if not doc:
        return {}
    return doc.get("raw_profile") or {}


def _structured_species_context(species_name: str) -> str:
    profile = _find_raw_profile_by_species(species_name)
    if not profile:
        return ""

    accepted = profile.get("accepted_name", {})
    taxonomy = profile.get("taxonomy", {})
    names = profile.get("names", {}).get("common", {})
    conservation = profile.get("conservation", {})
    iucn = conservation.get("iucn", {})
    vn_red = conservation.get("vietnam_red_data", {})
    distribution = profile.get("distribution", {})
    distribution_vn = distribution.get("vietnam", {})
    ecology = profile.get("ecology", {})
    provenance = profile.get("provenance", {})

    common_vi = _list_to_text(names.get("vi", []))
    common_en = _list_to_text(names.get("en", []))
    regions = _list_to_text(_normalize_region_values(distribution_vn.get("regions", [])))
    countries = _list_to_text(distribution.get("countries", []))
    habitats = _list_to_text(_fact_values(ecology.get("habitat_tags", [])))
    diet = _list_to_text(_fact_values(ecology.get("diet", [])))
    threats = _list_to_text(_fact_values(conservation.get("major_threats", [])))

    source_names = []
    for src in provenance.get("sources", []):
        name = str(src.get("name") or src.get("source") or "").strip()
        if name and name not in source_names:
            source_names.append(name)

    lines = [
        f"- Ten khoa hoc: {accepted.get('scientific', 'khong ro')}",
        f"- Ten thuong goi (VI): {common_vi}",
        f"- Ten thuong goi (EN): {common_en}",
        (
            "- Phan loai: "
            f"lop={taxonomy.get('class', 'khong ro')}, "
            f"bo={taxonomy.get('order', 'khong ro')}, "
            f"ho={taxonomy.get('family', 'khong ro')}, "
            f"chi={taxonomy.get('genus', 'khong ro')}"
        ),
        (
            "- IUCN: "
            f"{iucn.get('category', 'khong ro')} "
            f"(nam={iucn.get('year', 'khong ro')}, xu huong quan the={_fact_label(iucn.get('population_trend')) or 'khong ro'})"
        ),
        (
            "- Sach do Viet Nam: "
            f"{vn_red.get('category', 'khong ro')} "
            f"(nam={vn_red.get('year', 'khong ro')})"
        ),
        f"- CITES: {_format_cites_appendix(conservation.get('cites_appendix'), empty='khong ro')}",
        f"- Phan bo quoc gia: {countries}",
        f"- Phan bo tai Viet Nam (vung): {regions}",
        f"- Sinh canh: {habitats}",
        f"- Thuc an: {diet}",
        f"- De doa chinh: {threats}",
        f"- Nguon doi chieu: {_list_to_text(source_names)}",
    ]

    return "\n".join(lines)


# ============================================================
# LOAD
# ============================================================
print("📋 Loading RAG pipeline...")
embed_model = SentenceTransformer("keepitreal/vietnamese-sbert")
index = faiss.read_index(str(KB_DIR / "faiss_index.bin"))
metadata = json.load(open(KB_DIR / "chunks_metadata.json", encoding="utf-8"))
CHUNK_TOKENS = [_tokenize_search(_build_chunk_search_text(c)) for c in metadata]
SPECIES_RAW_COLLECTION = _build_species_raw_collection()

API_KEY = os.getenv("CEREBRAS_API_KEY", "").strip()
if not API_KEY:
    client = None
    print("⚠️  Thiếu CEREBRAS_API_KEY, sẽ chạy chế độ fallback (không gọi LLM API).")
else:
    client = Cerebras(api_key=API_KEY)
    print(f"✅ Ready! (provider: cerebras, model: {CEREBRAS_MODEL})\n")


# ============================================================
# RETRIEVE
# ============================================================
def retrieve(
    query: str, top_k: int = TOP_K, sci_name: str = "", alpha: float = ALPHA_ENTITY
) -> list[dict]:

    results = []
    seen = set()
    normalized_target = _normalize_sci_name(sci_name)

    # Bước 1: Nếu có sci_name → lấy trực tiếp các chunk của loài đó
    if normalized_target:
        for chunk in metadata:
            if _normalize_sci_name(chunk.get("sci_name", "")) == normalized_target:
                chunk = chunk.copy()
                chunk["score"] = 1.0  # exact match → score cao nhất
                key = (
                    chunk.get("sci_name", ""),
                    chunk.get("source", ""),
                    chunk.get("url", ""),
                    chunk.get("text", "")[:120],
                )
                if key not in seen:
                    seen.add(key)
                    results.append(chunk)
                if len(results) >= top_k // 2:  # lấy tối đa top_k/2 chunk của loài
                    break

    # Bước 2: Vector search cho phần còn lại
    remaining = top_k - len(results)
    if remaining > 0:
        query_tokens = _tokenize_search(query)
        vec = embed_model.encode([query], normalize_embeddings=True)
        scores, indices = index.search(
            np.array(vec, dtype=np.float32), max(top_k * 5, 10)
        )

        for sem_score, idx in zip(scores[0], indices[0]):
            lex_score = _lexical_score(query_tokens, CHUNK_TOKENS[idx])
            hybrid_score = alpha * float(sem_score) + (1.0 - alpha) * float(lex_score)

            # Keep weak semantic matches only if lexical signal is meaningful.
            if hybrid_score < MIN_HYBRID_SCORE or (
                sem_score < MIN_SCORE and lex_score < 0.2
            ):
                continue
            chunk = metadata[idx].copy()

            # Nếu đang hỏi một loài cụ thể, ưu tiên tuyệt đối đúng loài đó.
            # Tránh kéo thêm chunk của loài khác làm nguồn bị "lẫn".
            if normalized_target:
                chunk_sci = _normalize_sci_name(chunk.get("sci_name", ""))
                if chunk_sci and chunk_sci != normalized_target:
                    continue

            chunk["score"] = hybrid_score
            chunk["semantic_score"] = float(sem_score)
            chunk["lexical_score"] = float(lex_score)
            chunk["alpha"] = float(alpha)
            key = (
                chunk.get("sci_name", ""),
                chunk.get("source", ""),
                chunk.get("url", ""),
                chunk.get("text", "")[:120],
            )
            if key not in seen:
                seen.add(key)
                results.append(chunk)
            if len(results) >= top_k:
                break

    return results


INTENT_KEYWORDS = {
    "name": ["ten", "name", "accepted", "common"],
    "scientific_name": ["ten khoa hoc", "scientific", "accepted"],
    "taxonomy": ["phan loai", "taxonomy", "family", "order", "class"],
    "group": ["nhom", "class", "group"],
    "occurrence": ["vietnam", "viet nam", "countries", "range"],
    "diet": [
        "thuc an",
        "che do an",
        "an",
        "diet",
        "food",
        "prey",
        "feeding",
        "forage",
    ],
    "habitat": [
        "sinh canh",
        "moi truong song",
        "habitat",
        "forest",
        "wetland",
        "grassland",
        "river",
    ],
    "distribution": [
        "phan bo",
        "vung",
        "quoc gia",
        "vietnam",
        "range",
        "distribution",
        "locality",
    ],
    "conservation": [
        "iucn",
        "sach do",
        "bao ton",
        "nguy cap",
        "cites",
        "threat",
        "conservation",
    ],
    "threats": ["de doa", "threat", "habitat_loss", "illegal_trade"],
    "population_trend": ["population", "trend", "quan the"],
    "safety": ["danger", "venom", "doc", "nguy hiem", "encounter", "bi thuong", "mac bay", "cuu ho"],
    "legal": ["legal", "trade", "cites", "law", "buon ban", "mua ban", "trao doi", "van chuyen", "giay phep"],
    "source": [
        "nguon",
        "tham khao",
        "provenance",
        "source",
        "citation",
        "reference",
    ],
    "data_quality": ["unknown", "year", "provenance", "quality", "missing"],
    "altitude": ["elevation", "altitude", "do cao"],
    "activity_time": ["activity", "diurnal", "nocturnal", "ban ngay", "ban dem"],
    "behavior": [
        "tap tinh",
        "hanh vi",
        "sinh san",
        "behavior",
        "breeding",
        "activity",
    ],
}


def rerank_chunks(
    chunks: list[dict],
    question: str,
    sci_name: str = "",
    question_plan: dict[str, Any] | None = None,
    top_k: int = TOP_K,
) -> list[dict]:
    if not chunks:
        return []

    intents = _question_plan_intents(question_plan)
    if not intents:
        intents = ["source"] if _detect_source_query(question) else ["general"]

    normalized_question = _normalize_search_text(question)
    normalized_target = _normalize_sci_name(sci_name)

    reranked: list[dict] = []
    for index, chunk in enumerate(chunks):
        candidate = chunk.copy()
        text = _normalize_search_text(_build_chunk_search_text(candidate))
        score = float(candidate.get("score") or 0.0)
        boost = 0.0

        if normalized_target and _normalize_sci_name(candidate.get("sci_name", "")) == normalized_target:
            boost += 0.35

        for intent in intents:
            keywords = INTENT_KEYWORDS.get(intent, [])
            if any(keyword in text for keyword in keywords):
                boost += 0.18

        question_tokens = _tokenize_search(normalized_question)
        chunk_tokens = _tokenize_search(text)
        boost += min(_lexical_score(question_tokens, chunk_tokens), 0.25)

        if normalized_target and _normalize_sci_name(candidate.get("sci_name", "")) != normalized_target:
            boost -= 0.25

        candidate["rerank_score"] = score + boost
        candidate["rerank_boost"] = boost
        candidate["retrieval_rank"] = index + 1
        reranked.append(candidate)

    reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
    return reranked[:top_k]


# ============================================================
# BUILD PROMPT
# ============================================================
SYSTEM_PROMPT = """Bạn là chuyên gia về động vật hoang dã Việt Nam.
Nhiệm vụ: trả lời đúng trọng tâm câu hỏi, đầy đủ thông tin, có cấu trúc rõ ràng.

Yêu cầu bắt buộc:
1) Chỉ sử dụng dữ liệu trong phần THÔNG TIN THAM KHẢO, không bịa thêm.
2) Trả lời bằng tiếng Việt, mạch lạc, ưu tiên thông tin thực chứng.
3) Tránh lan man; mọi đoạn đều phải liên quan trực tiếp đến câu hỏi.
4) Nếu dữ liệu thiếu hoặc chưa chắc chắn, phải ghi rõ giới hạn dữ liệu.
5) Khi phù hợp, nêu tên khoa học, mức bảo tồn, phân bố, mối đe dọa và nguồn gốc thông tin.
6) Khi nêu bằng chứng, tham chiếu nguồn theo nhãn [Nguồn i] có trong phần THÔNG TIN THAM KHẢO.
7) Ưu tiên sử dụng dữ liệu cấu trúc (fact) trước, sau đó mới bổ sung diễn giải từ văn bản narrative.
"""


def _strip_control_prefix(question: str) -> str:
    return re.sub(r"^\[(?:FOCUS|INTENTS):[^\]]+\]\s*", "", question or "").strip()


def _question_plan_intents(question_plan: dict[str, Any] | None) -> list[str]:
    if not isinstance(question_plan, dict):
        return []
    intents = []
    for item in question_plan.get("intents") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in intents:
            intents.append(name)
    return intents


def _intent_title(intent: str) -> str:
    return {
        "name": "Tên loài",
        "scientific_name": "Tên khoa học",
        "taxonomy": "Phân loại",
        "group": "Nhóm loài",
        "occurrence": "Có ở Việt Nam",
        "distribution": "Phân bố",
        "diet": "Thức ăn",
        "habitat": "Môi trường sống",
        "altitude": "Độ cao",
        "activity_time": "Thời gian hoạt động",
        "conservation": "Bảo tồn",
        "threats": "Đe dọa",
        "population_trend": "Xu hướng quần thể",
        "safety": "An toàn",
        "legal": "Pháp lý",
        "source": "Nguồn dữ liệu",
        "data_quality": "Chất lượng dữ liệu",
        "behavior": "Tập tính",
        "general": "Trả lời",
    }.get(intent, intent)


def _intent_description(intent: str) -> str:
    return {
        "name": "trả lời tên Việt/tên thường gọi của loài",
        "scientific_name": "trả lời tên khoa học",
        "taxonomy": "trả lời họ/bộ/lớp hoặc phân loại học",
        "group": "trả lời nhóm chim/thú/bò sát/lưỡng cư/cá",
        "occurrence": "trả lời loài có được ghi nhận ở Việt Nam hay không",
        "distribution": "trả lời nơi phân bố/quốc gia/vùng/tỉnh/khu vực ghi nhận",
        "diet": "trả lời thức ăn hoặc chế độ ăn",
        "habitat": "trả lời kiểu sinh cảnh/môi trường sống",
        "altitude": "trả lời độ cao phân bố nếu có dữ liệu",
        "activity_time": "trả lời thời gian hoạt động nếu có dữ liệu",
        "conservation": "trả lời IUCN, Sách đỏ Việt Nam, CITES hoặc nguy cơ bảo tồn",
        "threats": "trả lời các mối đe dọa chính",
        "population_trend": "trả lời xu hướng quần thể",
        "safety": "trả lời thận trọng về an toàn khi gặp/tiếp xúc",
        "legal": "trả lời thận trọng về pháp lý, không thay thế tư vấn pháp lý",
        "source": "trả lời nguồn dữ liệu, provenance hoặc bằng chứng truy xuất",
        "data_quality": "trả lời phần dữ liệu thiếu/chưa rõ hoặc chắc chắn nhất",
        "behavior": "trả lời tập tính, hoạt động, sinh sản hoặc đặc điểm hành vi",
        "general": "trả lời trực tiếp câu hỏi",
    }.get(intent, "trả lời đúng ý này")


def _build_question_plan_instruction(question_plan: dict[str, Any] | None) -> str | None:
    intents = _question_plan_intents(question_plan)
    if not intents or intents == ["general"]:
        return None

    forbidden = []
    if isinstance(question_plan, dict):
        forbidden = [
            str(item).strip()
            for item in question_plan.get("forbidden_sections") or []
            if str(item).strip()
        ]

    lines = [
        "Nhiệm vụ: trả lời đúng các ý người dùng hỏi, không mở rộng sang chủ đề khác.",
        "",
        "Các ý cần trả lời theo đúng thứ tự:",
    ]
    for index, intent in enumerate(intents, 1):
        lines.append(f"{index}. {intent} - {_intent_description(intent)}.")

    lines.extend(
        [
            "",
            "Ràng buộc:",
            "- Chỉ dùng dữ liệu trong THÔNG TIN THAM KHẢO và FACT CẤU TRÚC ƯU TIÊN.",
            "- Mỗi mục tối đa 2-3 câu.",
            "- Nếu thiếu dữ liệu cho mục nào, nói rõ kho dữ liệu hiện chưa có thông tin đủ.",
            "- Không viết tổng quan dài trước các mục chính.",
        ]
    )

    if forbidden:
        lines.append(f"- Không tự thêm các chủ đề ngoài phạm vi: {', '.join(forbidden)}.")

    lines.extend(["", "Định dạng bắt buộc:"])
    for intent in intents:
        lines.append(f"**{_intent_title(intent)}:** ...")
    lines.append("**Giới hạn dữ liệu:** ... (chỉ ghi nếu có phần thiếu/chưa chắc)")
    return "\n".join(lines)


def build_prompt(
    question: str,
    chunks: list[dict],
    species_context: str = "",
    question_plan: dict[str, Any] | None = None,
    data_warnings: list[str] | None = None,
) -> str:
    context_parts = []
    structured_block = ""

    if species_context:
        context_parts.append(f"[Loài đang xem xét: {species_context}]")
        structured_block = _structured_species_context(species_context)

    for i, chunk in enumerate(chunks, 1):
        label = chunk["sci_name"] or chunk["common_name"] or "Thông tin chung"
        context_parts.append(f"[Nguồn {i} - {label}]\n{chunk['text']}")

    context = "\n\n".join(context_parts)

    planned_instruction = _build_question_plan_instruction(question_plan)

    if planned_instruction:
        answer_instruction = planned_instruction
    elif ANSWER_STYLE == "detailed":
        answer_instruction = """
Định dạng trả lời mong muốn (chi tiết):
- **Tổng quan nhanh**: 2-3 câu trả lời trực diện câu hỏi.
- **Thông tin chi tiết theo đúng trọng tâm câu hỏi**.
- **Bảo tồn và tình trạng**: IUCN, Sách đỏ Việt Nam, CITES (nếu có dữ liệu).
- **Phân bố và sinh cảnh**: quốc gia, vùng tại Việt Nam, sinh cảnh.
- **Đe dọa chính và hàm ý bảo tồn**.
- **Bằng chứng dữ liệu**: liệt kê 4-8 gạch đầu dòng từ FACT/nguồn truy xuất.
- **Kết luận ngắn**: tóm ý chính và nêu độ chắc chắn dữ liệu.

Độ dài mục tiêu: 260-450 từ nếu dữ liệu đủ; nếu thiếu dữ liệu thì vẫn giữ cấu trúc trên và ghi rõ giới hạn.
""".strip()
    else:
        answer_instruction = """
Định dạng trả lời mong muốn (ngắn gọn):
- Trả lời trực tiếp 1-2 đoạn ngắn.
- Nêu dữ kiện quan trọng nhất.
- Báo rõ nếu thiếu dữ liệu.
""".strip()

    structured_section = (
        f"=== FACT CẤU TRÚC ƯU TIÊN ===\n{structured_block}\n\n"
        if structured_block
        else ""
    )
    warnings_section = ""
    if data_warnings:
        warnings_section = (
            "=== CẢNH BÁO CHẤT LƯỢNG DỮ LIỆU ===\n"
            + "\n".join(f"- {warning}" for warning in data_warnings)
            + "\n\n"
            + "Không được viết 'Giới hạn dữ liệu: Không có'. "
            + "Phải nêu các giới hạn này nếu câu trả lời dùng đến dữ liệu liên quan.\n\n"
        )

    return f"""{SYSTEM_PROMPT}

{structured_section}
{warnings_section}

=== THÔNG TIN THAM KHẢO ===
{context}

=== CÂU HỎI ===
{question}

=== HƯỚNG DẪN TRÌNH BÀY ===
{answer_instruction}

=== TRẢ LỜI ==="""


def _extract_retry_seconds(err_msg: str, default_wait: int = 3) -> int:
    # Ưu tiên parse "retry in 40.1s" hoặc "retryDelay': '40s'"
    patterns = [r"retry in\s*([0-9]+(?:\.[0-9]+)?)s", r"retryDelay[^0-9]*([0-9]+)s"]
    for pat in patterns:
        m = re.search(pat, err_msg, flags=re.IGNORECASE)
        if m:
            try:
                return max(0, int(float(m.group(1))))
            except ValueError:
                pass
    return default_wait


def _build_fallback_answer(
    question: str, chunks: list[dict], species_name: str = ""
) -> str:
    lines = [
        "Mình chưa gọi được mô hình sinh câu trả lời trong thời gian cho phép, nên chỉ trả lời tạm từ dữ liệu truy xuất gần nhất.",
    ]
    if species_name:
        lines.append(f"**Loài đang xét:** {species_name}.")
    lines.append("")
    lines.append("**Dữ liệu liên quan:**")

    if not chunks:
        lines.append("- Không có đoạn truy xuất đủ gần để tóm tắt.")
    for i, c in enumerate(chunks[:3], 1):
        label = c.get("sci_name") or c.get("common_name") or "Thông tin chung"
        text = " ".join((c.get("text") or "").split())
        lines.append(f"{i}. [{label}] {text[:220]}{'...' if len(text) > 220 else ''}")

    lines.append("")
    lines.append(
        "**Giới hạn dữ liệu:** Đây là phản hồi fallback do generation chậm/lỗi, không phải câu trả lời đầy đủ; nên chạy lại hoặc xem debug sources để kiểm tra bằng chứng."
    )
    return "\n".join(lines)


def _generate_answer_with_retry(prompt: str) -> str:
    if client is None:
        raise RuntimeError("CEREBRAS_API_KEY is missing")

    last_error = None
    for attempt in range(MAX_API_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=CEREBRAS_MODEL,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            last_error = exc
            msg = str(exc).lower()
            quota_hit = (
                "429" in msg or "resource_exhausted" in msg or "rate limit" in msg
            )
            if not quota_hit:
                break
            if attempt >= MAX_API_RETRIES:
                break
            wait_s = min(
                _extract_retry_seconds(msg, default_wait=MAX_RETRY_WAIT_SECONDS),
                MAX_RETRY_WAIT_SECONDS,
            )
            if wait_s <= 0:
                continue
            print(f"⏳ API quota/rate-limit, chờ {wait_s}s rồi thử lại...")
            time.sleep(wait_s)
    raise last_error


def _generate_answer_with_timeout(prompt: str) -> str:
    if GENERATION_TIMEOUT_SECONDS <= 0:
        return _generate_answer_with_retry(prompt)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_generate_answer_with_retry, prompt)
    try:
        return future.result(timeout=GENERATION_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError(
            f"generation exceeded {GENERATION_TIMEOUT_SECONDS:g}s"
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


# ============================================================
# RAG QUERY
# ============================================================
def rag_query(
    question: str, species_name: str = "", question_plan: dict[str, Any] | None = None
) -> dict:
    total_started = time.perf_counter()
    clean_question = _strip_control_prefix(question)
    intents = _question_plan_intents(question_plan)
    search_query = clean_question
    is_source_query = _detect_source_query(clean_question)
    is_facet = not species_name and _detect_facet_query(clean_question)
    alpha = ALPHA_FACET if is_facet else ALPHA_ENTITY
    profile = "source" if is_source_query and species_name else ("facet" if is_facet else "entity")
    species_profile = _find_raw_profile_by_species(species_name) if species_name else {}
    data_warnings = (
        _data_warnings_from_profile(species_profile, intents=intents)
        if species_name
        else []
    )

    retrieve_started = time.perf_counter()
    raw_chunks = retrieve(
        search_query,
        top_k=max(TOP_K * 3, 12),
        sci_name=species_name,
        alpha=alpha,
    )
    chunks = rerank_chunks(
        raw_chunks,
        clean_question,
        sci_name=species_name,
        question_plan=question_plan,
        top_k=TOP_K,
    )
    retrieve_ms = int((time.perf_counter() - retrieve_started) * 1000)

    evidence = _build_evidence_items(
        chunks,
        question_plan=question_plan,
        profile=species_profile,
    )

    sources = []
    for c in chunks:
        label = c.get("source") or c.get("sci_name") or c.get("common_name")
        if label and label not in sources:
            sources.append(label)
    source_quality = _source_quality_summary(sources, species_profile)
    retrieval_warnings = _retrieval_warnings(chunks, species_name)

    if is_source_query and species_name:
        answer = _build_source_answer(species_name, species_profile, data_warnings)
        provenance_sources = [
            item["name"] for item in _provenance_sources(species_profile) if item.get("name")
        ]
        if provenance_sources:
            sources = provenance_sources
        source_quality = _source_quality_summary(sources, species_profile)
        return {
            "answer": answer,
            "sources": sources,
            "source_quality": source_quality,
            "chunks": chunks,
            "evidence": evidence,
            "score": chunks[0]["score"] if chunks else 0,
            "fallback": False,
            "retrieval_profile": "source_evidence",
            "retrieval_alpha": alpha,
            "data_warnings": data_warnings,
            "timings_ms": {
                "retrieve": retrieve_ms,
                "generation": 0,
                "total": int((time.perf_counter() - total_started) * 1000),
            },
            "direct_answer": True,
            "flow": "source_evidence",
            "retrieval_warnings": retrieval_warnings,
            "coverage_warnings": _coverage_warnings(answer),
        }

    structured_answer = _build_structured_focus_answer(
        species_name,
        species_profile,
        question_plan,
        data_warnings,
    )
    if structured_answer:
        provenance_sources = [
            item["name"] for item in _provenance_sources(species_profile) if item.get("name")
        ]
        if provenance_sources:
            sources = provenance_sources
        source_quality = _source_quality_summary(sources, species_profile)
        if "data_quality" in intents or any(
            signal in _normalize_search_text(clean_question)
            for signal in ("chac chan nhat", "con thieu", "chua ro")
        ):
            direct_flow = "data_quality"
        elif any(intent in {"safety", "legal"} for intent in intents):
            direct_flow = "safety_legal"
        elif "source" in intents:
            direct_flow = "source_evidence"
        else:
            direct_flow = "species_structured"
        return {
            "answer": structured_answer,
            "sources": sources,
            "source_quality": source_quality,
            "chunks": chunks,
            "evidence": evidence,
            "score": chunks[0]["score"] if chunks else 0,
            "fallback": False,
            "retrieval_profile": direct_flow,
            "retrieval_alpha": alpha,
            "data_warnings": data_warnings,
            "timings_ms": {
                "retrieve": retrieve_ms,
                "generation": 0,
                "total": int((time.perf_counter() - total_started) * 1000),
            },
            "direct_answer": True,
            "flow": direct_flow,
            "retrieval_warnings": retrieval_warnings,
            "coverage_warnings": _coverage_warnings(structured_answer),
        }

    if not chunks:
        return {
            "answer": "Xin lỗi, tôi không tìm được thông tin liên quan.",
            "sources": [],
            "source_quality": [],
            "chunks": [],
            "evidence": [],
            "fallback": False,
            "retrieval_profile": profile,
            "retrieval_alpha": alpha,
            "data_warnings": data_warnings,
            "timings_ms": {
                "retrieve": retrieve_ms,
                "generation": 0,
                "total": int((time.perf_counter() - total_started) * 1000),
            },
            "flow": "rag",
            "retrieval_warnings": [],
            "coverage_warnings": [],
        }

    prompt = build_prompt(
        clean_question,
        chunks,
        species_context=species_name,
        question_plan=question_plan,
        data_warnings=data_warnings,
    )
    used_fallback = False
    generation_started = time.perf_counter()
    generation_error = None
    try:
        answer = _generate_answer_with_timeout(prompt)
    except Exception as exc:
        # Khi hết quota free hoặc rate-limit kéo dài, không cho pipeline crash.
        print(f"⚠️  Generation API unavailable: {exc}")
        answer = _build_fallback_answer(question, chunks, species_name)
        used_fallback = True
        generation_error = f"{type(exc).__name__}: {exc}"
    generation_ms = int((time.perf_counter() - generation_started) * 1000)

    return {
        "answer": answer,
        "sources": sources,
        "source_quality": source_quality,
        "chunks": chunks,
        "evidence": evidence,
        "score": chunks[0]["score"] if chunks else 0,
        "fallback": used_fallback,
        "retrieval_profile": profile,
        "retrieval_alpha": alpha,
        "data_warnings": data_warnings,
        "timings_ms": {
            "retrieve": retrieve_ms,
            "generation": generation_ms,
            "total": int((time.perf_counter() - total_started) * 1000),
        },
        "generation_error": generation_error,
        "flow": "rag",
        "retrieval_warnings": retrieval_warnings,
        "coverage_warnings": _coverage_warnings(answer),
    }


# ============================================================
# TEST
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vietnam Wildlife RAG")
    parser.add_argument("--species", default="", help="Tên khoa học loài (optional)")
    parser.add_argument("--question", default="", help="Câu hỏi cần trả lời")
    args = parser.parse_args()

    if args.question.strip():
        species = args.species.strip()
        question = args.question.strip()
        print(f"{'='*60}")
        print(f"🐾 Loài   : {species or 'không xác định'}")
        print(f"❓ Hỏi    : {question}")
        result = rag_query(question, species_name=species)
        print(f"💬 Trả lời:\n{result['answer']}")
        print(
            f"🔎 Retrieval: {result.get('retrieval_profile', 'unknown')} "
            f"(alpha={result.get('retrieval_alpha', 0):.2f})"
        )
        print(f"📚 Nguồn  : {', '.join(result['sources'])}")
        print()
    else:
        tests = [
            ("Halcyon smyrnensis", "Con chim này ăn gì và sống ở đâu?"),
            ("Calloselasma rhodostoma", "Rắn này có độc không? Nguy hiểm thế nào?"),
            ("", "Những loài động vật nào ở Việt Nam đang bị đe dọa tuyệt chủng?"),
            ("", "Sách đỏ Việt Nam là gì?"),
        ]

        for species, question in tests:
            print(f"{'='*60}")
            print(f"🐾 Loài   : {species or 'không xác định'}")
            print(f"❓ Hỏi    : {question}")
            result = rag_query(question, species_name=species)
            print(f"💬 Trả lời:\n{result['answer']}")
            print(
                f"🔎 Retrieval: {result.get('retrieval_profile', 'unknown')} "
                f"(alpha={result.get('retrieval_alpha', 0):.2f})"
            )
            print(f"📚 Nguồn  : {', '.join(result['sources'])}")
            print()
