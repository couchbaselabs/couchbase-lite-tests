#!/bin/bash
# Test all dataset URLs from the host machine.
# Run: bash servers/reactnative/scripts/test_urls.sh

set -euo pipefail

BASE="https://raw.githubusercontent.com/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/dbs/js"

PASS=0
FAIL=0

check_url() {
  local label="$1"
  local url="$2"
  local expect_min_bytes="${3:-1}"
  local http_code size
  http_code=$(curl -sL -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
  size=$(curl -sL "$url" 2>/dev/null | wc -c | tr -d ' ')
  if [[ "$http_code" == "200" ]] && [[ "$size" -ge "$expect_min_bytes" ]]; then
    echo "  PASS  $label  (HTTP $http_code, ${size} bytes)"
    ((PASS++))
  else
    echo "  FAIL  $label  (HTTP $http_code, ${size} bytes, expected >=${expect_min_bytes})"
    ((FAIL++))
  fi
}

echo "=== Dataset URL Verification ==="
echo ""
echo "[1] Index file:"
check_url "travel/index.json" "$BASE/travel/index.json" 50
echo ""
echo "[2] Collection JSONL files:"
check_url "travel.airlines.jsonl (~30KB)" "$BASE/travel/travel.airlines.jsonl" 1000
check_url "travel.airports.jsonl (empty)" "$BASE/travel/travel.airports.jsonl" 0
check_url "travel.hotels.jsonl (~1.9MB)" "$BASE/travel/travel.hotels.jsonl" 100000
check_url "travel.landmarks.jsonl (empty)" "$BASE/travel/travel.landmarks.jsonl" 0
check_url "travel.routes.jsonl (~3.6MB)" "$BASE/travel/travel.routes.jsonl" 100000
echo ""
echo "[3] Content validation - airlines first line:"
first_line=$(curl -sL "$BASE/travel/travel.airlines.jsonl" 2>/dev/null | head -1)
if echo "$first_line" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  echo "  PASS  First line is valid JSON"
  ((PASS++))
else
  echo "  FAIL  First line is NOT valid JSON"
  ((FAIL++))
fi
echo ""
echo "[4] Content validation - airlines doc count:"
airline_count=$(curl -sL "$BASE/travel/travel.airlines.jsonl" 2>/dev/null | grep -c '^{' || echo 0)
if [[ "$airline_count" -ge 100 ]]; then
  echo "  PASS  airlines has $airline_count docs"
  ((PASS++))
else
  echo "  FAIL  airlines has only $airline_count docs"
  ((FAIL++))
fi
echo ""
echo "=== SUMMARY: $PASS passed, $FAIL failed ==="
exit $FAIL
