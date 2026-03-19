<#
.SYNOPSIS
    Minecraft Mod Auto Translator 起動スクリプト (PowerShell版)

.DESCRIPTION
    Minecraft Modの言語ファイルを自動翻訳するPythonスクリプトを実行するためのラッパーじゃ。
    仮想環境(venv)の自動構築、ライブラリのインストール、日本語UIによる対話的なオプション選択を提供するぞ。
    .envファイルによるGemini APIキーの保存・読み込みにも対応した。

    主な機能:
    - Python環境のチェック
    - 仮想環境(.venv)の自動作成とライブラリインストール
    - 翻訳エンジン（Google/Gemini/Local）の選択メニュー
    - Gemini APIキーの自動保存・読み込み(.env)
    - Modフォルダと出力先フォルダのドラッグ＆ドロップ入力対応

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
    .\start.ps1 -h
    ヘルプを表示する。

.EXAMPLE
    .\start.ps1 -InputPath "C:\Games\Minecraft\mods" -OutputPath "MyJpPack"
    引数を指定して起動することも可能じゃ。

.NOTES
    Author: Wise Wolf
    Version: 3.17 (Gemma-Only Mode Integration)
#>

param (
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

#region ヘルプ表示処理
# ヘルプ引数が渡された場合の処理（そなたとの約束通りじゃ）
if ($args -contains '-h' -or $args -contains '--help') {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit
}
#endregion

# 文字コードをUTF-8に設定（これで日本語も安心じゃ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

#region 設定・定数定義
# --- 設定エリア ---
$VENV_DIR = "venv"
$SCRIPT_NAME = "mod_translator.py"
$ENV_FILE = ".env"
$REQUIREMENTS = @("deep-translator", "requests", "python-dotenv") # dotenvを追加じゃ
#endregion

#region 関数定義
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

# .envファイルから変数を読み込む簡易関数
function Get-Env-Variable {
    param([string]$Key)
    if (Test-Path $ENV_FILE) {
        $lines = Get-Content $ENV_FILE -Encoding UTF8
        foreach ($line in $lines) {
            if ($line -match "^$Key=(.*)") {
                return $matches[1].Trim()
            }
        }
    }
    return $null
}
#endregion

#region メイン処理開始
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
#endregion

#region 仮想環境構築
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
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    $PY_EXEC = "$VENV_DIR\Scripts\python.exe"
    $PIP_EXEC = "$VENV_DIR\Scripts\pip.exe"
}
else {
    $PY_EXEC = "$VENV_DIR/bin/python"
    $PIP_EXEC = "$VENV_DIR/bin/pip"
}

# pipの存在確認
if (-not (Test-Path $PIP_EXEC)) {
    Write-Log "エラー: pipが見つかりません。パス: $PIP_EXEC" "Red"
    Write-Log "仮想環境の作成に失敗している可能性があります。'venv' フォルダを削除して再試行してください。" "Red"
    Write-Host "何かキーを押すと終了します..." -NoNewline
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Log "必要なライブラリを確認・インストール中..." "Gray"
& $PIP_EXEC install $REQUIREMENTS --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Log "エラー: ライブラリのインストールに失敗したようじゃ。" "Red"
    Write-Log "インターネット接続を確認するか、VPN/プロキシ設定を見直すのじゃ。" "Red"
    Write-Host "何かキーを押すと終了します..." -NoNewline
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}
#endregion

#region エンジン選択と設定
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
        
        # .envチェック
        $env_key = Get-Env-Variable "GEMINI_API_KEY"
        
        if (-not [string]::IsNullOrWhiteSpace($env_key)) {
            Write-Log ".envファイルからAPIキーを読み込んだぞ。" "Green"
            $api_key = $env_key
        }
        else {
            $api_key = Read-Host "Gemini API Keyを入力 (右クリックで貼り付け)"
            if ([string]::IsNullOrWhiteSpace($api_key)) {
                Write-Log "API Keyがないと動かぬぞ。終了じゃ。" "Red"
                exit
            }
            
            # 保存確認
            Write-Host "このAPIキーを .env ファイルに保存しておくか？(次回から入力を省略できるぞ)" -ForegroundColor Yellow
            $save_env = Read-Host " [Y] Yes / [N] No"
            if ($save_env -match "^[Yy]") {
                try {
                    "GEMINI_API_KEY=$api_key" | Out-File $ENV_FILE -Encoding UTF8
                    Write-Log ".env ファイルに保存したぞ。" "Green"
                }
                catch {
                    Write-Log "保存に失敗したようじゃが、処理は続行するぞ。" "Red"
                }
            }
        }
        $args_list += "--key", "$api_key"

        Write-Host ""
        Write-Host "Gemma限定モードを使うか？" -ForegroundColor Yellow
        Write-Host " (Geminiが使えない時や、確実なGemmaモデルのみで回すモードじゃ)"
        $gemma_check = Read-Host " [Y] Yes / [N] No"
        if ($gemma_check -match "^[Yy]") {
            $args_list += "--gemma-only"
            Write-Log "Gemma限定モード: ON" "Cyan"
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
#endregion

#region 入出力パス設定
# 4. フォルダパスの入力
if ([string]::IsNullOrWhiteSpace($InputPath)) {
    Write-Host ""
    Write-Host "翻訳対象のMod/Shaderフォルダをドラッグ＆ドロップせよ:" -ForegroundColor Green
    $InputPath = Read-Host "> "
}
$InputPath = $InputPath -replace '"', ''

if (-not (Test-Path $InputPath)) {
    Write-Log "エラー: そのフォルダは見つからぬぞ: $InputPath" "Red"
    Write-Host "何かキーを押すと終了します..." -NoNewline
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}
$args_list += "--input", "$InputPath"

# 5. 出力先
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
#endregion

#region スクリプト実行
# 6. Pythonスクリプト実行
Write-Host ""
Write-Log "よし、翻訳開始じゃ！" "Green"

# デバッグ表示用
$debug_args = $args_list | ForEach-Object { if ($_ -match " ") { """$_""" } else { $_ } }
Write-Host "実行コマンド: $PY_EXEC $SCRIPT_NAME $debug_args" -ForegroundColor DarkGray
Write-Host "--------------------------------------------------"

& $PY_EXEC $SCRIPT_NAME @args_list

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Log "エラー: 翻訳スクリプトが異常終了したようじゃ。" "Red"
    Write-Host "上記のエラーメッセージを確認するのじゃ。" -ForegroundColor Red
}
else {
    Write-Host ""
    Write-Log "処理完了じゃ。お疲れ様。" "Green"
}

Write-Host "何かキーを押すと終了します..." -NoNewline
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
#endregion