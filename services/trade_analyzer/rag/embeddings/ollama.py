"""Ollama embedding backend (nomic-embed-text)."""
from __future__ import annotations

import os

import ollama


class OllamaEmbeddingProvider:
    def __init__(self, model: str = "nomic-embed-text") -> None:
        self.model = model
        self._host = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")

    def _client(self) -> ollama.Client:
        return ollama.Client(host=self._host)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        resp = self._client().embeddings(model=self.model, prompt=text)
        return list(resp["embedding"])

    def health(self) -> tuple[bool, str]:
        try:
            self.embed_query("health")
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
