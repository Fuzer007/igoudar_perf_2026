#!/bin/bash
# Build and deploy script for Render
set -e

echo "Starting uvicorn on 0.0.0.0:${PORT:-8000}..."
python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
