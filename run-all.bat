@echo off
setlocal
cd /d "%~dp0"
title Vesper AI - Launch All Services

echo ========================================================
echo               Starting Vesper AI System
echo ========================================================
echo.

:: 1. Start Ollama in background if not already running
echo [1/4] Checking Ollama server...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Starting Ollama server...
    start "Ollama Server" /min cmd /c "set OLLAMA_HOST=0.0.0.0:11434 && ollama serve"
    timeout /t 3 /nobreak >nul
) else (
    echo Ollama is already running.
)

:: 2. Start VoiceID sidecar (:8788) in WSL
echo [2/4] Starting VoiceID Sidecar (:8788)...
start "VoiceID Sidecar (:8788)" wsl -d Ubuntu -- bash -c "cd /mnt/c/College/Academics/Sem5/NLP_MiniProject/vesper-ai/voiceid && .venv-local/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8788"

:: 3. Start FastAPI backend (:8000) in WSL
echo [3/4] Starting FastAPI Backend (:8000)...
start "FastAPI Backend (:8000)" wsl -d Ubuntu -- bash -c "cd /mnt/c/College/Academics/Sem5/NLP_MiniProject/vesper-ai/backend && .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000"

:: 4. Start Next.js Frontend (:3000) on Windows
echo [4/4] Starting Next.js Frontend (:3000)...
start "Next.js Frontend (:3000)" cmd /c "cd /d app && npm run dev"

echo.
echo ========================================================
echo Services launched!
echo   Frontend : http://localhost:3000
echo   Backend  : http://localhost:8000/api/health
echo   VoiceID  : http://localhost:8788/health
echo   Ollama   : http://localhost:11434
echo ========================================================
echo.
echo You can close this launcher window.
timeout /t 5 >nul
