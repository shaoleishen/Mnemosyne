"""Configuration management for KnowCran."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

S2_BASE_URL = "https://api.semanticscholar.org"

DEFAULT_FIELDS = ",".join([
    "paperId", "title", "abstract", "year", "publicationDate", "venue",
    "authors", "externalIds", "citationCount", "referenceCount",
    "influentialCitationCount", "fieldsOfStudy", "s2FieldsOfStudy",
    "openAccessPdf", "url",
])

EXPANDED_FIELDS = DEFAULT_FIELDS + ",references,citations"

DISCOVERY_QUERIES = [
    "{q}",
    "{q} mechanism",
    "{q} treatment",
    "{q} review",
    "{q} clinical",
]


def _detect_claw_bin() -> str | None:
    """Detect Claw binary path following the priority order from the goal plan."""
    env = os.getenv("MNEMOSYNE_CLAW_BIN")
    if env and Path(env).exists():
        return env
    # Sibling paths
    for rel in [
        "../claw-code-main/rust/target/debug/claw.exe",
        "../claw-code-main/rust/target/debug/claw",
    ]:
        p = Path(rel)
        if p.exists():
            return str(p.resolve())
    # On PATH
    found = shutil.which("claw")
    return found


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWCRAN_DATA_DIR", "data")))
    vault_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWCRAN_VAULT_DIR", "vault")))
    rate_limit_seconds: float = field(default_factory=lambda: float(os.getenv("KNOWCRAN_RATE_LIMIT_SECONDS", "1.1")))
    s2_api_key: str = field(default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""))

    # LLM provider settings
    llm_provider: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_LLM_PROVIDER", "none"))
    claw_bin: str | None = field(default_factory=_detect_claw_bin)
    claw_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_CLAW_MODEL", "sonnet"))
    claw_permission_mode: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_CLAW_PERMISSION_MODE", "read-only"))
    claw_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_CLAW_TIMEOUT_SECONDS", "600")))
    claw_max_retries: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_CLAW_MAX_RETRIES", "2")))
    llm_cache_dir: Path = field(default_factory=lambda: Path(os.getenv("MNEMOSYNE_LLM_CACHE_DIR", "data/raw/llm")))

    # PDF download, parsing, and embedding settings
    pdf_download_enabled: bool = field(default_factory=lambda: os.getenv("MNEMOSYNE_PDF_DOWNLOAD_ENABLED", "true").lower() == "true")
    pdf_dir: Path = field(default_factory=lambda: Path(os.getenv("MNEMOSYNE_PDF_DIR", "data/pdfs")))
    pdf_strategy: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_PDF_STRATEGY", "fastest"))
    scihub_enabled: bool = field(default_factory=lambda: os.getenv("MNEMOSYNE_SCIHUB_ENABLED", "true").lower() == "true")
    libgen_enabled: bool = field(default_factory=lambda: os.getenv("MNEMOSYNE_LIBGEN_ENABLED", "true").lower() == "true")
    tor_enabled: bool = field(default_factory=lambda: os.getenv("MNEMOSYNE_TOR_ENABLED", "false").lower() == "true")
    pdf_batch_workers: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_PDF_BATCH_WORKERS", "5")))
    pdf_parser: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_PDF_PARSER", "auto"))
    mineru_api_url: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_MINERU_URL", os.getenv("MINERU_API_URL", "http://127.0.0.1:8000")))
    mineru_mode: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_MINERU_MODE", "managed"))
    mineru_backend: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_MINERU_BACKEND", "docker"))
    mineru_gpu: bool = field(default_factory=lambda: os.getenv("MNEMOSYNE_MINERU_GPU", "false").lower() == "true")
    mineru_workers: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_MINERU_WORKERS", "1")))
    mineru_models_dir: Path = field(default_factory=lambda: Path(os.getenv("MNEMOSYNE_MINERU_MODELS_DIR", "data/models/mineru")))
    mineru_config_file: Path = field(default_factory=lambda: Path(os.getenv("MNEMOSYNE_MINERU_CONFIG_FILE", "data/mineru/magic-pdf.json")))
    mineru_return_md: bool = field(default_factory=lambda: os.getenv("MINERU_RETURN_MD", "true").lower() == "true")
    mineru_return_content_list: bool = field(default_factory=lambda: os.getenv("MINERU_RETURN_CONTENT_LIST", "true").lower() == "true")
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", os.getenv("OPENAI_API_key", "")))
    openai_api_base: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_EMBEDDING_API_BASE", "https://api.openai.com/v1"))
    embedding_provider: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_EMBEDDING_PROVIDER", "openai"))
    embedding_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_EMBEDDING_MODEL", "text-embedding-3-large"))
    local_embedding_mode: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_MODE", "managed"))
    local_embedding_url: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_URL", "http://127.0.0.1:8010/v1"))
    local_embedding_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_MODEL", "BAAI/bge-m3"))
    local_embedding_device: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_DEVICE", "cpu"))
    local_embedding_batch_size: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_BATCH_SIZE", "16")))
    local_embedding_startup_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_LOCAL_EMBEDDING_STARTUP_TIMEOUT_SECONDS", "180")))
    mineru_startup_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_MINERU_STARTUP_TIMEOUT_SECONDS", "180")))

    # Vision API settings (multimodal)
    vision_providers: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_PROVIDERS", ""))
    vision_health_file: Path = field(default_factory=lambda: Path(os.getenv("MNEMOSYNE_VISION_HEALTH_FILE", "data/runtime/vision_provider_health.json")))

    # Vision provider: Mimo
    vision_mimo_api_base: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_MIMO_API_BASE", ""))
    vision_mimo_api_key: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_MIMO_API_KEY", ""))
    vision_mimo_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_MIMO_MODEL", ""))

    # Vision provider: Kimi
    vision_kimi_api_base: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_KIMI_API_BASE", ""))
    vision_kimi_api_key: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_KIMI_API_KEY", ""))
    vision_kimi_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_KIMI_MODEL", ""))

    # Vision provider: Qwen
    vision_qwen_api_base: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_QWEN_API_BASE", ""))
    vision_qwen_api_key: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_QWEN_API_KEY", ""))
    vision_qwen_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_QWEN_MODEL", ""))

    # Vision provider: DeepSeek
    vision_deepseek_api_base: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_DEEPSEEK_API_BASE", ""))
    vision_deepseek_api_key: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_DEEPSEEK_API_KEY", ""))
    vision_deepseek_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_VISION_DEEPSEEK_MODEL", ""))

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.vault_dir = Path(self.vault_dir)

        if not os.getenv("MNEMOSYNE_PDF_DIR") and self.pdf_dir == Path("data/pdfs"):
            self.pdf_dir = self.data_dir / "pdfs"
            
        if not os.getenv("MNEMOSYNE_MINERU_MODELS_DIR") and self.mineru_models_dir == Path("data/models/mineru"):
            self.mineru_models_dir = self.data_dir / "models" / "mineru"
            
        if not os.getenv("MNEMOSYNE_MINERU_CONFIG_FILE") and self.mineru_config_file == Path("data/mineru/magic-pdf.json"):
            self.mineru_config_file = self.data_dir / "mineru" / "magic-pdf.json"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw" / "semantic_scholar"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "knowcran.sqlite"

    def ensure_pdf_dir(self) -> Path:
        """Create and return the PDF directory."""
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        return self.pdf_dir

    @classmethod
    def from_env(cls) -> Settings:
        return cls()

    def get_vision_router(self):
        """Create a VisionRouter from configured providers."""
        from knowcran.vision.router import VisionRouter
        from knowcran.vision.provider import VisionProvider

        providers = []
        provider_configs = self.vision_providers.split(",")

        for name in provider_configs:
            name = name.strip().lower()
            if not name:
                continue

            api_base = getattr(self, f"vision_{name}_api_base", "")
            api_key = getattr(self, f"vision_{name}_api_key", "")
            model = getattr(self, f"vision_{name}_model", "")

            if api_base and api_key and model:
                providers.append(VisionProvider(
                    name=name,
                    api_base=api_base,
                    api_key=api_key,
                    model=model,
                ))

        if not providers:
            return None

        return VisionRouter(
            providers=providers,
            health_file=self.vision_health_file,
        )


# Module-level defaults for backward compatibility
_default = Settings()
DATA_DIR = _default.data_dir
VAULT_DIR = _default.vault_dir
RAW_DIR = _default.raw_dir
DB_PATH = _default.db_path
RATE_LIMIT_SECONDS = _default.rate_limit_seconds
S2_API_KEY = _default.s2_api_key
