@echo off
setlocal enabledelayedexpansion
title AI Employee - Stack Starter
cd /d "%~dp0"

echo ============================================
echo  AI Employee - starting full stack
echo ============================================

rem ---------- 1. Make sure Docker is running ----------
tasklist /FI "IMAGENAME eq Docker Desktop.exe" 2>nul | find /I "Docker Desktop.exe" >nul
if not errorlevel 1 goto engine_wait

set "DOCKERPATH=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKERPATH%" set "DOCKERPATH=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKERPATH%" (
    echo [ERROR] Docker Desktop not found. Install it from https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)
echo Starting Docker Desktop...
start "" "%DOCKERPATH%"

:engine_wait
set /a tries=0
:engine_loop
docker info >nul 2>&1
if not errorlevel 1 goto compose_up
set /a tries+=1
if !tries! geq 60 (
    echo [ERROR] Docker engine did not become ready within 5 minutes.
    echo         Open Docker Desktop manually and re-run start.bat.
    pause
    exit /b 1
)
timeout /t 5 /nobreak >nul
goto engine_loop

rem ---------- 2. Start containers (db, backend, frontend) ----------
:compose_up
echo Docker engine ready. Starting containers (db, backend, frontend)...
docker compose up -d --build
if errorlevel 1 (
    echo [ERROR] docker compose up failed - see output above.
    pause
    exit /b 1
)

rem ---------- 3. Wait for the backend API ----------
echo Waiting for the backend API to respond...
set /a tries=0
:health_loop
curl.exe -fsS http://localhost:8000/health >nul 2>&1
if not errorlevel 1 goto migrate
set /a tries+=1
if !tries! geq 120 (
    echo [WARN] Backend not responding after 6 minutes. Check: docker compose logs backend
    goto frontend_wait
)
timeout /t 3 /nobreak >nul
goto health_loop

rem ---------- 4. Apply any pending database migrations ----------
:migrate
echo Applying pending database migrations...
docker compose exec -T backend alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Migrations failed. Run manually: docker compose exec backend alembic upgrade head
    pause
    exit /b 1
)

rem ---------- 5. Wait for the frontend, then open it ----------
:frontend_wait
echo Waiting for the frontend...
set /a tries=0
:front_loop
curl.exe -fsS http://localhost:5173/ >nul 2>&1
if not errorlevel 1 goto open_browser
set /a tries+=1
if !tries! geq 60 (
    echo [WARN] Frontend not responding after 3 minutes. Check: docker compose logs frontend
    goto done
)
timeout /t 3 /nobreak >nul
goto front_loop

:open_browser
start "" http://localhost:5173

:done
echo.
echo ============================================
echo  All services are up:
echo    Frontend : http://localhost:5173
echo    Backend  : http://localhost:8000  (API docs: http://localhost:8000/docs)
echo    Database : localhost:5433
echo ============================================
echo.
echo  Watch live logs anytime with:  docker compose logs -f
echo  This window can be closed after services are running.
pause
