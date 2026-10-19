"""Optional lazy sentence-transformers embeddings and cosine ranking."""

from __future__ import annotations

import json
import math
import os
from typing import Any, Callable

from .paths import load_dotenv, model_cache_dir

MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingProvider:
    def __init__(self, model_name: str = MODEL_NAME, loader: Callable[[str], Any] | None = None) -> None:
        self.model_name = model_name
        self._loader = loader
        self._model: Any = None
        self._attempted = False
        self.last_error: str | None = None

    def _get_model(self) -> Any | None:
        if self._attempted:
            return self._model
        self._attempted = True
        try:
            load_dotenv()
            if self._loader:
                self._model = self._loader(self.model_name)
            else:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self._model = SentenceTransformer(
                    self.model_name,
                    cache_folder=str(model_cache_dir()),
                    local_files_only=os.getenv("FILE_MEMORY_OFFLINE_MODE", "1") == "1",
                )
        except Exception as error:
            self._model = None
            self.last_error = str(error)
        return self._model

    def readiness(self) -> tuple[bool, str]:
        """Load the optional model and return a user-facing readiness status."""
        if self._get_model() is not None:
            return True, f"{self.model_name} is ready"
        detail = self.last_error or "the model is not installed in the local cache"
        return False, f"{self.model_name} is unavailable: {detail}"

    def encode(self, text: str) -> list[float] | None:
        model = self._get_model()
        if model is None:
            return None
        try:
            vector = model.encode(text, normalize_embeddings=True)
            return [float(value) for value in vector]
        except Exception:
            return None


def searchable_text(record: dict[str, Any]) -> str:
    return " ".join((record.get("filename") or "", record.get("note") or "", record.get("snippet") or ""))[:4000]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def decode_embedding(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        result = json.loads(value)
        return [float(item) for item in result]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
