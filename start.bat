@echo off
setlocal
chcp 65001 > nul

:: ============================================================
:: Minecraft Mod Translator Setup & Launcher
::
:: 機能:
:: 1. Python環境(venv)の自動構築
:: 2. 必要なライブラリの自動インストール
:: 3. ユーザーへのフォルダパス質問
:: 4. 翻訳スクリプトの実行
:: ============================================================

echo.
echo ========================================================
echo       Minecraft Mod Auto Translator (Wrapper)
echo ========================================================
echo.

:: Pythonの確認
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Pythonが見つかりません。インストールしてください。
    echo インストール時に "Add Python to PATH" にチェックを入れるのを忘れないように。
    pause
    exit /b
)

:: 仮想環境(venv)の確認と作成
if not exist "venv" (
    echo [INFO] 初回起動を検知しました。仮想環境を作成中...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] 仮想環境の作成に失敗しました。
        pause
        exit /b
    )
)

:: 仮想環境のアクティブ化
call venv\Scripts\activate

:: 依存ライブラリのインストール確認
pip show deep-translator > nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 必要なライブラリをインストールしています...
    pip install deep-translator tqdm
)

echo.
echo 環境準備完了じゃ。翻訳を開始するぞ。
echo.

:: ユーザー入力（ドラッグ＆ドロップ対応）
:ASK_DIR
echo 翻訳したいModが入っているフォルダのパスを入力（またはドラッグ＆ドロップ）してください。
set /p MOD_DIR="> "

:: 入力パスのダブルクォート除去処理
set MOD_DIR=%MOD_DIR:"=%

if not exist "%MOD_DIR%" (
    echo [ERROR] 指定されたフォルダが見つかりません。もう一度入力してください。
    goto ASK_DIR
)

echo.
echo 出力するリソースパックの名前を入力してください（例: MyJpPack）。
echo 何も入力せずにEnterを押すと "Generated_Pack" になります。
set /p OUT_NAME="> "

if "%OUT_NAME%"=="" set OUT_NAME=Generated_Pack

echo.
echo --------------------------------------------------------
echo [設定確認]
echo 入力: %MOD_DIR%
echo 出力: %OUT_NAME%
echo.
echo Modファイル本体は削除・変更されません。
echo 翻訳リソースパックのみが生成されます。
echo --------------------------------------------------------
echo.
pause

:: Pythonスクリプト実行
:: ここで --reset をつけると進捗をリセット、つけなければ続きから
python mod_translator.py -i "%MOD_DIR%" -o "%OUT_NAME%"

echo.
if %errorlevel% equ 0 (
    echo すべて完了じゃ！ "%OUT_NAME%" フォルダを resourcepacks に入れるのじゃ。
) else (
    echo エラーが発生したようじゃ。ログを確認せよ。
)

pause