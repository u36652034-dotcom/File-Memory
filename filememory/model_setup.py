"""Download and cache the required local models for the desktop setup wizard."""

from __future__ import annotations

from .embeddings import MODEL_NAME
from .paths import model_cache_dir

CHAT_MODEL = "HuggingFaceTB/SmolLM2-360M-Instruct"


def prepare_local_models() -> str:
    """Fetch both local models into the user application-data cache."""
    from sentence_transformers import SentenceTransformer  # type: ignore
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

    cache = model_cache_dir()
    SentenceTransformer(MODEL_NAME, cache_folder=str(cache))
    AutoTokenizer.from_pretrained(CHAT_MODEL, cache_dir=str(cache))
    AutoModelForCausalLM.from_pretrained(CHAT_MODEL, cache_dir=str(cache))
    return f"Models ready in {cache}"
