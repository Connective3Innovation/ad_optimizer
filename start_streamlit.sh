#!/bin/bash
# Start Streamlit Frontend

echo "Starting Streamlit Frontend..."
echo "Make sure FastAPI backend is running at: http://localhost:8000"
echo "Streamlit will be available at: http://localhost:8501"
echo ""

cd "$(dirname "$0")"
streamlit run src/streamlit_app.py
