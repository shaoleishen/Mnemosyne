import logging
from typing import List

logger = logging.getLogger(__name__)

class LocalEmbedder:
    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.backend = None
        self._init_model()

    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Initializing SentenceTransformer model '{self.model_name}' on '{self.device}'")
            self.model = SentenceTransformer(self.model_name, device=self.device)
            self.backend = "sentence-transformers"
        except ImportError:
            try:
                from fastembed import TextEmbedding
                logger.info(f"SentenceTransformer not available. Initializing FastEmbed model '{self.model_name}'")
                # fastembed handles device internally, we just initialize it
                self.model = TextEmbedding(model_name=self.model_name)
                self.backend = "fastembed"
            except ImportError:
                raise ImportError(
                    "Neither 'sentence-transformers' nor 'fastembed' is installed. "
                    "Please install package extras: pip install knowcran[local]"
                )

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if self.backend == "sentence-transformers":
            embeddings = self.model.encode(texts)
            if hasattr(embeddings, "tolist"):
                return embeddings.tolist()
            return [list(e) for e in embeddings]
        elif self.backend == "fastembed":
            # fastembed's embed() returns a generator
            embeddings = list(self.model.embed(texts))
            return [list(e) for e in embeddings]
        else:
            raise RuntimeError("Embedder is not initialized correctly.")
