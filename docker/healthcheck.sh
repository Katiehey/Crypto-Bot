#!/bin/bash
set -e

# Verify Python is the container's main process via /proc 
grep -q "python" /proc/1/cmdline || exit 1

# Require heartbeat file for liveness
test -f /app/state/heartbeat.json
