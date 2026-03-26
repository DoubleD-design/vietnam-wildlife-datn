from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from app.core.config import settings

OUT_OF_SCOPE_MESSAGE = "Mình chưa thể trả lời câu hỏi này vì nội dung vượt ngoài phạm vi dữ liệu hiện có của mình."


class RagPipelineService:
    def __init__(self) -> None:
        self._rag_query_func = None
        self._load_error: str | None = None

    def answer(self, question: str, species_scientific_name: str = "") -> str:
        rag_query = self._ensure_loaded()
        if rag_query is None:
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
        except Exception:
            return OUT_OF_SCOPE_MESSAGE

    def _ensure_loaded(self):
        if self._rag_query_func is not None:
            return self._rag_query_func

        try:
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
                return None

            return self._rag_query_func
        except BaseException as exc:
            self._load_error = str(exc)
            return None

    @property
    def load_error(self) -> str | None:
        return self._load_error
