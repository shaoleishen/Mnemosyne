import logging
import os
from typing import List, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mnemosyne Local Embedding Server",
    description="OpenAI-compatible local embeddings endpoint for Mnemosyne/knowcran",
)

# Global embedder instance
embedder = None

class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = "BAAI/bge-m3"

class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]

class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: EmbeddingUsage

@app.on_event("startup")
def startup_event():
    global embedder
    model_name = os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_MODEL", "BAAI/bge-m3")
    device = os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_DEVICE", "cpu")
    
    logger.info(f"Starting embedding server with model={model_name} on device={device}")
    
    # Defer import to startup time to avoid failing module load when packages are missing
    from knowcran.services.embedder import LocalEmbedder
    try:
        embedder = LocalEmbedder(model_name, device=device)
        logger.info("Local embedder successfully initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize local embedder: {e}", exc_info=True)

@app.get("/health")
def health():
    if embedder is None:
        raise HTTPException(status_code=500, detail="Embedder not initialized")
    return {"status": "ok", "backend": embedder.backend}

@app.get("/")
def root():
    model_name = os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_MODEL", "BAAI/bge-m3")
    return {
        "message": "Mnemosyne Local Embedding Server is running",
        "model": model_name,
        "initialized": embedder is not None
    }

@app.post("/v1/embeddings", response_model=EmbeddingResponse)
def create_embeddings(req: EmbeddingRequest):
    global embedder
    if embedder is None:
        raise HTTPException(status_code=500, detail="Embedder is not initialized")
        
    texts = [req.input] if isinstance(req.input, str) else req.input
    if not texts:
        return EmbeddingResponse(
            object="list",
            data=[],
            model=req.model,
            usage=EmbeddingUsage()
        )
        
    # Standardize string inputs
    cleaned_texts = [str(t) for t in texts]
    
    try:
        embeddings = embedder.embed(cleaned_texts)
        data = [
            EmbeddingData(index=idx, embedding=emb)
            for idx, emb in enumerate(embeddings)
        ]
        return EmbeddingResponse(
            object="list",
            data=data,
            model=req.model,
            usage=EmbeddingUsage()
        )
    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
