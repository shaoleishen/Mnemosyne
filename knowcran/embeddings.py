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
        self.provider = self.settings.embedding_provider
        
        if self.provider == "local":
            self.api_base = self.settings.local_embedding_url.rstrip("/")
            self.model = self.settings.local_embedding_model
            self.api_key = "local"  # Dummy key to bypass API key checks
        else:
            self.api_key = self.settings.openai_api_key
            self.api_base = self.settings.openai_api_base.rstrip("/")
            self.model = self.settings.embedding_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of strings."""
        if not texts:
            return []

        # Strip strings to avoid empty input errors
        cleaned_texts = [t.strip() if t.strip() else " " for t in texts]

        # Throw exception if provider is none/mock or key is missing
        if self.provider == "none":
            raise ValueError("Embedding provider is set to 'none'.")
        if not self.api_key:
            raise ValueError("OpenAI API key is missing. Cannot generate embeddings.")

        # Determine batch size: use local_embedding_batch_size for local, and a safe default (e.g. 64) for others
        batch_size = 64
        if self.provider == "local":
            batch_size = getattr(self.settings, "local_embedding_batch_size", 16)

        all_embeddings = []
        for i in range(0, len(cleaned_texts), batch_size):
            batch = cleaned_texts[i:i + batch_size]
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "input": batch,
                "model": self.model,
            }
            
            logger.info(f"Generating embeddings for batch of {len(batch)} chunks (total {len(texts)}) using {self.model} via {self.provider}")
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
            all_embeddings.extend(embeddings)

        return all_embeddings
