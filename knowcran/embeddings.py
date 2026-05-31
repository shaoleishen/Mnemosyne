from __future__ import annotations

import logging
import array
import httpx
from typing import Any

from knowcran.config import Settings

logger = logging.getLogger(__name__)

def vector_to_bytes(vector: list[float]) -> bytes:
    """Serialize a list of floats to binary bytes (float32)."""
    return array.array("f", vector).tobytes()

def bytes_to_vector(data: bytes) -> list[float]:
    """Deserialize binary bytes (float32) back to a list of floats."""
    arr = array.array("f")
    arr.frombytes(data)
    return arr.tolist()

class EmbeddingProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.api_key = self.settings.openai_api_key
        self.api_base = self.settings.openai_api_base.rstrip("/")
        self.model = self.settings.embedding_model
        self.provider = self.settings.embedding_provider

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of strings."""
        if not texts:
            return []

        # Strip strings to avoid empty input errors
        cleaned_texts = [t.strip() if t.strip() else " " for t in texts]

        # Use mock embeddings if provider is none/mock or key is missing
        if self.provider == "none" or not self.api_key:
            logger.warning("No OpenAI API key found or provider set to none. Generating mock/zero embeddings.")
            # Default dimension for text-embedding-3-large is 3072, default for small is 1536
            dim = 3072 if "large" in self.model else 1536
            return [[0.0] * dim for _ in cleaned_texts]

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "input": cleaned_texts,
                "model": self.model,
            }
            
            logger.info(f"Generating embeddings for {len(texts)} chunks using {self.model} via {self.provider}")
            response = httpx.post(
                f"{self.api_base}/embeddings",
                headers=headers,
                json=payload,
                timeout=60.0
            )

            if response.status_code != 200:
                raise ValueError(f"Embedding API error {response.status_code}: {response.text}")

            resp_json = response.json()
            data = resp_json.get("data", [])
            # Sort by index to maintain original order
            data_sorted = sorted(data, key=lambda x: x.get("index", 0))
            
            embeddings = [item["embedding"] for item in data_sorted]
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            # Generate fallback zero embeddings to prevent pipeline crash
            dim = 3072 if "large" in self.model else 1536
            return [[0.0] * dim for _ in cleaned_texts]
