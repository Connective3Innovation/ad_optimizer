#!/bin/bash
# Start FastAPI Backend

echo "Starting FastAPI Backend..."
echo "API will be available at: http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo ""

cd "$(dirname "$0")"
python src/api.py
