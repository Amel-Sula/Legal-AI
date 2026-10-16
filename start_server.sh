#!/usr/bin/env bash
# ./start_server.sh                        -> 14B origjinali
# ./start_server.sh Qwen/Qwen3-32B-AWQ --alias  -> 32B nen emrin e vjeter (Probe B)
source $HOME/venv/bin/activate
MODEL="${1:-Qwen/Qwen3-14B-AWQ}"
EXTRA=""
if [ "$2" == "--alias" ]; then
  EXTRA="--served-model-name Qwen/Qwen3-14B-AWQ"
fi
VLLM_USE_FLASHINFER_SAMPLER=0 vllm serve "$MODEL" \
  --max-model-len 8192 --seed 42 $EXTRA
# Nese 32B ben OOM gjate nisjes: shto --max-model-len 6144 --enforce-eager
