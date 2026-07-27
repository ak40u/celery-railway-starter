#!/usr/bin/env bash
# End-to-end check of a deployed web + worker + scheduler stack.
#
# It proves the three parts are actually three parts: the web service answers
# immediately, the worker finishes the work afterwards, a failing task is
# recorded as failed rather than lost, and the scheduler produces its own work
# with nobody asking.
#
#   scripts/verify-queue.sh https://your-api.up.railway.app 'the-token'
set -uo pipefail

BASE="${1:?usage: verify-queue.sh <base-url> <api-token>}"
TOKEN="${2:?usage: verify-queue.sh <base-url> <api-token>}"
BASE="${BASE%/}"
failed=0

ok()   { echo "  ok   $1${2:+ - $2}"; }
fail() { echo "  FAIL $1 - $2"; failed=1; }

pick() {
  python3 -c '
import json, sys
try:
    node = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
for part in sys.argv[2:]:
    try:
        node = node[int(part)] if part.isdigit() else node[part]
    except Exception:
        sys.exit(0)
print(node if isinstance(node, str) else json.dumps(node))
' "$@"
}

api() { curl -s --max-time 60 -H "authorization: Bearer $TOKEN" "$@"; }

wait_for_status() {
  local id="$1" want="$2" tries="${3:-40}"
  for _ in $(seq 1 "$tries"); do
    local body status
    body=$(api "$BASE/jobs/$id")
    status=$(pick "$body" status)
    [ "$status" = "$want" ] && { echo "$body"; return 0; }
    [ "$status" = "failed" ] && [ "$want" = "done" ] && { echo "$body"; return 1; }
    sleep 2
  done
  echo ""
  return 1
}

echo "checking $BASE"

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$BASE/health")
[ "$code" = "200" ] && ok "health" || fail "health" "got $code"

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -X POST "$BASE/jobs" -H 'content-type: application/json' -d '{}')
[ "$code" = "401" ] && ok "the queue is not open" || fail "the queue is not open" "got $code"

# 1. Enqueuing returns at once. The task sleeps for three seconds; if the
#    request took that long, the work is happening in the wrong process.
start=$(date +%s)
body=$(api -X POST "$BASE/jobs" -H 'content-type: application/json' -d '{"payload":{"seconds":3,"echo":"verified"}}')
elapsed=$(( $(date +%s) - start ))
ID=$(pick "$body" id)
if [ -n "$ID" ] && [ "$elapsed" -lt 3 ]; then
  ok "enqueue returns immediately" "${elapsed}s for a 3s task"
else
  fail "enqueue returns immediately" "took ${elapsed}s, body ${body:0:120}"
fi

# 2. The worker finishes it.
if done_body=$(wait_for_status "$ID" done); then
  ok "the worker completed the job" "result $(pick "$done_body" result)"
else
  fail "the worker completed the job" "${done_body:0:160}"
fi

# 3. A task that raises is recorded as failed - not silently dropped, which is
#    what happens when nothing writes the outcome down.
body=$(api -X POST "$BASE/jobs" -H 'content-type: application/json' -d '{"payload":{"seconds":0,"fail":"deliberate failure"}}')
FAIL_ID=$(pick "$body" id)
if fail_body=$(wait_for_status "$FAIL_ID" failed 30); then
  ok "a failing task is recorded" "$(pick "$fail_body" error)"
else
  fail "a failing task is recorded" "${fail_body:0:160}"
fi

# 4. The scheduler produces work on its own.
found=""
for _ in $(seq 1 40); do
  body=$(api "$BASE/heartbeats")
  count=$(python3 -c '
import json, sys
try:
    print(len(json.loads(sys.argv[1]).get("heartbeats", [])))
except Exception:
    print(0)
' "$body")
  [ "$count" != "0" ] && { found="$body"; break; }
  sleep 5
done
[ -n "$found" ] && ok "the scheduler ran a periodic task" "$(pick "$found" heartbeats 0 noted_at)" \
  || fail "the scheduler ran a periodic task" "no heartbeat in about three minutes"

echo
[ "$failed" = "0" ] && echo "all checks passed" || { echo "some checks failed"; exit 1; }
