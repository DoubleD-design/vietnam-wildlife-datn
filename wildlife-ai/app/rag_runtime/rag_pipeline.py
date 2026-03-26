# rag_pipeline.py
import json
import os
import re
import time
import argparse
import unicodedata
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
TOP_K = 4
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


def _build_species_raw_collection():
    try:
        client = MongoClient(RAG_MONGODB_URI, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client[RAG_MONGODB_DATABASE][RAG_SPECIES_RAW_COLLECTION]
    except Exception as exc:
        print(f"⚠️  Không thể kết nối MongoDB species_raw: {exc}")
        return None


def _find_raw_profile_by_species(species_name: str) -> dict[str, Any]:
    if not SPECIES_RAW_COLLECTION:
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
    regions = _list_to_text(distribution_vn.get("regions", []))
    countries = _list_to_text(distribution.get("countries", []))
    habitats = _list_to_text(ecology.get("habitat_tags", []))
    threats = _list_to_text(conservation.get("major_threats", []))

    source_names = []
    for src in provenance.get("sources", []):
        name = str(src.get("name") or "").strip()
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
            f"(nam={iucn.get('year', 'khong ro')}, xu huong quan the={iucn.get('population_trend', 'khong ro')})"
        ),
        (
            "- Sach do Viet Nam: "
            f"{vn_red.get('category', 'khong ro')} "
            f"(nam={vn_red.get('year', 'khong ro')})"
        ),
        f"- CITES: Appendix {conservation.get('cites_appendix', 'khong ro')}",
        f"- Phan bo quoc gia: {countries}",
        f"- Phan bo tai Viet Nam (vung): {regions}",
        f"- Sinh canh: {habitats}",
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
    raise SystemExit(
        "Thiếu CEREBRAS_API_KEY. Hãy set env var trước khi chạy, ví dụ:\n"
        "export CEREBRAS_API_KEY='your_key'"
    )
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
6) Uu tien su dung du lieu cau truc (fact) truoc, sau do moi bo sung dien giai tu van ban narrative.
"""


def build_prompt(question: str, chunks: list[dict], species_context: str = "") -> str:
    context_parts = []
    structured_block = ""

    if species_context:
        context_parts.append(f"[Loài đang xem xét: {species_context}]")
        structured_block = _structured_species_context(species_context)

    for i, chunk in enumerate(chunks, 1):
        label = chunk["sci_name"] or chunk["common_name"] or "Thông tin chung"
        context_parts.append(f"[Nguồn {i} - {label}]\n{chunk['text']}")

    context = "\n\n".join(context_parts)

    if ANSWER_STYLE == "detailed":
        answer_instruction = """
Định dạng trả lời mong muốn (chi tiết):
- Tong quan nhanh: 2-3 cau tra loi truc dien cau hoi.
- Thong tin chi tiet theo dung trong tam cau hoi.
- Bao ton va tinh trang: IUCN, Sach do Viet Nam, CITES (neu co du lieu).
- Phan bo va sinh canh: quoc gia, vung tai Viet Nam, sinh canh.
- De doa chinh va ham y bao ton.
- Bang chung du lieu: liet ke 4-8 gach dau dong tu FACT/nguon truy xuat.
- Ket luan ngan: tom y chinh va neu do chac chan du lieu.

Do dai muc tieu: 260-450 tu neu du lieu du; neu thieu du lieu thi van giu cau truc tren va ghi ro gioi han.
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

    return f"""{SYSTEM_PROMPT}

{structured_section}

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
        "Hiện API sinh câu trả lời đang tạm thời không khả dụng, nên tôi trả lời tạm dựa trực tiếp trên kho tri thức nội bộ.",
    ]
    if species_name:
        lines.append(f"Loài đang xét: {species_name}")
        structured = _structured_species_context(species_name)
        if structured:
            lines.append("")
            lines.append("FACT cấu trúc ưu tiên:")
            lines.append(structured)
    lines.append(f"Câu hỏi: {question}")
    lines.append("")
    lines.append("Tóm tắt trọng tâm:")
    lines.append(
        "- Dưới đây là các dữ kiện liên quan trực tiếp được trích từ các đoạn truy xuất tốt nhất."
    )
    lines.append("")
    lines.append("Thông tin chi tiết từ nguồn nội bộ:")

    for i, c in enumerate(chunks[:5], 1):
        label = c.get("sci_name") or c.get("common_name") or "Thông tin chung"
        text = " ".join((c.get("text") or "").split())
        lines.append(f"{i}. [{label}] {text[:320]}{'...' if len(text) > 320 else ''}")

    lines.append("")
    lines.append(
        "Lưu ý: Đây là phản hồi fallback nên văn phong có thể kém tự nhiên hơn chế độ sinh câu trả lời đầy đủ."
    )
    return "\n".join(lines)


def _generate_answer_with_retry(prompt: str) -> str:
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


# ============================================================
# RAG QUERY
# ============================================================
def rag_query(question: str, species_name: str = "") -> dict:
    search_query = f"{question}"
    is_facet = not species_name and _detect_facet_query(question)
    alpha = ALPHA_FACET if is_facet else ALPHA_ENTITY
    profile = "facet" if is_facet else "entity"

    chunks = retrieve(search_query, top_k=TOP_K, sci_name=species_name, alpha=alpha)

    if not chunks:
        return {
            "answer": "Xin lỗi, tôi không tìm được thông tin liên quan.",
            "sources": [],
            "chunks": [],
            "fallback": False,
            "retrieval_profile": profile,
            "retrieval_alpha": alpha,
        }

    prompt = build_prompt(question, chunks, species_context=species_name)
    used_fallback = False
    try:
        answer = _generate_answer_with_retry(prompt)
    except Exception as exc:
        # Khi hết quota free hoặc rate-limit kéo dài, không cho pipeline crash.
        print(f"⚠️  Generation API unavailable: {exc}")
        answer = _build_fallback_answer(question, chunks, species_name)
        used_fallback = True

    sources = []
    for c in chunks:
        label = c["sci_name"] or c["common_name"]
        if label and label not in sources:
            sources.append(label)

    return {
        "answer": answer,
        "sources": sources,
        "chunks": chunks,
        "score": chunks[0]["score"] if chunks else 0,
        "fallback": used_fallback,
        "retrieval_profile": profile,
        "retrieval_alpha": alpha,
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
