@echo off
REM Telegram Product Scraper - Windows Setup Script
REM This script automates the initial setup process

echo ===================================================================
echo    Telegram Product Scraper - Setup Script
echo ===================================================================
echo.

REM Check Python
echo [1/6] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found. Please install Python 3.8+
    echo     Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found
echo.

REM Create virtual environment
echo [2/6] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [!] Virtual environment already exists
)
echo.

REM Activate virtual environment
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [X] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

REM Install dependencies
echo [4/6] Installing dependencies...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo [OK] Dependencies installed
echo.

REM Setup .env file
echo [5/6] Setting up configuration...
if not exist ".env" (
    copy .env.example .env >nul
    echo [OK] Created .env file from template
    echo [!] Please edit .env with your credentials
    echo.
    echo     Required:
    echo       * TELEGRAM_API_ID
    echo       * TELEGRAM_API_HASH
    echo       * TELEGRAM_PHONE
    echo.
    echo     Optional:
    echo       * GEMINI_API_KEY (for AI extraction)
    echo       * BACKEND_URL (for API integration)
    echo.
) else (
    echo [!] .env file already exists
)
echo.

REM Create directories
echo [6/6] Creating directories...
if not exist "downloaded_images" mkdir downloaded_images
echo [OK] Created downloaded_images directory
echo.

REM Summary
echo ===================================================================
echo    Setup Complete!
echo ===================================================================
echo.
echo Next steps:
echo.
echo   1. Edit configuration:
echo      notepad .env
echo.
echo   2. Get Telegram credentials:
echo      https://my.telegram.org
echo.
echo   3. (Optional) Get Gemini API key:
echo      https://makersuite.google.com/app/apikey
echo.
echo   4. Test Gemini API (optional):
echo      python test_gemini.py
echo.
echo   5. Run the scraper:
echo      python scraper.py
echo.
echo For more information, see README.md
echo.
pause
