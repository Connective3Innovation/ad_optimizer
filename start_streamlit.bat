@echo off
REM Start Streamlit Frontend (Windows)

echo Starting Streamlit Frontend...
echo Make sure FastAPI backend is running at: http://localhost:8000
echo Streamlit will be available at: http://localhost:8501
echo.

cd /d "%~dp0"
streamlit run src\streamlit_app.py
pause
