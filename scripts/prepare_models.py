"""Download the selected local models into the project-local model cache."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from filememory.model_setup import prepare_local_models
from filememory.paths import load_dotenv, model_cache_dir


EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHAT_MODEL = "HuggingFaceTB/SmolLM2-360M-Instruct"


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    os.environ.setdefault("FILE_MEMORY_MODEL_DIR", str(project_root / ".models"))
    cache = model_cache_dir()
    os.environ["HF_HOME"] = str(cache)
    os.environ["FILE_MEMORY_MODEL_DIR"] = str(cache)
    print(prepare_local_models())


if __name__ == "__main__":
    main()
