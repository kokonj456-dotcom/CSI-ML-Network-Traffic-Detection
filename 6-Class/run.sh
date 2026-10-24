#!/usr/bin/env bash
# Runner script to serve the 6-Class interactive web dashboard on port 3000
PORT=3000
echo "Starting 6-Class Multi-Domain Threat Taxonomy Dashboard on http://localhost:$PORT ..."
cd "$(dirname "$0")"
/opt/miniconda3/envs/csi403/bin/python -m http.server $PORT

