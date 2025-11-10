@echo off
REM Start FastAPI Backend (Windows)

echo Starting FastAPI Backend...
echo API will be available at: http://localhost:8000
echo API Documentation: http://localhost:8000/docs
echo.

cd /d "%~dp0"
python src\api.py
pause
