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

- **PLaMo 3 Translate** : LM StudioのOpenAI互換Completions APIに接続し、公式PFML3形式で翻訳する。

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

    3. Colab ノートブック側の「3. 翻訳モデルのダウンロードとロード」セルを実行し、モデル（例: `Qwen2.5-7B-Instruct-GGUF`）を Colab 側にダウンロード・ロードさせるのじゃ。（ロード完了後、ローカルPCの LM Studio 上で「Linked (リンク済み)」モデルとして認識されるぞ）

    4. 翻訳ツールは通常の **[3] LM Studio / Ollama** モードでローカル接続（`localhost:1234`）のまま実行すれば、自動的に Colab の GPU で翻訳が行われるぞ！

  - **LM Studio (ローカルPC) の場合** : 事前に LM Studio を起動し、モデルロードをした後、**「Developer」タブ（サーバーアイコン）** から **「Start Server」** を押しておくこと（ポート `1234`）。

  - 推奨LLMモデル

    - Qwen2.5-7B-Instruct-GGUF / Qwen2.5-Translate-GGUF (Colab等のGPU利用時)

      - オヌヌメ。翻訳精度と速度が優秀。

    - mmnga/plamo-2-translate-gguf (ローカルPC動作時)

      - 速度は少し遅いが高精度。また翻訳特化モデルのため破綻の心配が無い。



- **[4] PLaMo 3 Translate（LM Studio）** :

  - Preferred Networksの翻訳特化モデルを**LM Studio**から利用する。llama.cppを別途起動する必要はない。
  - 公式のPFML3形式で英語から日本語に翻訳し、既存のキャッシュ・中断再開機能を使用する。
  - 重複文字列は1回だけ翻訳する。`§a`などの色コード、`%s`などの書式指定子、`{name}`などの変数を照合し、壊れた訳文は再試行して採用しない。
  - **セットアップ:**
    1. LM Studioの「Discover」から[公式PLaMo 3 Translate 2B GGUF](https://huggingface.co/pfnet/plamo-3-translate-2b-GGUF)（例: Q4_K_M）をダウンロードする。見つからなければGGUFを入手し、[LM Studioへインポート](https://lmstudio.ai/docs/app/advanced/import-model)する。
    2. LM StudioでPLaMo 3 Translateをロードし、「Developer」タブでAPIサーバーを**Start Server**する（通常はポート1234）。
    3. `run.bat`を実行し、メニュー**[4]**を選ぶ。URLはEnterで標準値（`http://127.0.0.1:1234/v1/completions`）。
    4. モデルIDはEnterで自動検出する。複数のPLaMoモデルが見つかる場合は、LM StudioのモデルID（`GET http://localhost:1234/v1/models`で確認可能）を入力する。
    5. 日本語の文体を選択する（標準は常体、選択で敬体）。
  - **コマンドラインから実行（例）:**

    ```powershell
    python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --plamo-form plain
    ```

  - APIサーバーの接続先変更は`--plamo-api-url`、モデルIDの直接指定は`--model`を使用する。キャッシュにある文章を翻訳し直す場合は`--force`を併用する。
  - 公式モデルの0.8B・2B・8B・31B（GGUF対応）から適切なサイズを選べる。モデルの詳細は[公式モデルカード](https://huggingface.co/pfnet/plamo-3-translate-2b-GGUF)を参照。

### LLM翻訳の並列処理

**Gemini・Ollama・LM Studio・PLaMo**で翻訳リクエストを複数同時に実行できる。Google Translateは対象外じゃ。

- CLI: `--workers 2`（既定）、`--workers 1`で逐次実行。並列数は1以上を指定する。
- PowerShell: `.\start.ps1 -Workers 4`（既定は2）。対話メニューに質問は追加しない。
- Gemini: 既存のモデル優先順位・エラー時の切替・欠落項目の再試行を維持する。並列ワーカー間でモデル切替を同期し、モデル別のAPI送信間隔を共有するため、指定数を増やしてもレート制限を超えて連投しない。
- Ollama / LM Studio: 最大20件のJSONバッチを複数実行する。少数の項目も並列数に合わせて分割する。
- PLaMo: 原文の重複排除、書式保護、修復モデル、1件ごとのキャッシュ保存を維持する。対訳履歴は並列グループ内の順序を使うため、グループをまたぐ直前の対訳は共有しない。
- 並列タスクの完了順に依存せず、返す翻訳結果は入力キーの順序で整列する。PLaMoのキャッシュ書き込みはロックで直列化する。

例：

```powershell
python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --workers 4
.\start.ps1 -Workers 4
```

ローカルLLMで同時実行を増やしても、単一GPUの処理能力によっては速度が上がらない場合があるぞ。

### LM Linkの複数デバイスでPLaMoを分散翻訳

**既定ではLM Link上でロード済みのPLaMoモデルをすべて使用する。** モデルIDや使用デバイスを指定する必要はない。PLaMoの詳細設定では、**除外するデバイス名またはDevice identifierのみ**をカンマ区切りで指定する。空欄なら除外なしじゃ。

例：`Prestige-13-A13M,21KJ` と入力すると、それらの端末にあるPLaMoモデルを翻訳対象から除く。ローカル端末の除外には `local` または自端末名を指定できる。

```powershell
python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --exclude-devices "Prestige-13-A13M,21KJ" --workers 2
```

除外なしなら `--exclude-devices` 自体を指定しない。PowerShellの詳細設定でもEnterで全端末を利用する。

- `lms ps --json`から現在ロード済みのモデル、モデルインスタンスID、`deviceIdentifier`を読み取り、PLaMo 3 Translateだけを自動抽出する。除外が指定された場合は `lms link status --json` から端末名とIDを照合する。LM StudioのCLIが必要じゃ。
- 明示された除外端末が見つからない場合、除外後に利用可能なPLaMoがない場合はエラーで停止する。自動ロードしない。
- **同じモデルインスタンスIDが複数端末に存在する場合、APIから送信先を区別できない可能性があるため停止する。** その場合はLM Studioでインスタンスごとに異なるIDを割り当てる必要がある（例：`lms load <model-key> --identifier plamo-local`）。誤って除外端末へ送信することを防ぐためじゃ。
- `--model`を指定すると、そのモデル名またはインスタンスIDのみに絞り込める。従来の `--plamo-models` は互換性のため残してあるが、除外指定と同時には使用できない。
- モデルごとの翻訳キャッシュ、重複文章の統合、構文修復用LFMは従来どおりじゃ。

LM Link自体は、同一モデルの通常のAPI呼び出しを優先デバイスに送る仕様じゃ。そのため本ツールは`lms ps --json`の識別情報を確認し、区別不能なら黙って誤配送せず停止する。実機での複数デバイス配分は別途検証が必要じゃ。

### PLaMo 3 Translateの翻訳品質を高める設定

PLaMo 3 Translate公式の**参考文脈（context）・用語集（glossary）・対訳履歴（translation history）**を、`/v1/completions`へ送るPFML3に組み込んでおる。LM Studioはこれまでどおり利用可能じゃ。

- **自動参考文脈:** Mod名と各言語ファイルの共通文脈を利用する。キーごとの文脈を含めると共通プレフィックスが変化するため、既定では省き、必要な場合だけ`--plamo-key-context`で有効化する。独自の背景説明は`--plamo-context`または`--plamo-context-file`で追加できる。
- **用語集:** `plamo_glossary.example.json`をコピー・編集して`--plamo-glossary`へ指定する。原語と訳語を固定できる。**一般用語は指定された用語集のみ使用する。`%s`等の書式指定子・改行・装飾コードの保護タグは、必要な文章だけ内部の用語集に自動追加する。**
- **対訳履歴:** 同一言語ファイルで直前に翻訳した短い文章を最大3件参考にする（`--plamo-history 0`で無効化、最大10）。プロンプトキャッシュを効かせるため、対訳履歴は既定で16件翻訳するごとに更新する（`--plamo-history-refresh 1`で従来の毎回更新に戻せる）。履歴と訳語の一貫性を保ちながら、共通プロンプトの再評価を減らす。
- **堅牢性:** 番号付き`%1$s`・`%2$s`の語順入替を許容し、番号なしの書式、`<amount>`の変数、改行の欠落を防ぐ。`%s`など書式のみの項目は推論せずそのまま保存する。本文中の書式指定子は一時タグに置換して保護する。`Anvil Cost: %s`など末尾に書式がある設定ラベルは文字部分だけ翻訳し、書式と区切り記号を後から復元する。Java版の`§a`・`§l`などの装飾コードに加え、実際の改行・文字列の`\\n`も一時的なプレースホルダーに置き換え、文章全体を一度に翻訳してから復元する。保護タグを原語＝訳語としてPLaMo公式用語集にも追加し、全文翻訳を優先する。タグの欠落や順序変更が起きた場合は、改行単位で再翻訳して元の改行を保持する。`&a`などはプラグイン等による代替表記であり、Mod・シェーダー向けの保護対象には含めない。0.8Bモデルが書式指定子を余分に生成した場合は同一条件での再試行を省き、原文を保持する。長文は出力上限を拡張し、打切り時は増やして再試行する。
- **キャッシュ:** PLaMo専用`plamo_cache.json`にMod・キー・モデル・用語集・文脈ごとに保存する。翻訳が1件成功するたびに保存するので途中でサーバーが切れてもそれまでの訳文が残る。既存`trans_cache.json`は従来のエンジン用として保持する。
- **既存キャッシュの継続利用:** この最適化以前の`plamo_cache.json`も読み込む。ただし以前の分割方式で生成された可能性がある`§`装飾付きの訳文だけは再翻訳し、それ以外はキャッシュを再利用する。

例：用語集ファイル（`plamo_glossary.example.json`を編集して使用）

```json
{
    "Tin": "スズ",
    "Digital Miner": "デジタルマイナー",
    "Redstone": "レッドストーン"
}
```

例：参考文脈ファイル（UTF-8の任意のテキスト）

```text
This is the translation of item names and tooltips for a technology-focused Minecraft mod.
「bank」が川や川岸を指す場面では、その情景を参考に翻訳する。
```

コマンドラインから指定するときの例：

```powershell
python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --plamo-glossary "plamo_glossary.example.json" --plamo-context-file "my_mod_context.txt" --plamo-history 3
```

`run.bat`の[4]メニューでも用語集・文脈ファイル・履歴数を指定できる。なお、用語集の内容を変更すると設定別キャッシュを切り替えて翻訳をやり直す設計じゃ。

### PLaMo専用：2モデルによる構文修復

PLaMoの翻訳で書式が破損した場合に限り、別のLM Studioモデルへ修復を依頼できる。修復モデルは固定ではなく、`--repair-model`でロード済みの任意のLLMを指定できる（LFM2.5など）。省略すると従来のPLaMo単独動作となる。汎用の`lmstudio`・`ollama`エンジンには適用しない。

- PLaMoと修復モデルはLM Studioで**両方とも手動ロード**する。CPU/GPUオフロードの設定はLM Studio側で行う。
- モデルのロード状態は`/api/v1/models`（旧版は`/api/v0/models`）で確認し、本ツールからロードAPIは呼ばない。
- 未ロード時は**手動ロードされるまで自動待機**し、手動ロード後に処理を再開する（`--model-load-policy wait`と同じ）。エラー終了の選択は不要。
- モデルを切り替える場合は`--repair-model`のIDを変更する。修復結果はモデル別に`plamo_cache.json`へ保存する。
- **翻訳はPLaMoだけ**が担当する。Pythonは両端の書式を自動復元し、複雑な場合のみ補助モデルへ**構文トークンの挿入位置（整数の配列）**を問い合わせる。補助モデルに日本語の文章を生成させず、PythonがPLaMoの日本語本文へ構文を挿入する。書式なしの本文が記号だけ（例：`Config`に対する`%s: %s`）なら修復を依頼せず原文維持とし、過去に保存された記号だけの不正な修復キャッシュも再利用しない。構文・本文の不変条件を検証し、修復は1つのワーカーで翻訳と並行して進める。修復前後の内容と成否を表示し、最後に件数を集計する。
- LM Studioの**Just in Time Model Loading**は無効にすると、推論要求による自動ロードを防げる。両モデルを手動ロードしたまま運用する。

PowerShellの起動メニュー[4]は**修復モデルID（空欄で無効）**と**詳細設定（通常はN）**の2項目のみを質問する。PLaMoモデルは自動検出し、用語集・文体・接続先・履歴の変更は詳細設定にまとめてある。未ロード時の選択はなく、手動ロードを待機する。

例（モデルIDはLM Studioでロードした実際の識別子へ置き換える）：

```powershell
python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --model "plamo-3-translate-0.8b" --repair-model "lfm2.5-1.2b-instruct"
```

修復モデルが別のLM Studioサーバーにある場合は、`--repair-api-url`で`http://127.0.0.1:1234/v1/chat/completions`とは異なる接続先を指定する。

### 検証コマンド

Pythonのライブラリは必ず仮想環境へインストールする。既存の`venv`があれば流用可能。

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install deep-translator requests python-dotenv
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

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

