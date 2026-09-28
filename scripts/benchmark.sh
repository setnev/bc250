#!/usr/bin/env bash
# No service or hardware changes. Stop competing workloads separately.
set -euo pipefail
bench_bin="${LLAMA_BENCH:-/opt/bc250-ai/llama.cpp/build/bin/llama-bench}"
model_file="${MODEL_FILE:-/var/lib/bc250-ai/models/Qwen3.5-9B-Q4_K_M.gguf}"
threads="${THREADS:-6}"
[[ -x "$bench_bin" ]] || { echo "Set LLAMA_BENCH to the built llama-bench executable." >&2; exit 1; }
[[ -f "$model_file" ]] || { echo "Set MODEL_FILE to the verified Qwen3.5-9B Q4_K_M GGUF." >&2; exit 1; }
[[ "$threads" =~ ^[1-9][0-9]*$ ]] || { echo "THREADS must be a positive integer." >&2; exit 1; }
exec "$bench_bin" -m "$model_file" -p 512 -n 128 -b 128 -ub 128 -t "$threads" -ngl 99 -fa on -r 3 -o json
