#!/bin/bash
# Run the study's model blocks one after another (Joern: "model run after model run").
#
#   scripts/run_models.sh [study.toml] model1 model2 ...
#
# A block that stops on a transient fault (overload, network, the daily request cap)
# is resumed after a pause; the runner never records a run it could not finish, so a
# resume repeats nothing that is already on disk. Exit code 3 = transient stop,
# 0 = block complete, anything else = stop and look. One process at a time against
# the endpoint: this script is that process.
set -u
STUDY=${1:-studies/paper0_2026/study.toml}; shift || true
MODELS=("$@")
PAUSE_TRANSIENT=${PAUSE_TRANSIENT:-1800}   # 30 min after a transient stop
MAX_RESUMES=${MAX_RESUMES:-48}             # about a day of retries per model
set -a; . ~/.config/raiLP/secrets.env; set +a
cd "$(dirname "$0")/.."
for m in "${MODELS[@]}"; do
  for ((i = 0; i <= MAX_RESUMES; i++)); do
    echo "=== $m attempt $i $(date -u +%FT%TZ)"
    python3 -m genstudy --study "$STUDY" run --model "$m"
    rc=$?
    if [ $rc -eq 0 ]; then echo "=== $m complete $(date -u +%FT%TZ)"; break; fi
    if [ $rc -ne 3 ]; then echo "=== $m stopped with exit $rc: not resuming"; exit $rc; fi
    echo "=== $m transient stop; resuming in $PAUSE_TRANSIENT s"; sleep "$PAUSE_TRANSIENT"
  done
done
echo "=== all requested models done $(date -u +%FT%TZ)"
