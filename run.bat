@echo off
chcp 932 >nul
rem ------------------------------------------------------
rem  下にヘルプがあるぞ。困ったら -h をつけるのじゃ。
rem ------------------------------------------------------

rem 引数がヘルプかどうか確認
if "%~1"=="-h" goto :SHOW_HELP
if "%~1"=="--help" goto :SHOW_HELP

rem ------------------------------------------------------
rem  メイン処理
rem  PowerShellを「ExecutionPolicy Bypass」で強制実行する。
rem  渡された引数(%*)はそのままスクリプトに引き継ぐ。
rem ------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File ".\start.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 予期せぬエラーで終了したようじゃ。
    pause
)

exit /b

rem ------------------------------------------------------
rem  ヘルプ表示セクション
rem ------------------------------------------------------
:SHOW_HELP
echo.
echo ==========================================================
echo   Minecraft Mod Auto Translator Launcher
echo ==========================================================
echo.
echo  PowerShellスクリプト (start.ps1) を起動するためのラッパーじゃ。
echo  実行ポリシー(ExecutionPolicy)をBypassして実行するため、
echo  事前の設定なしでダブルクリックのみで起動できるぞ。
echo.
echo  使い方:
echo    Run_Translator.bat [オプション]
echo.
echo  オプション:
echo    -h, --help      このヘルプを表示して一時停止する
echo    その他          start.ps1 にそのまま引数として渡される
echo.
echo  使用例:
echo    Run_Translator.bat
echo      -> 対話モードで起動（通常はこれ）
echo.
echo    Run_Translator.bat -InputPath "C:\Mods"
echo      -> 引数付きで起動
echo.
pause
exit /b