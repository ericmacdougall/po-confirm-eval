#!/bin/sh
# usage: ops/run_shards.sh <system> <split> <prompt> <tag> <port> <model_tag> [extra args]
# Runs 4 shards in parallel against a llama-server (localhost tunnel); each shard is light HTTP client work.
set -eu
SYS=$1; SPLIT=$2; PROMPT=$3; TAG=$4; PORT=$5; MTAG=$6; shift 6
cd "$(dirname "$0")/.."
export LABE_SERVER_URL="http://127.0.0.1:$PORT" LABE_MODEL_TAG="$MTAG"
pids=""
for i in 0 1 2 3; do
  python3 src/run_system.py --system "$SYS" --split "$SPLIT" --prompt "$PROMPT" --tag "$TAG" --shard $i --nshards 4 "$@" > "runs/log_${TAG}_${SPLIT}_$i.txt" 2>&1 &
  pids="$pids $!"
done
failed=0
for pid in $pids; do
  wait "$pid" || failed=1
done
if [ "$failed" -ne 0 ]; then
  echo "FAILED $TAG $SPLIT: inspect all shard logs" >&2
  exit 1
fi
echo "DONE $TAG $SPLIT"
