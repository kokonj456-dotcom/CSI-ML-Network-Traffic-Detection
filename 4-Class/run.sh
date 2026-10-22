#!/bin/bash
# 4-Class Presentation Dashboard Runner
PORT=3000
echo "=========================================================="
echo "Starting 4-Class Interactive Presentation Web Dashboard"
echo "URL: http://localhost:$PORT"
echo "Directory: 4-Class/"
echo "=========================================================="
python3 -m http.server $PORT --directory 4-Class

