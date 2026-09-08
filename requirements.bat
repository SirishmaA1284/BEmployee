@echo off
setlocal enabledelayedexpansion
title AI Employee - Requirements Installer
cd /d "%~dp0"

echo ================================================
echo  AI Employee - Requirements Installer
echo  Installs the required APPLICATIONS (Docker
echo  Desktop, Python 3.11+, Node.js 20+) and all
echo  project dependencies (backend pip + frontend
echo  npm). Safe to re-run at any time.
echo ================================================
echo.

where winget >nul 2>&1
if errorlevel 1 (
    echo [ERROR] winget is not available on this system.
    echo         Install "App Installer" from the Microsoft Store, then re-run.
    pause
    exit /b 1
)

call :refresh_path
call :ensure_docker
if errorlevel 1 exit /b 1
call :ensure_python
if errorlevel 1 exit /b 1
call :ensure_node
if errorlevel 1 exit /b 1
call :setup_backend
if errorlevel 1 exit /b 1
call :setup_frontend
if errorlevel 1 exit /b 1
call :create_backend_env_file

echo.
echo ================================================
echo  All done. Next step: double-click start.bat
echo  to launch Postgres, backend and frontend.
echo  ^(If Docker Desktop was just installed, log
echo  out/in once first so its CLI is on PATH.^)
echo ================================================
pause
exit /b 0

rem ================================================
rem  Refreshes PATH with Machine + User values so
rem  applications installed during this run are found.
rem ================================================
:refresh_path
set "FRESH="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine')"`) do set "FRESH=%%P"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "FRESH=!FRESH!;%%P"
if defined FRESH set "PATH=!FRESH!;!PATH!"
goto :eof

rem ================================================
rem  1/5 Docker Desktop
rem ================================================
:ensure_docker
set "DOCKERPATH=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKERPATH%" set "DOCKERPATH=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
if exist "%DOCKERPATH%" (
    echo [1/5] OK - Docker Desktop is installed.
    goto :eof
)
where docker >nul 2>&1
if not errorlevel 1 (
    echo [1/5] OK - Docker CLI is available.
    goto :eof
)
echo [1/5] Installing Docker Desktop ^(large download, be patient^)...
winget install -e --id Docker.DockerDesktop --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo        [WARN] Automatic install failed. Install manually from
    echo        https://www.docker.com/products/docker-desktop and re-run.
    exit /b 1
)
echo        Installed. If Docker does not start, log out/in once, then run start.bat.
goto :eof

rem ================================================
rem  2/5 Python 3.11+
rem ================================================
:ensure_python
set "PYCMD="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYCMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto python_ok
)
where python >nul 2>&1
if errorlevel 1 goto python_install
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYCMD=python"
    goto python_ok
)
:python_install
echo [2/5] Installing Python 3.11...
winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo        [ERROR] Python install failed. Install 3.11+ manually from
    echo        https://www.python.org/downloads/ and re-run.
    exit /b 1
)
set "FRESH="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "FRESH=%%P"
if defined FRESH set "PATH=!FRESH!;!PATH!"
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYCMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYCMD (
    echo        [ERROR] Python not found after install. Open a NEW terminal and re-run.
    exit /b 1
)
:python_ok
echo [2/5] OK - Python is available.
goto :eof

rem ================================================
rem  3/5 Node.js 20+
rem ================================================
:ensure_node
where node >nul 2>&1
if errorlevel 1 goto node_install
node -e "process.exit(parseInt(process.versions.node,10)>=20?0:1)" >nul 2>&1
if not errorlevel 1 goto node_ok
:node_install
echo [3/5] Installing Node.js LTS ^(20+^)...
winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo        [ERROR] Node.js install failed. Install 20+ manually from
    echo        https://nodejs.org/ and re-run.
    exit /b 1
)
call :refresh_path
where node >nul 2>&1
if errorlevel 1 (
    echo        [ERROR] Node.js not found after install. Open a NEW terminal and re-run.
    exit /b 1
)
:node_ok
echo [3/5] OK - Node.js is available.
goto :eof

rem ================================================
rem  4/5 Backend virtualenv + pip dependencies
rem ================================================
:setup_backend
if not exist "backend\.venv\Scripts\python.exe" (
    echo [4/5] Creating backend virtualenv...
    "%PYCMD%" -m venv backend\.venv
    if errorlevel 1 (
        echo        [ERROR] Failed to create backend\.venv.
        exit /b 1
    )
) else (
    echo [4/5] backend\.venv already exists.
)
echo        Installing Python dependencies ^(requirements-dev.txt^)...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 goto pip_fail
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements-dev.txt --quiet --disable-pip-version-check
if errorlevel 1 goto pip_fail
echo [4/5] OK - Python dependencies installed.
goto :eof
:pip_fail
echo        [ERROR] pip install failed. Re-run this file after fixing network access.
exit /b 1

rem ================================================
rem  5/5 Frontend npm dependencies
rem ================================================
:setup_frontend
echo [5/5] Installing frontend dependencies...
where npm >nul 2>&1
if errorlevel 1 (
    echo        [ERROR] npm not found. Open a NEW terminal and re-run.
    exit /b 1
)
pushd frontend
if exist node_modules (
    echo        node_modules already present - skipping.
) else (
    if exist package-lock.json (
        call npm ci --no-audit --no-fund
    ) else (
        call npm install --no-audit --no-fund
    )
    if errorlevel 1 (
        echo        [ERROR] npm install failed. Re-run this file.
        popd
        exit /b 1
    )
)
popd
echo [5/5] OK - Frontend dependencies installed.
goto :eof

rem ================================================
rem  Convenience: backend\.env for host-based runs
rem ================================================
:create_backend_env_file
if not exist "backend\.env" (
    if exist ".env.example" (
        copy /Y ".env.example" "backend\.env" >nul
        echo Created backend\.env from .env.example - check DATABASE_URL matches docker-compose.yml.
    )
)
goto :eof
