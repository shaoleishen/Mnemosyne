# Local WSL GPU Setup

This guide targets a local Windows + WSL2 workstation with an NVIDIA GPU, such as an RTX 3070 8GB, large system RAM, and a recent Intel i9 CPU.

## 1. Create the Conda Environment

```bash
conda create -n mnemosyne python=3.12 -y
conda activate mnemosyne
python -m pip install --upgrade pip
pip install -e ".[dev,local,rag]"
```

For CUDA-enabled local embeddings:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Confirm CUDA visibility before starting Mnemosyne services:

```bash
nvidia-smi
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
```

## 2. Configure Local Production Mode

Create `.env` from `.env.example` and use local managed embeddings:

```env
MNEMOSYNE_EMBEDDING_PROVIDER=local
MNEMOSYNE_LOCAL_EMBEDDING_MODE=managed
MNEMOSYNE_LOCAL_EMBEDDING_URL=http://127.0.0.1:8010/v1
MNEMOSYNE_LOCAL_EMBEDDING_MODEL=BAAI/bge-m3
MNEMOSYNE_LOCAL_EMBEDDING_DEVICE=cuda
MNEMOSYNE_LOCAL_EMBEDDING_BATCH_SIZE=16
MNEMOSYNE_LOCAL_EMBEDDING_STARTUP_TIMEOUT_SECONDS=240

MNEMOSYNE_MINERU_MODE=managed
MNEMOSYNE_MINERU_BACKEND=docker
MNEMOSYNE_MINERU_GPU=true
MNEMOSYNE_MINERU_WORKERS=1
MNEMOSYNE_MINERU_STARTUP_TIMEOUT_SECONDS=240
MNEMOSYNE_PDF_BATCH_WORKERS=5
MINERU_MODEL_SOURCE=local
```

For an RTX 3070 8GB, keep `MNEMOSYNE_MINERU_WORKERS=1`. Increase PDF download workers freely, but avoid concurrent MinerU OCR/layout workers unless VRAM headroom is proven.

## 3. Build the MinerU Docker Image

Mnemosyne expects a local image named `mineru:latest` for managed Docker mode.

```bash
wget https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile
docker build -t mineru:latest -f Dockerfile .
```

Docker GPU support must be configured in WSL2. A quick check:

```bash
docker info --format '{{json .Runtimes}}'
```

The output should include `nvidia` before using `knowcran services start --gpu`.

## 4. Start and Inspect Services

```bash
knowcran doctor --gpu
knowcran services start --gpu
knowcran services status
knowcran services logs embedding
knowcran services logs mineru
```

The local embedding endpoint is OpenAI-compatible at `/v1/embeddings`, while health checks use `/health` at the service root.

## 5. Run a Topic Pipeline

```bash
knowcran init
knowcran run-topic "intracerebral hemorrhage" --limit 50 --gpu
```

When finished:

```bash
knowcran services stop
```

## Operational Notes

- The first local embedding run may download `BAAI/bge-m3`; pre-download it if you need offline runs.
- MinerU models should live under `MNEMOSYNE_MINERU_MODELS_DIR` or `data/models/mineru`.
- If Docker GPU runtime is missing, managed MinerU now fails fast instead of silently starting a CPU or broken container.
- If `MNEMOSYNE_PDF_PARSER=auto` and MinerU is unavailable, Mnemosyne falls back to PyMuPDF and records the degraded reason.
