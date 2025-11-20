
# Minecraft Mod Auto Translator (AI Powered)

Minecraft の Mod ファイル（.jar）から言語ファイル（en_us.json）を抽出し、**Google 翻訳** または **生成AI（Gemini / Local LLM）** を用いて日本語化リソースパックを自動生成するツールじゃ。

**Mod ファイル本体（.jar）を書き換えることはない（読み取り専用）** ため、安全に利用できるのが特徴じゃの。

## 特徴

* **選べる翻訳エンジン** :
* **Google 翻訳** : 無料・手軽・高速。
* **Gemini AI** : Google の高性能 AI。文脈を理解した自然な翻訳が可能（要 API キー）。
* **Local AI (Ollama / LM Studio)** : PC 内のローカル LLM を使用。完全無料・無制限だが、PC スペックが必要。
* **出力先を自由に指定可能** : デフォルトのフォルダだけでなく、**フルパス（例: C:\MyPacks\Test）** や **ドラッグ＆ドロップ** で出力先を自由に指定できるようになったぞ。
* **プロジェクト別管理** : 翻訳キャッシュ（`trans_cache.json`）と進捗ログ（`progress_log.json`）を出力フォルダ内に保存するため、複数のプロジェクトを並行して進められる。
* **自動クリーニング** : 翻訳エラー（Error 504など）がキャッシュに混入しても、次回起動時に自動で検知して削除する。
* **自動バージョン検知** : pack.mcmeta をスキャンしてバージョンを自動設定する。
* **全自動セットアップ** : `start.bat` を実行するだけで環境構築が完了する。

## 必要要件

* **Python 3.x** : 「Add Python to PATH」にチェックを入れてインストールすること。
* **インターネット接続** : AI API 使用時。
* **(Local AI モードのみ)** : [Ollama](https://ollama.com/) または [LM Studio](https://lmstudio.ai/)。

## 使い方（推奨）

基本的には `start.bat` をダブルクリックして、対話形式で進めるのが一番楽じゃ。

1. **`start.bat` を実行する。**
2. **翻訳モードを選択する。**
   * `[1] Google Translate`
   * `[2] Gemini AI` (要 API キー)
   * `[3] LM Studio / Ollama` (ローカルサーバーを起動しておくこと)
3. **「翻訳したい Mod が入っているフォルダのパス」** を入力（ドラッグ＆ドロップ）する。
4. **「出力するリソースパックのパス」** を入力する。
   * **フォルダ名だけ** （例: `MyPack`）→ ツールと同じ場所に作成される。
   * **フルパス** （例: `C:\Users\User\Desktop\MyPack`）→ 指定した場所に作成される。
   * **ドラッグ＆ドロップ** → 既存のフォルダを指定して続きから再開できる。
5. ツールが翻訳を開始する。
6. 完了すると、指定した場所にリソースパックが生成されるぞ。

## おすすめのローカルLLMモデル (VRAM 4GB以下向け)

| モデル名                        | 推奨量子化 | 必要VRAM            | 特徴                                              |
| ------------------------------- | ---------- | ------------------- | ------------------------------------------------- |
| **Qwen 2.5 3B Instruct**  | `Q4_K_M` | **約 2.4 GB** | **【本命】** 3Bクラス最強の日本語能力。     |
| **Gemma 2 2B Instruct**   | `Q4_K_M` | **約 1.8 GB** | **【最軽量】** Google製。超低スペック向け。 |
| **Llama 3.2 3B Instruct** | `Q4_K_M` | **約 2.4 GB** | Meta製。英語からの翻訳に強い。                    |

## 使い方（コマンドライン / 上級者向け）

```
python mod_translator.py -h
```

**1. 出力先をフルパスで指定する場合**

```
python mod_translator.py -i "mods" -o "C:\Users\User\Desktop\MyPack" --engine google
```

**2. Gemini API を使う場合**

```
python mod_translator.py -i "mods" -o "MyPack" --engine gemini --key "AIzaSy..."
```

**3. LM Studio を使う場合**

```
python mod_translator.py -i "mods" -o "MyPack" --engine lmstudio
```
