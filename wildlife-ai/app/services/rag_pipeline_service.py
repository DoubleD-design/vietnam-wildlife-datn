from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path

from app.core.config import settings

OUT_OF_SCOPE_MESSAGE = "Mình chưa thể trả lời câu hỏi này vì nội dung vượt ngoài phạm vi dữ liệu hiện có của mình."
logger = logging.getLogger(__name__)


class RagPipelineService:
    _shared_rag_query_func = None
    _shared_load_error: str | None = None

    def __init__(self) -> None:
        self._rag_query_func = self.__class__._shared_rag_query_func
        self._load_error: str | None = self.__class__._shared_load_error

    def answer(self, question: str, species_scientific_name: str = "") -> str:
        rag_query = self._ensure_loaded()
        if rag_query is None:
            if self._load_error:
                logger.error("RAG load failed: %s", self._load_error)
            return OUT_OF_SCOPE_MESSAGE

        try:
            result = rag_query(
                question, species_name=(species_scientific_name or "").strip()
            )
            answer = (result or {}).get("answer")
            return (
                answer.strip()
                if isinstance(answer, str) and answer.strip()
                else OUT_OF_SCOPE_MESSAGE
            )
        except Exception as exc:
            logger.exception("RAG query error: %s", exc)
            return OUT_OF_SCOPE_MESSAGE

    def _ensure_loaded(self):
        if self._rag_query_func is not None:
            return self._rag_query_func

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
            if settings.hf_home:
                os.environ.setdefault("HF_HOME", settings.hf_home)
            if settings.hf_hub_offline:
                os.environ.setdefault("HF_HUB_OFFLINE", settings.hf_hub_offline)
            if settings.hf_token:
                os.environ.setdefault("HF_TOKEN", settings.hf_token)
                os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", settings.hf_token)

            rag_dir = Path(settings.rag_project_dir).expanduser().resolve()
            if not rag_dir.exists():
                self._load_error = f"RAG directory not found: {rag_dir}"
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

            return self._rag_query_func
        except BaseException as exc:
            self._load_error = str(exc)
            self.__class__._shared_load_error = self._load_error
            return None

    @property
    def load_error(self) -> str | None:
        return self._load_error
