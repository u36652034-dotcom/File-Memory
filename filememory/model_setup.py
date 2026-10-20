"""Download and cache the local models required by first-run setup."""

from __future__ import annotations

from .embeddings import MODEL_NAME
from .paths import model_cache_dir, resource_path

CHAT_MODEL = "HuggingFaceTB/SmolLM2-360M-Instruct"


def bootstrap_bundled_model_cache(cache=None) -> bool:
    """Copy an offline install's bundled Hugging Face cache into app data."""
    import shutil

    bundled = resource_path("models")
    if not bundled.is_dir():
        return False
    destination = cache or model_cache_dir()
    destination.mkdir(parents=True, exist_ok=True)
    for source in bundled.iterdir():
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    return True


def prepare_embedding_model(cache=None, local_files_only: bool = False) -> str:
    """Fetch or validate the required all-MiniLM-L6-v2 embedding model."""
    from sentence_transformers import SentenceTransformer  # type: ignore

    cache = cache or model_cache_dir()
    SentenceTransformer(
        MODEL_NAME,
        cache_folder=str(cache),
        local_files_only=local_files_only,
    )
    return f"{MODEL_NAME} ready in {cache}"


def prepare_chat_model(cache=None, local_files_only: bool = False) -> str:
    """Fetch or validate SmolLM2 for the Local AI setup choice."""
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

    cache = cache or model_cache_dir()
    AutoTokenizer.from_pretrained(CHAT_MODEL, cache_dir=str(cache), local_files_only=local_files_only)
    AutoModelForCausalLM.from_pretrained(CHAT_MODEL, cache_dir=str(cache), local_files_only=local_files_only)
    return f"{CHAT_MODEL} ready in {cache}"


def prepare_models_for_mode(ai_mode: str, cache=None) -> str:
    """Prepare embeddings for every setup and SmolLM2 only for Local AI."""
    if ai_mode not in {"local_ai", "groq"}:
        raise ValueError("first-run setup requires Local AI or Groq")
    cache = cache or model_cache_dir()
    bundled = bootstrap_bundled_model_cache(cache)
    local_files_only = bundled
    prepare_embedding_model(cache, local_files_only=local_files_only)
    if ai_mode == "local_ai":
        prepare_chat_model(cache, local_files_only=local_files_only)
        return f"Embedding model and {CHAT_MODEL} are ready in {cache}"
    return f"Embedding model is ready in {cache}; SmolLM2 was not downloaded"


def prepare_local_models() -> str:
    """Backward-compatible helper used by the standalone model preparation script."""
    return prepare_models_for_mode("local_ai")
