#!/bin/bash
set -e

# If the mounted models directory is empty or doesn't exist, copy the pre-downloaded models
if [ ! -d "/root/models" ] || [ -z "$(ls -A /root/models 2>/dev/null)" ]; then
    echo "Populating models directory /root/models from backup..."
    mkdir -p /root/models
    cp -r /root/models_backup/* /root/models/
fi

export MINERU_MODEL_SOURCE=local
exec "$@"
