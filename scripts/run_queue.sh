#!/bin/bash
# The study's request queue, one step after another against the endpoint:
#
#   scripts/run_queue.sh [study.toml] step1 step2 ...
#
# A step is `run:<model>` (the model's block of the design; `run:<model>:<k>/<n>` runs shard
# k of n, for a service that allows parallel requests), `graph:<model>` (notation
# gate + parsing of that model's answers) or `references` (parse the papers' own
# formulations that have no stored reply yet). Every step is resumable: a step that stops
# on a transient fault (exit 3: overload, network, the daily request cap) is resumed
# after a pause and repeats nothing that is already on disk; any other non-zero exit
# stops the queue. One process at a time against the endpoint: this script is that
# process (Joern: "model run after model run"; ScaDS is a shared service).
set -u
STUDY=${1:-studies/paper0_2026/study.toml}; shift || true
STEPS=("$@")
PAUSE_TRANSIENT=${PAUSE_TRANSIENT:-1800}   # 30 min after a transient stop
MAX_RESUMES=${MAX_RESUMES:-96}             # about two days of retries per step
set -a; . ~/.config/raiLP/secrets.env; set +a
cd "$(dirname "$0")/.."
for step in "${STEPS[@]}"; do
  case "$step" in
    run:*:*/*) rest=${step#run:}; cmd=(run --model "${rest%%:*}" --shard "${rest#*:}") ;;
    run:*) cmd=(run --model "${step#run:}") ;;
    graph:*) cmd=(graph --model "${step#graph:}") ;;
    references) cmd=(validate-references --repeats 2) ;;
    *) echo "=== unknown step $step"; exit 2 ;;
  esac
  for ((i = 0; i <= MAX_RESUMES; i++)); do
    echo "=== $step attempt $i $(date -u +%FT%TZ)"
    python3 -m genstudy --study "$STUDY" "${cmd[@]}"
    rc=$?
    if [ $rc -eq 0 ]; then echo "=== $step complete $(date -u +%FT%TZ)"; break; fi
    if [ $rc -ne 3 ]; then echo "=== $step stopped with exit $rc: not resuming"; exit $rc; fi
    echo "=== $step transient stop; resuming in $PAUSE_TRANSIENT s"; sleep "$PAUSE_TRANSIENT"
  done
done
echo "=== queue done $(date -u +%FT%TZ)"
