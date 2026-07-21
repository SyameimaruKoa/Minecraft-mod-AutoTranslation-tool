# Minecraft Mod Auto Translator (AI Powered)



[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/SyameimaruKoa/Minecraft-mod-AutoTranslation-tool/blob/main/run_colab_server.ipynb)



Minecraft の Mod ファイル（`.jar`）から言語ファイル（`en_us.json`）を抽出し、**Google 翻訳** または **生成 AI（Gemini / Local LLM / Cloud LLM via LM Link）** を用いて、高品質な日本語化リソースパックを全自動で生成するツールじゃ。



Mod ファイル本体（`.jar`）を書き換えることはなく「読み取り専用」で扱うため、 **Mod が破損する心配は一切ない** 。安全に日本語化を楽しめるぞ。



## 🚀 特徴



### 1. 選べる翻訳エンジン



- **Google 翻訳** : 完全無料、API キー不要。手軽に翻訳したい場合に最適。

- **Gemini AI (API使用空きがあれば推奨)** : Google の高性能 AI。文脈を理解した自然な翻訳が可能（要 API キー）。

  - **スマートモデル選択** : `gemini-2.5-flash-lite` や `gemma-3` などの最新モデルを使用。RPD（リクエスト制限）と TPM（トークン制限）を考慮し、**自動で最適なバッチサイズと待機時間**を調整する。

  - **Gemma 限定モード** : 高効率な「Gemma」モデルのみを使用するモード。Geminiが利用できない環境や、レート制限回避に最適。

- **Local / Cloud AI (Ollama / LM Studio / Google Colab)(推奨)** : ローカルPC、または Google Colab などの外部 GPU サーバーの LLM を使用。完全無料・無制限。

  - **LM Link 接続対応**: LM Studio の LM Link（アカウント連携）機能を利用し、Google Colab の強力な GPU をローカルPCの LM Studio と接続して、オフロード（身代わり推論）翻訳が行えるぞ。ローカルPCのGPUパワーが不足していても、クラウドで超高速翻訳が可能じゃ。



### 2. 使いやすい日本語 UI (PowerShell 対応)



- **完全日本語対応** : 起動スクリプトを `start.ps1` (PowerShell) に刷新。従来のバッチファイルで発生していた**文字化け問題を完全解消**し、親切な日本語案内で操作できる。

- **詳細な進捗表示** : 翻訳の進捗率（%）や、完了までの予想時間（ETA）をリアルタイムで表示する。

- **API キー自動保存** : 一度入力した Gemini API キーは `.env` ファイルに保存され、次回以降の入力を省略できる。



### 3. シェーダーパック翻訳対応



- **`.lang` ファイル対応** : Mod の `.json` だけでなく、シェーダーパック特Actions有の `.lang` ファイル（`key=value` 形式）も翻訳可能。

- **自動モード切替** : フォルダ名に `shader` が含まれている場合、自動的に「シェーダー翻訳モード」に切り替わり、適切なフォルダ構造で出力する。



### 4. 鉄壁のエラー対策 & 自動復帰



- **ドリルダウン・リトライ (Drill-down Retry)** : 翻訳中に一部の項目が欠落しても、スキップせずに「欠落分のみのミニバッチ」を作成し、即座に再翻訳を試みる。これにより、大容量バッチでも**翻訳漏れを許さない執念深い挙動**を実現した。

- **高度な JSON 修復機能 (Auto-Stitch)** : AI が大量のデータを処理する際、複数の JSON を連結して返したり（Extra data）、途中で途切れたりするケースがあるが、これらを自動的に検知・結合・修復するロジックを搭載。

- **自動フォールバック & 優先度復帰** : レート制限（429 エラー）が発生すると、自動的に別のモデルへ切り替えて翻訳を継続する。さらに、**30 分経過すると自動的に優先度の高いモデルへ復帰**し、効率を維持する。

- **スマート BAN (Smart Ban)** : 連続で失敗するモデルを一時的に除外する。応答しないモデルに時間を浪費せず、健全なモデルだけで処理を回す。



### 5. プロジェクト管理



- **プロジェクト別管理** : 翻訳キャッシュと進捗ログを出力リソースパックのフォルダ内に保存。複数の Mod パックを並行して翻訳してもデータが混ざらない。

- **中断・再開** : いつでも中断でき、同じ出力先を指定すれば続きから再開できる。



## 💻 必要要件



1. **Windows OS**

2. **PowerShell** （Windows に標準搭載されておる）

3. **Python 3.x**

   - インストール時、 **「Add Python to PATH」に必ずチェックを入れること** 。

4. **インターネット接続** （AI API 使用時）

5. **(Gemini モードのみ)** : Gemini API キー。

   - [Google AI Studio](https://aistudio.google.com/app/apikey) から無料で取得可能。

6. **(Local / Cloud AI モードのみ)** : [Ollama](https://ollama.com/) または [LM Studio](https://lmstudio.ai/)。

   - ローカルPCのスペックが不足している場合は、Google Colab 上で LM Link を起動して利用可能じゃ。
    <a href="https://colab.research.google.com/github/SyameimaruKoa/Minecraft-mod-AutoTranslation-tool/blob/main/run_colab_server.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>



## 📖 使い方（推奨手順）



基本的には、付属の **`run.bat`** をダブルクリックして対話形式で進めるのが一番簡単じゃ。



### 手順 1: 起動



フォルダ内の `run.bat` をダブルクリックする。



（これは PowerShell スクリプト `start.ps1` を安全に起動するためのラッパーじゃ。実行ポリシーを気にせず起動できるぞ）



初回起動時は、必要なライブラリ（deep-translator 等）が自動でインストールされるので、少し待つのじゃ。



### 手順 2: 翻訳エンジンの選択



メニューが表示されるので、数字キーを押して選択する。



- **[1] Google Translate** :

  - API キー不要。精度はそこそこだが、一番手軽。

- **[2] Gemini AI** :

  - **API キー**の入力を求められるので、コピー＆ペーストする。

  - キーは `.env` に保存するか選べるぞ。

  - その後、**「Gemma 限定モード」** を使うか聞かれる。

    - **[Y]** : `gemma-3` などのGemmaモデルのみを使用する。

    - **[N]** : Gemma限定にせず、優先リストに従ってFlashやProモデルなども含めて総力戦で翻訳する。(Proモデルを使う場合は自身で追加してください)

- **[3] LM Studio / Ollama / Google Colab (LM Link)** :

  - ローカル、または Google Colab 上の GPU で動作する LLM を使用する場合。

  - **Google Colab (LM Link) の場合** :

    1. 付属の [run_colab_server.ipynb](file:///c:/Users/kouki/Documents/MyApp/Minecraft-mod-AutoTranslation-tool/run_colab_server.ipynb) の「Open in Colab」バッジをクリックして Colab で開き、セルを実行して LM Studio の起動と `lms login` & `lms link enable` を完了する。

    2. ローカルPCの LM Studio でも同じアカウントでログインし、リモート接続を承認する。

    3. ローカルの LM Studio GUI から、モデルをダウンロード・ロードする（ColabのGPUにロードされるのじゃ）。

    4. 翻訳ツールは通常の **[3] LM Studio / Ollama** モードでローカル接続（`localhost:1234`）のまま実行すれば、自動的に Colab の GPU で翻訳が行われるぞ！

  - **LM Studio (ローカルPC) の場合** : 事前に LM Studio を起動し、モデルロードをした後、**「Developer」タブ（サーバーアイコン）** から **「Start Server」** を押しておくこと（ポート `1234`）。

  - 推奨LLMモデル

    - Qwen2.5-7B-Instruct-GGUF / Qwen2.5-Translate-GGUF (Colab等のGPU利用時)

      - オヌヌメ。翻訳精度と速度が優秀。

    - mmnga/plamo-2-translate-gguf (ローカルPC動作時)

      - 速度は少し遅いが高精度。また翻訳特化モデルのため破綻の心配が無い。



### 手順 3: フォルダの指定



1. **「翻訳したい Mod または シェーダーパック が入っているフォルダ」** をウィンドウにドラッグ＆ドロップして Enter。

2. **「出力するリソースパックの場所（名前）」** を入力。

   - 以前作成したフォルダを指定すると、**続きから翻訳を再開** できる。



### 手順 4: 翻訳開始



あとは待つだけじゃ。進捗バー（%表示と残り時間）が表示され、翻訳がガシガシ進んでいくぞ。



生成されたフォルダを Minecraft の resourcepacks（シェーダーの場合は shaderpacks 内の対象 zip を解凍して上書き、またはそのまま配置）に入れて適用せよ。



## 🔧 上級者向け（コマンドライン実行）



コマンドラインから直接 Python スクリプトを実行する場合の引数一覧じゃ。



### ヘルプの表示



```PowerShell

.\start.ps1 -h

# または

python mod_translator.py -h

```

