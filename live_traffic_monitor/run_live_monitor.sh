#!/bin/bash
# ==============================================================================
# One-Click Launcher: Wireshark Live Defense Monitor & AI Intrusion Detection
# Starts FastAPI WebSocket backend on http://localhost:8088 and opens browser
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="/opt/miniconda3/envs/csi403/bin/python"

if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python3"
fi

echo "======================================================================"
echo " Starting Wireshark Live Defense Monitor // Model M9 (5.04M Rows)"
echo " Environment: $PYTHON_EXEC"
echo " Dashboard URL: http://localhost:8088"
echo "======================================================================"

# Check if port 8088 is currently occupied
PID=$(lsof -ti:8088)
if [ -n "$PID" ]; then
    echo "Notice: Port 8088 occupied by PID $PID. Releasing port..."
    kill -9 $PID 2>/dev/null || true
    sleep 1
fi

# Open browser after 1.5 seconds in background
(sleep 1.5 && open "http://localhost:8088" 2>/dev/null || true) &

# Run server in backend directory
cd "$SCRIPT_DIR/backend"
exec "$PYTHON_EXEC" server.py
