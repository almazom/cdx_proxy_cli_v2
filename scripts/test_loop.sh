#!/bin/bash
# Automated test loop for cdx proxy

echo "=== CDX Proxy Autonomous Test Loop ==="
echo "Starting $(date)"
echo

passed=0
failed=0

while true; do
    result=$(timeout 60 codex exec -s danger-full-access "say hello" 2>&1)
    
    if echo "$result" | grep -q "Reconnecting"; then
        failed=$((failed + 1))
        echo "[$(date +%H:%M:%S)] FAILED - Stream disconnected"
    elif echo "$result" | grep -q "hello"; then
        passed=$((passed + 1))
        echo "[$(date +%H:%M:%S)] PASSED - Got response"
    else
        failed=$((failed + 1))
        echo "[$(date +%H:%M:%S)] FAILED - No response"
    fi
    
    # Show stats every 10 tests
    total=$((passed + failed))
    if [ $((total % 10)) -eq 0 ]; then
        rate=$((passed * 100 / total))
        echo
        echo "=== Stats ==="
        echo "Total: $total | Passed: $passed | Failed: $failed | Rate: ${rate}%"
        echo
    fi
    
    sleep 5
done
