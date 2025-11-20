<#
.SYNOPSIS
    Minecraft Mod Auto Translator 起動スクリプト (PowerShell版)

.DESCRIPTION
    Minecraft Modの言語ファイルを自動翻訳するPythonスクリプトを実行するためのラッパーじゃ。
    仮想環境(venv)の自動構築、ライブラリのインストール、日本語UIによる対話的なオプション選択を提供するぞ。
    
    主な機能:
    - Python環境のチェック
    - 仮想環境(.venv)の自動作成とライブラリインストール
    - 翻訳エンジン（Google/Gemini/Local）の選択メニュー
    - Modフォルダと出力先フォルダのドラッグ＆ドロップ入力対応
    - 日本語表示（文字化けなし）

.PARAMETER InputPath
    [オプション] 翻訳対象のModまたはShaderが入っているフォルダのパス。
    指定しない場合は対話モードで入力を求められる。

.PARAMETER OutputPath
    [オプション] 出力するリソースパックのパス（フォルダ名）。
    デフォルトは "Output_Pack"。

.EXAMPLE
    .\start.ps1
    対話モードで起動する。基本はこれじゃ。

.EXAMPLE
    .\start.ps1 -InputPath "C:\Games\Minecraft\mods" -OutputPath "MyJpPack"
    引数を指定して起動することも可能じゃ。

.NOTES
    Author: Wise Wolf
    Version: 3.2 (WinPS Compatible)
#>

param (
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

# 文字コードをUTF-8に設定（これで日本語も安心じゃ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- 設定エリア ---
$VENV_DIR = "venv"
$SCRIPT_NAME = "mod_translator.py"
$REQUIREMENTS = "deep-translator requests"

# --- ヘルパー関数 ---
function Write-Log {
    param([string]$Message, [string]$Color = "White")
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $Message" -ForegroundColor $Color
}

function Check-Python {
    try {
        $null = Get-Command "python" -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

# --- メイン処理 ---

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Minecraft Mod Auto Translator (PS版)   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Pythonの確認
if (-not (Check-Python)) {
    Write-Log "エラー: Pythonが見つかりません。インストールし、PATHに通してください。" "Red"
    Write-Log "Python公式サイト: https://www.python.org/" "Red"
    Write-Host "何かキーを押すと終了します..." -NoNewline
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# 2. 仮想環境の構築とライブラリインストール
if (-not (Test-Path $VENV_DIR)) {
    Write-Log "仮想環境($VENV_DIR)を作成中... 少し待つのじゃ。" "Yellow"
    python -m venv $VENV_DIR
    if ($LASTEXITCODE -ne 0) {
        Write-Log "仮想環境の作成に失敗したようじゃ。" "Red"
        Write-Host "何かキーを押すと終了します..." -NoNewline
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
}

# 仮想環境内のPythonとPipのパス
# Windows PowerShell 5.1 ($IsWindowsが存在しない) 対策として $env:OS もチェック
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $PY_EXEC = "$VENV_DIR\Scripts\python.exe"
    $PIP_EXEC = "$VENV_DIR\Scripts\pip.exe"
}
else {
    $PY_EXEC = "$VENV_DIR/bin/python"
    $PIP_EXEC = "$VENV_DIR/bin/pip"
}

# ライブラリのインストールチェック（簡易）
Write-Log "必要なライブラリを確認中..." "Gray"
# エラーハンドリング追加: pipが見つからない場合のメッセージ
if (-not (Test-Path $PIP_EXEC)) {
    Write-Log "エラー: pipが見つかりません。パス: $PIP_EXEC" "Red"
    Write-Log "仮想環境の作成に失敗している可能性があります。'.venv' フォルダを削除して再試行してください。" "Red"
    Write-Host "何かキーを押すと終了します..." -NoNewline
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

& $PIP_EXEC install $REQUIREMENTS --disable-pip-version-check | Out-Null

# 3. メニュー表示と選択
Write-Host ""
Write-Host "翻訳エンジンを選択するのじゃ:" -ForegroundColor Green
Write-Host " [1] Google Translate (無料/キー不要/精度並)"
Write-Host " [2] Gemini AI (高速/要APIキー/高精度 - 推奨)"
Write-Host " [3] Local LLM (Ollama/LM Studio)"
Write-Host ""

$engine_choice = Read-Host "番号を入力 [1-3]"

$args_list = @()
$api_key = ""

switch ($engine_choice) {
    "1" {
        $args_list += "--engine", "google"
        Write-Log "Google翻訳モードで実行するぞ。" "Cyan"
    }
    "2" {
        $args_list += "--engine", "gemini"
        $api_key = Read-Host "Gemini API Keyを入力 (右クリックで貼り付け)"
        if ([string]::IsNullOrWhiteSpace($api_key)) {
            Write-Log "API Keyがないと動かぬぞ。終了じゃ。" "Red"
            exit
        }
        $args_list += "--key", "$api_key"
        
        Write-Host ""
        Write-Host "Lite限定モードを使うか？" -ForegroundColor Yellow
        Write-Host " (レート制限(429)を回避し、軽量モデルのみで回すモードじゃ)"
        $lite_check = Read-Host " [Y] Yes / [N] No"
        if ($lite_check -match "^[Yy]") {
            $args_list += "--lite-only"
            Write-Log "Lite限定モード: ON" "Cyan"
        }
    }
    "3" {
        Write-Host " [1] Ollama"
        Write-Host " [2] LM Studio"
        $local_type = Read-Host "どちらを使う？ [1-2]"
        if ($local_type -eq "2") {
            $args_list += "--engine", "lmstudio"
            Write-Log "LM Studioモード: 事前にサーバー(port 1234)を起動しておくのじゃぞ。" "Yellow"
        }
        else {
            $args_list += "--engine", "ollama"
            $model_name = Read-Host "使用するモデル名を入力 (例: gemma2:9b / 空欄でデフォルト)"
            if (-not [string]::IsNullOrWhiteSpace($model_name)) {
                $args_list += "--model", "$model_name"
            }
        }
    }
    Default {
        Write-Log "よくわからん入力をしたな。Google翻訳にしておくぞ。" "Yellow"
        $args_list += "--engine", "google"
    }
}

# 4. フォルダパスの入力 (引数がなければ聞く)
if ([string]::IsNullOrWhiteSpace($InputPath)) {
    Write-Host ""
    Write-Host "翻訳対象のMod/Shaderフォルダをドラッグ＆ドロップせよ:" -ForegroundColor Green
    $InputPath = Read-Host "> "
}
# パスの引用符削除処理（PowerShellのRead-Hostの癖対策）
$InputPath = $InputPath -replace '"', ''

if (-not (Test-Path $InputPath)) {
    Write-Log "エラー: そのフォルダは見つからぬぞ: $InputPath" "Red"
    Write-Host "何かキーを押すと終了します..." -NoNewline
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}
$args_list += "--input", "$InputPath"

# 5. 出力先 (引数がなければ聞く)
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Write-Host ""
    Write-Host "出力先リソースパック名（またはフルパス）を入力せよ:" -ForegroundColor Green
    $OutputPath = Read-Host "> "
    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        $OutputPath = "Output_Pack"
    }
}
$OutputPath = $OutputPath -replace '"', ''
$args_list += "--output", "$OutputPath"

# 6. Pythonスクリプト実行
Write-Host ""
Write-Log "よし、翻訳開始じゃ！" "Green"
Write-Host "実行コマンド: $PY_EXEC $SCRIPT_NAME $args_list" -ForegroundColor DarkGray
Write-Host "--------------------------------------------------"

# 引数リストを渡して実行
& $PY_EXEC $SCRIPT_NAME @args_list

Write-Host ""
Write-Log "処理完了じゃ。お疲れ様。" "Green"
Write-Host "何かキーを押すと終了します..." -NoNewline
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")