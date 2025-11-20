@echo off
setlocal
chcp 65001 > nul

:: ============================================================
:: Minecraft Mod Translator (Gemini Edition)
::
:: 機能:
:: 1. 環境構築
:: 2. 翻訳モード選択 (Google vs Gemini)
:: 3. 実行
::
:: ヘルプ: 引数なしで実行すると対話モードになります。
:: ============================================================

echo.
echo ========================================================
echo       Minecraft Mod Auto Translator (AI Powered)
echo ========================================================
echo.

:: Pythonチェック
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Pythonが見つかりません。
    pause
    exit /b
)

:: 仮想環境作成
if not exist "venv" (
    echo [INFO] 仮想環境を作成中...
    python -m venv venv
)

call venv\Scripts\activate

:: ライブラリインストール (Gemini対応)
:: google-generativeai を追加
pip show google-generativeai > nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 必要なライブラリをインストール中...
    pip install deep-translator tqdm google-generativeai
)

echo.
echo 翻訳モードを選択するのじゃ。
echo.
echo   [1] Google翻訳 (無料・キー不要・精度そこそこ)
echo   [2] Gemini AI翻訳 (要APIキー・高精度・文脈理解あり)
echo.
set /p MODE="選択 (1 or 2) > "

set ENGINE=google
set KEY_OPT=
set API_KEY=

if "%MODE%"=="2" (
    set ENGINE=gemini
    echo.
    echo Gemini APIキーを入力するのじゃ。
    echo (入力しても画面には表示されるが、気にせずペーストせよ)
    echo キーは https://aistudio.google.com/app/apikey から取得できるぞ。
    set /p API_KEY="API Key > "
)

:: キーが空ならGoogleに戻す
if "%ENGINE%"=="gemini" (
    if "%API_KEY%"=="" (
        echo [WARNING] キーが空じゃぞ。Googleモードに切り替える。
        set ENGINE=google
    )
)

echo.
:ASK_DIR
echo Modフォルダのパスを入力（ドラッグ＆ドロップ可）:
set /p MOD_DIR="> "
set MOD_DIR=%MOD_DIR:"=%

if not exist "%MOD_DIR%" goto ASK_DIR

echo.
echo 出力リソースパック名 (空欄でデフォルト):
set /p OUT_NAME="> "
if "%OUT_NAME%"=="" set OUT_NAME=Generated_Pack_%ENGINE%

echo.
echo 開始するぞ... Engine: %ENGINE%
echo.

if "%ENGINE%"=="gemini" (
    python mod_translator.py -i "%MOD_DIR%" -o "%OUT_NAME%" --engine gemini --key "%API_KEY%"
) else (
    python mod_translator.py -i "%MOD_DIR%" -o "%OUT_NAME%" --engine google
)

echo.
pause