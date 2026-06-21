#!/bin/bash
# Launch llama-server for Preserve Layer 3
#
# Usage:
#   ./scripts/start_llm_server.sh          # GPU mode (default)
#   ./scripts/start_llm_server.sh gpu      # GPU mode (explicit)
#   ./scripts/start_llm_server.sh cpu      # CPU-only mode
#
# Prerequisites:
#   Build llama.cpp: see vendor/llama.cpp/README.md
#   Download model:  python scripts/download_model.py

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

SERVER_BIN="$PROJECT_DIR/vendor/llama.cpp/build/bin/llama-server"
MODEL="$PROJECT_DIR/models/Qwen3.5-0.8B-Q4_K_M.gguf"
PORT=8090
MODE="${1:-gpu}"

if [ ! -f "$SERVER_BIN" ]; then
    echo "ERROR: llama-server not found at $SERVER_BIN"
    echo ""
    echo "Build it with:"
    echo "  cd $PROJECT_DIR/vendor/llama.cpp"
    echo "  cmake -B build -DGGML_CUDA=ON -DGGML_NATIVE=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_BUILD_TYPE=Release"
    echo "  cmake --build build --config Release -j\$(nproc)"
    exit 1
fi

if [ ! -f "$MODEL" ]; then
    echo "ERROR: Model not found at $MODEL"
    echo "Download with: python scripts/download_model.py --model 0.8B --quant Q4_K_M"
    exit 1
fi

if [ "$MODE" = "gpu" ]; then
    NGL=99
    echo "Starting llama-server (GPU mode, all layers on GPU)"
else
    NGL=0
    echo "Starting llama-server (CPU mode)"
fi

echo "  Model: $MODEL"
echo "  Port:  $PORT"
echo "  URL:   http://127.0.0.1:$PORT/v1"
echo ""

exec "$SERVER_BIN" \
    -m "$MODEL" \
    -ngl $NGL \
    -c 4096 \
    -t 4 \
    --flash-attn on \
    --reasoning off \
    --host 127.0.0.1 \
    --port $PORT \
    --metrics
