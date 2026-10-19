"""Lazy note suggestion providers: offline, optional local model, or Groq."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable


class OfflineSuggestionProvider:
    def suggest(self, filename: str, snippet: str = "") -> str:
        stem = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
        first_line = next((line.strip() for line in snippet.splitlines() if line.strip()), "")
        if first_line:
            return f"{stem}: {first_line[:140]}".strip(": ")
        return f"File about {stem}" if stem else "File note"


class SmolLM2SuggestionProvider:
    def __init__(self, loader: Callable[[str], Any] | None = None) -> None:
        self.loader = loader
        self._pipeline: Any = None
        self._attempted = False

    def suggest(self, filename: str, snippet: str = "") -> str | None:
        if not self._attempted:
            self._attempted = True
            try:
                if self.loader:
                    self._pipeline = self.loader()
                else:
                    from transformers import pipeline  # type: ignore
                    self._pipeline = pipeline("text-generation", model="HuggingFaceTB/SmolLM2-360M-Instruct")
            except Exception:
                self._pipeline = None
        if self._pipeline is None:
            return None
        try:
            prompt = f"Write a short note for {filename}. Context: {snippet[:500]}"
            result = self._pipeline(prompt, max_new_tokens=48, do_sample=False)
            return str(result[0]["generated_text"])[len(prompt):].strip()
        except Exception:
            return None


class GroqSuggestionProvider:
    def __init__(self, api_key: str | None = None, url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.url = url or os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
        self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    def suggest(self, filename: str, snippet: str = "") -> str | None:
        if not self.api_key:
            return None
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": f"Write a short note for {filename}: {snippet[:700]}"}],
            "temperature": 0.2,
            "max_tokens": 80,
        }).encode()
        request = urllib.request.Request(
            self.url, data=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode())
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None
