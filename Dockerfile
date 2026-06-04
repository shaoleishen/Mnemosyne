# Use compatible CUDA 12.4 base image for host CUDA 12.6 driver compatibility
FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

# Install libgl for opencv support & Noto fonts for Chinese characters
RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 \
        libglib2.0-0 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install PyTorch with compatible CUDA 12.4 version first to prevent upgrade to incompatible CUDA 13.0
RUN python3 -m pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124 --break-system-packages

# Install mineru latest
RUN python3 -m pip install -U 'mineru[core]>=3.2.1' --break-system-packages && \
    python3 -m pip cache purge

# Copy pre-downloaded model cache and configuration
COPY huggingface_cache /root/.cache
COPY mineru.json /root/mineru.json

# Set the entry point to activate the virtual environment and run the command line tool
ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
