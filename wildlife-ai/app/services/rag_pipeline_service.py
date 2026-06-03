from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings

OUT_OF_SCOPE_MESSAGE = "Mình chưa thể trả lời câu hỏi này vì nội dung vượt ngoài phạm vi dữ liệu hiện có của mình."
RAG_UNAVAILABLE_MESSAGE = (
    "Hệ thống RAG hiện chưa sẵn sàng nên mình chưa thể truy xuất kho tri thức. "
    "Vui lòng kiểm tra trạng thái RAG hoặc thử lại sau khi AI server được khởi động lại."
)
logger = logging.getLogger(__name__)


@dataclass
class RagAnswerResult:
    status: str
    answer: str
    error: str | None = None
    raw: dict[str, Any] | None = None


class RagPipelineService:
    _shared_rag_query_func = None
    _shared_load_error: str | None = None
    _shared_last_query_error: str | None = None
    _shared_resolved_rag_dir: Path | None = None
    _shared_load_lock = threading.Lock()

    def __init__(self) -> None:
        self._rag_query_func = self.__class__._shared_rag_query_func
        self._load_error: str | None = self.__class__._shared_load_error
        self._last_query_error: str | None = self.__class__._shared_last_query_error

    def answer(self, question: str, species_scientific_name: str = "") -> str:
        return self.answer_result(question, species_scientific_name).answer

    def answer_result(
        self,
        question: str,
        species_scientific_name: str = "",
        question_plan: dict[str, Any] | None = None,
    ) -> RagAnswerResult:
        rag_query = self._ensure_loaded()
        if rag_query is None:
            if self._load_error:
                logger.error("RAG load failed: %s", self._load_error)
            return RagAnswerResult(
                status="RAG_UNAVAILABLE",
                answer=RAG_UNAVAILABLE_MESSAGE,
                error=self._load_error,
            )

        try:
            result = rag_query(
                question,
                species_name=(species_scientific_name or "").strip(),
                question_plan=question_plan,
            )
            answer = (result or {}).get("answer")
            if isinstance(answer, str) and answer.strip():
                self._last_query_error = None
                self.__class__._shared_last_query_error = None
                return RagAnswerResult(
                    status="ANSWERED",
                    answer=answer.strip(),
                    raw=result if isinstance(result, dict) else None,
                )

            self._last_query_error = "rag_query returned no answer"
            self.__class__._shared_last_query_error = self._last_query_error
            return RagAnswerResult(
                status="RAG_UNAVAILABLE",
                answer=RAG_UNAVAILABLE_MESSAGE,
                error=self._last_query_error,
                raw=result if isinstance(result, dict) else None,
            )
        except Exception as exc:
            self._last_query_error = f"{type(exc).__name__}: {exc}"
            self.__class__._shared_last_query_error = self._last_query_error
            logger.exception("RAG query error: %s", exc)
            return RagAnswerResult(
                status="RAG_UNAVAILABLE",
                answer=RAG_UNAVAILABLE_MESSAGE,
                error=self._last_query_error,
            )

    def _ensure_loaded(self):
        if self._rag_query_func is not None:
            return self._rag_query_func

        with self.__class__._shared_load_lock:
            if self.__class__._shared_rag_query_func is not None:
                self._rag_query_func = self.__class__._shared_rag_query_func
                self._load_error = self.__class__._shared_load_error
                return self._rag_query_func

            # Avoid reloading on every request after a known fatal load error.
            if self.__class__._shared_load_error is not None:
                self._load_error = self.__class__._shared_load_error
                return None

            try:
                # rag_pipeline reads configuration from os.environ directly.
                # Mirror pydantic settings into process env before import.
                if settings.cerebras_api_key:
                    os.environ.setdefault("CEREBRAS_API_KEY", settings.cerebras_api_key)
                if settings.cerebras_model:
                    os.environ.setdefault("CEREBRAS_MODEL", settings.cerebras_model)
                if settings.cerebras_api_url:
                    os.environ.setdefault("CEREBRAS_API_URL", settings.cerebras_api_url)
                os.environ.setdefault("MONGODB_URI", settings.mongodb_uri)
                os.environ.setdefault("MONGODB_DATABASE", settings.mongodb_database)
                os.environ.setdefault(
                    "MONGODB_SPECIES_RAW_COLLECTION",
                    settings.mongodb_species_raw_collection,
                )
                os.environ.setdefault(
                    "RAG_MAX_API_RETRIES", str(settings.rag_max_api_retries)
                )
                os.environ.setdefault(
                    "RAG_MAX_RETRY_WAIT_SECONDS",
                    str(settings.rag_max_retry_wait_seconds),
                )
                os.environ.setdefault(
                    "RAG_GENERATION_TIMEOUT_SECONDS",
                    str(settings.rag_generation_timeout_seconds),
                )
                os.environ.setdefault("RAG_TOP_K", str(settings.rag_top_k))
                if settings.hf_home:
                    os.environ.setdefault("HF_HOME", settings.hf_home)
                if settings.hf_hub_offline:
                    os.environ.setdefault("HF_HUB_OFFLINE", settings.hf_hub_offline)
                if settings.hf_token:
                    os.environ.setdefault("HF_TOKEN", settings.hf_token)
                    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", settings.hf_token)

                rag_dir = self._resolve_rag_dir()
                if not rag_dir.exists():
                    self._load_error = f"RAG directory not found: {rag_dir}"
                    self.__class__._shared_load_error = self._load_error
                    return None

                if str(rag_dir) not in sys.path:
                    sys.path.insert(0, str(rag_dir))

                # rag_pipeline.py reads relative knowledge_base paths during import,
                # so we import it with cwd set to the RAG project once.
                original_cwd = Path.cwd()
                try:
                    os.chdir(rag_dir)
                    module = importlib.import_module("rag_pipeline")
                finally:
                    os.chdir(original_cwd)

                self._rag_query_func = getattr(module, "rag_query", None)
                if self._rag_query_func is None:
                    self._load_error = "rag_query not found in rag_pipeline"
                    self.__class__._shared_load_error = self._load_error
                    return None

                self.__class__._shared_rag_query_func = self._rag_query_func
                self.__class__._shared_load_error = None
                self.__class__._shared_resolved_rag_dir = rag_dir

                return self._rag_query_func
            except BaseException as exc:
                self._load_error = f"{type(exc).__name__}: {exc}"
                self.__class__._shared_load_error = self._load_error
                logger.error(
                    "RAG load failed: %s\n%s",
                    self._load_error,
                    traceback.format_exc(),
                )
                return None

    def _resolve_rag_dir(self) -> Path:
        configured = Path(settings.rag_project_dir).expanduser()
        candidates: list[Path] = []
        if configured.is_absolute():
            candidates.append(configured)
        else:
            service_file = Path(__file__).resolve()
            wildlife_ai_root = service_file.parents[2]
            app_root = service_file.parents[1]
            candidates.extend(
                [
                    Path.cwd() / configured,
                    wildlife_ai_root / configured,
                    app_root / configured,
                ]
            )

        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists():
                self.__class__._shared_resolved_rag_dir = resolved
                return resolved

        resolved = candidates[0].resolve() if candidates else configured.resolve()
        self.__class__._shared_resolved_rag_dir = resolved
        return resolved

    def health(self, load: bool = False) -> dict[str, Any]:
        rag_dir = self.__class__._shared_resolved_rag_dir or self._resolve_rag_dir()
        kb_dir = rag_dir / "knowledge_base"
        index_path = kb_dir / "faiss_index.bin"
        metadata_path = kb_dir / "chunks_metadata.json"

        if load:
            self._ensure_loaded()

        metadata_count: int | str | None = None
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(metadata, list):
                    metadata_count = len(metadata)
            except Exception as exc:
                metadata_count = f"unreadable: {type(exc).__name__}: {exc}"

        return {
            "status": "ok" if self.__class__._shared_rag_query_func else "unavailable",
            "loaded": self.__class__._shared_rag_query_func is not None,
            "ragProjectDirSetting": settings.rag_project_dir,
            "resolvedRagProjectDir": str(rag_dir),
            "ragDirectoryExists": rag_dir.exists(),
            "knowledgeBaseDirectoryExists": kb_dir.exists(),
            "faissIndexExists": index_path.exists(),
            "chunksMetadataExists": metadata_path.exists(),
            "chunksMetadataCount": metadata_count,
            "loadError": self.__class__._shared_load_error,
            "lastQueryError": self.__class__._shared_last_query_error,
            "cerebrasModelConfigured": bool(settings.cerebras_model),
            "cerebrasApiKeyConfigured": bool(settings.cerebras_api_key),
            "mongodbDatabase": settings.mongodb_database,
            "mongodbSpeciesRawCollection": settings.mongodb_species_raw_collection,
        }

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def last_query_error(self) -> str | None:
        return self._last_query_error
