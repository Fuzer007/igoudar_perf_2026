#!/bin/bash
# Build and deploy script for Render
set -euo pipefail

# Render web services provide $PORT. If it's missing, you're likely using the wrong service type.
: "${PORT:?PORT env var is required (use a Render Web Service, not a Background Worker)}"

echo "Starting uvicorn on 0.0.0.0:${PORT}..."
python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
