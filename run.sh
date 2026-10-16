#!/usr/bin/env bash
# Xhiron te dyja kontratat kundrejt serverit lokal vLLM.
# Perdorim:  bash run.sh
set -u
cd "$(dirname "$0")"

if ! curl -s --max-time 3 http://localhost:8000/v1/models > /dev/null; then
  echo "[GABIM] Serveri vLLM nuk pergjigjet ne localhost:8000"
  echo "        Ne nje dritare tjeter:  vllm serve Qwen/Qwen3-14B-AWQ --max-model-len 8192"
  exit 1
fi

rm -f rezultatet.txt
for k in kontrata_test_01 kontrata_biocheck; do
  echo "[${OR_MODEL:-Qwen/Qwen3-14B-AWQ}] $k"
  {
    echo
    echo "=================================================="
    echo "MODELI: ${OR_MODEL:-Qwen/Qwen3-14B-AWQ}  |  KONTRATA: $k"
    echo "=================================================="
  } >> rezultatet.txt
  python3 score.py "$k.txt" real >> rezultatet.txt 2>&1
done

echo
echo "MBAROI. Rezultatet: rezultatet.txt"
