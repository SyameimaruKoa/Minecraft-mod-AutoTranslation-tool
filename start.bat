@echo off
setlocal
chcp 65001 > nul

REM ============================================================
REM Minecraft Mod Translator (Standalone Cache Edition)
REM Version 3.3 (Custom Output Path Support)
REM
REM Note: Run with --help to see usage.
REM ============================================================

REM Check for help argument
if "%1"=="-h" goto SHOW_HELP
if "%1"=="--help" goto SHOW_HELP

echo.
echo ========================================================
echo       Minecraft Mod Auto Translator (AI Powered)
echo ========================================================
echo.

REM Check Python
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.x.
    pause
    exit /b
)

REM Check/Create venv
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment...
    if exist "venv" rmdir /s /q "venv"
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b
    )
)

call venv\Scripts\activate

REM Install Libraries
pip show google-generativeai > nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing requirements...
    pip install deep-translator tqdm google-generativeai requests
)

:SELECT_MODE
echo.
echo Select Translation Mode:
echo.
echo   [1] Google Translate (Free, No Key)
echo   [2] Gemini AI (Cloud, Requires API Key)
echo   [3] LM Studio (Local, Run Server manually!)
echo.
echo Press 1, 2 or 3:
choice /c 123 /n

if errorlevel 3 goto SETUP_LMSTUDIO
if errorlevel 2 goto SETUP_GEMINI
if errorlevel 1 goto SETUP_GOOGLE

goto SELECT_MODE

:SETUP_GEMINI
echo.
echo Enter Gemini API Key:
echo (Input will be visible, just paste it)
echo.
set /p API_KEY="API Key > "

if "%API_KEY%"=="" (
    echo [WARNING] Key is empty. Switching to Google mode.
    set ENGINE=google
    goto ASK_DIR
)
set ENGINE=gemini
goto ASK_DIR

:SETUP_LMSTUDIO
echo.
echo [IMPORTANT]
echo 1. Open LM Studio.
echo 2. Load your model (e.g. Qwen 2.5 7B).
echo 3. Go to "Developer" tab (Server icon) on the left.
echo 4. Click "Start Server" (Port 1234).
echo.
echo Press any key when the Server is running...
pause > nul

echo Checking connection to LM Studio...
curl http://localhost:1234/v1/models > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Cannot connect to LM Studio!
    echo Make sure you clicked "Start Server" in LM Studio.
    pause
    goto SELECT_MODE
)
set ENGINE=lmstudio
goto ASK_DIR

:SETUP_GOOGLE
set ENGINE=google
goto ASK_DIR

:ASK_DIR
echo.
echo --------------------------------------------------------
echo Enter Mod Folder Path (Drag and Drop):
set /p MOD_DIR="> "
set MOD_DIR=%MOD_DIR:"=%

if not exist "%MOD_DIR%" goto ASK_DIR

echo.
echo Output Resource Pack Path:
echo [Tip] You can enter a simple NAME (e.g. MyPack)
echo       OR a FULL PATH (e.g. C:\Users\Me\Desktop\MyPack).
echo       Drag and Drop is also supported.
set /p OUT_NAME="> "
set OUT_NAME=%OUT_NAME:"=%

if "%OUT_NAME%"=="" set OUT_NAME=Generated_Pack_%ENGINE%

echo.
echo Starting... Engine: %ENGINE%
echo Target Output: %OUT_NAME%
echo.

REM Execute Python script
if "%ENGINE%"=="gemini" (
    python mod_translator.py -i "%MOD_DIR%" -o "%OUT_NAME%" --engine gemini --key "%API_KEY%"
) else if "%ENGINE%"=="lmstudio" (
    python mod_translator.py -i "%MOD_DIR%" -o "%OUT_NAME%" --engine lmstudio
) else (
    python mod_translator.py -i "%MOD_DIR%" -o "%OUT_NAME%" --engine google
)

echo.
if %errorlevel% neq 0 (
    echo [ERROR] Something went wrong. Check the logs.
) else (
    echo [SUCCESS] Completed! Check the folder.
)
pause
exit /b

:SHOW_HELP
echo.
echo Usage: start.bat [OPTIONS]
echo.
echo Description:
echo   Interactive launcher for Minecraft Mod Auto Translator.
echo   Sets up Python environment and runs the translator.
echo.
echo Options:
echo   -h, --help    Show this help message.
echo.
pause