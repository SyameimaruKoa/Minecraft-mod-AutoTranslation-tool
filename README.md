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

### PLaMo 3 TranslateのGGUFモデルと選び方

PLaMo 3 Translateは翻訳専用モデル。**0.8B・2B・8B・31Bはパラメータ数の異なるモデル**で、Q4・Q5・Q6・Q8などは同じモデルを圧縮した量子化形式じゃ。量子化のビット数を上げてもモデルのパラメータ数は変わらない。

| モデル配布元 | 対応モデル | 特徴 |
|---|---|---|
| [pfnet公式](https://huggingface.co/pfnet/plamo-3-translate-8b-GGUF) | 0.8B / 2B / 8B / 31B | 公式の検証済みGGUF。8Bの既定はQ4_K_M（5.28GB） |
| [mradermacher 通常版](https://huggingface.co/mradermacher/plamo-3-translate-8b-GGUF) | 8B | Q5_K_M・Q6_K・Q8_0など公式にない量子化も選べる |
| [mradermacher i1版](https://huggingface.co/mradermacher/plamo-3-translate-8b-i1-GGUF) | 8B | imatrixによる重み付け量子化。Q5_K_M・Q6_K・IQ系などに対応 |

**推奨モデル（目安）**

| 実行環境 | 第一候補 | 理由 |
|---|---|---|
| Google Colab無料枠・T4（16GB） | mradermacher通常版 8B／Q8_0（約9.1GB） | GPUメモリに余裕があれば量子化誤差を抑えられる |
| RTX 2070／2070 Max-Q（8GB） | mradermacher i1版 8B／Q5_K_M（約6.1GB） | 全層GPUロード時のKVキャッシュ・作業メモリを確保しやすい |
| RTX 2070で短い文脈・精度優先 | 8B／Q6_K（約7.0GB） | VRAM使用量が多く、ロード可能か実測が必要 |
| Prestige-13-A13M-5009JP（i7-1355U／Iris Xe／32GB） | pfnet公式 8B／Q4_K_M（5.28GB） | 共有メモリ環境では容量よりメモリ帯域・推論速度を優先 |

- **公式Q4_K_Mは品質上も有力**：PFN公式の8B翻訳ベンチマークではBF16に近いスコア。非公式Q5・Q6・Q8との実翻訳比較値は未確認のため、精度向上を断定しない。
- **Colabでの選択**：`run_colab_server.ipynb`の設定セルで`model_source`を`pfnet`・`mradermacher`・`mradermacher-i1`から選ぶ。`plamo_size="8b"`にして`quantization`を指定。通常版Q8_0は`mradermacher`、i1-Q5_K_Mは`mradermacher-i1`じゃ。
- **取得方法**：pfnet公式は従来どおり既知のファイル名を使用。mradermacher版はHugging Faceのファイル一覧から量子化名とGGUF容量を確認して取得する。未配布の組み合わせは拒否し、他の実験的な量子化配布元は追加しない。
- **ローカルPC**：上記Hugging FaceのGGUFをLM Studioへインポートしてロードする。Colabノートブックは不要じゃ。
- **LM Linkの分散実行**：異なる量子化や配布元のモデルは`modelKey`が異なり得る。同じ翻訳プールに参加させるなら、実際の`modelKey`を各端末で一致させるのじゃ。

### LLM翻訳の並列処理

**Gemini・Ollama・LM Studio・PLaMo**で翻訳リクエストを複数同時に実行できる。Google Translateは対象外じゃ。

- CLI: `--workers 2`（直接実行時の既定）。PLaMoでは`--workers auto`でLM Studio公式の`config.parallel`に同時要求数を合わせる。PowerShellの対話起動ではPLaMoのみ`auto`を既定にし、Gemini・Ollama・その他LM Studioは2並列を維持する。公式APIで並列値を確認できない場合は2並列へフォールバックする。
- PowerShell: `.\start.ps1`のPLaMoは`auto`が既定。`.\start.ps1 -Workers 4`で4並列に固定できる。ほかのLLMの既定は2並列。
- Gemini: 既存のモデル優先順位・エラー時の切替・欠落項目の再試行を維持する。並列ワーカー間でモデル切替を同期し、モデル別のAPI送信間隔を共有するため、指定数を増やしてもレート制限を超えて連投しない。
- Ollama / LM Studio: 最大20件のJSONバッチを複数実行する。少数の項目も並列数に合わせて分割する。
- PLaMo: 同一モデルを搭載した複数端末へモデルごとに`--workers`件まで要求を同時送信する。LM Link自動検出時は実行中もモデル一覧を定期更新し、共通キューから空いたPCが次の仕事を取得する。原文の重複排除、書式保護、修復モデル、1件ごとのキャッシュ保存を維持する。対訳履歴は並列グループ内の順序を使うため、グループをまたぐ直前の対訳は共有しない。
- 並列タスクの完了順に依存せず、返す翻訳結果は入力キーの順序で整列する。PLaMoのキャッシュ書き込みはロックで直列化する。

例：

```powershell
python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --workers 4
.\start.ps1 -Workers 4
```

ローカルLLMで同時実行を増やしても、単一GPUの処理能力によっては速度が上がらない場合があるぞ。

### ColabのLM Link認証状態をGoogleドライブへ保存

`run_colab_server.ipynb`は`dbv4-wd14-tagger`のTailscaleと同じ方式で、LM Studioの認証状態を**そのままGoogleドライブに保存・次回自動復元**する。追加のパスフレーズやColabシークレットは不要じゃ。

- Googleドライブの既定保存先は`MyDrive/.colab-secret/lmstudio/`。設定セルで`USE_GOOGLE_DRIVE=True`、`DRIVE_FOLDER_NAME=".colab-secret"`を共有する。保存を無効化することもできる。
- 初回はLM Studioのブラウザ認証が必要。ログイン後に`credentials`と`hub`の認証ファイルを直接保存し、次回起動時に復元する。有効なログイン状態なら再認証しない。
- 内部デーモン用の`.internal`、モデル本体、ログは保存しない。ドライブ上の認証ファイルは追加暗号化せず保存されるため、ドライブの共有設定には注意すること。
- モデル取得は**pfnet公式／mradermacher通常版／mradermacher i1版**に対応し、**pfnet公式8B／Q4_K_Mを既定値**とする。mradermacher版は8Bのみ、Hugging Faceで確認できたGGUFファイルを直接取得。公式8B／31Bに存在しないQ4_0は拒否する。中断時は再開可能。`lms get`のインタラクティブ検索は使わない。LM Link一時無効化直後の`lms unload --all`が`connector_closed`などで失敗した場合は、既知の一時エラーに限って再試行する。モデル本体はランタイム上へ保存するため、再作成時には再ダウンロードする。

### LM Linkの複数デバイスでPLaMoを分散翻訳

**既定ではLM Link上でロード済みの、同じ`modelKey`のPLaMoを自動検出する。** 異なる端末で`identifier`が同じでもエラーにしないが、LM StudioのREST APIでは同一IDは1つの論理送信先となる。PLaMoの詳細設定では、**除外するデバイス名またはDevice identifierのみ**をカンマ区切りで指定する。空欄なら除外なしじゃ。

例：`Prestige-13-A13M,21KJ` と入力すると、それらの端末にあるPLaMoモデルを翻訳対象から除く。ローカル端末の除外には `local` または自端末名を指定できる。

```powershell
python mod_translator.py --engine plamo --input "C:\Minecraft\mods" --output "Output_Pack" --exclude-devices "Prestige-13-A13M,21KJ" --workers 2
```

除外なしなら `--exclude-devices` 自体を指定しない。PowerShellの詳細設定でもEnterで全端末を利用する。

- `lms ps --json`から現在ロード済みのモデル、モデルインスタンスID、`deviceIdentifier`を読み取り、各端末で翻訳用PLaMo 3 Translateが1つだけか検査する。同一端末に複数ある場合は自動選択せずエラーとする。修復用LFMは対象外。除外が指定された場合は `lms link status --json` から端末名とIDを照合する。LM StudioのCLIが必要じゃ。
- **分散先の翻訳用PLaMoはすべて`modelKey`が完全一致する必要がある。** 例えばPC-Aに8B＋修復用LFM、PC-Bに同じ8Bなら可。PC-Aが8BでPC-Bが2Bなら停止する。同じ8Bでも`modelKey`が違えば停止する。`modelKey`の一致はファイルハッシュの一致を保証しない。
- 明示された除外端末が見つからない場合、除外後に利用可能なPLaMoがない場合はエラーで停止する。自動ロードしない。
- LM Link端末の翻訳用インスタンスIDは`lms ps --json`から取得し、モデル一覧API上の別名で上書きしない。複数端末に同じIDがある場合は重複を統合し、REST APIで実際に区別できる送信先だけを翻訳プールへ登録する。
- **同じ`identifier`・同じ`modelKey`が複数端末にある場合も起動可能**。インスタンスIDの変更は不要じゃ。ただし、LM Linkの通常REST APIは優先デバイスへ送信し、同じIDの複数PCへ要求を分散しない。端末を指定して除外しても同じIDが別端末に残る場合は、除外の保証ができないためエラーとする。
- `--model`を指定すると、そのモデル名またはインスタンスIDのみに絞り込める。従来の `--plamo-models` は互換性のため残してあるが、除外指定と同時には使用できない。
- **翻訳中のモデル増減:** LM Linkを5秒間隔で監視し、最初に選択した`modelKey`と完全一致する新しい論理送信先（異なる`identifier`）を追加する。消えた論理送信先の未完了バッチは残存先へ再割当し、論理送信先が2回連続で0になった場合に停止する。同じIDの端末が増えても新しいREST送信先にはならない。一時的なモデル一覧取得失敗は最大3回再試行する。
- **速度差の吸収:** REST APIから個別に指定できる複数の論理モデルIDがある場合は共有キュー方式を使い、空いたモデルが次のバッチを取得する。末尾の遅延バッチ再割当と、一時的な通信不能モデルの隔離にも対応する。同じIDを持つ複数端末は個別の推論先として区別できないため、この方式だけでは2台の負荷を分散できない。
- **Colab GPU:** ノートブックはPLaMoロード時に公式の`lms load --gpu max --parallel N`を指定する。既存のGPU KVキャッシュ・Flash Attentionを維持し、VRAM消費率を上げるだけを目的としてコンテキスト長や並列数を無理に拡張しない。Windowsの`--workers auto`はロード済みの`parallel`値を取得して同時要求数を合わせる。
- **補助モデル:** LFMなどの構文修復モデルはこの翻訳用モデルの参加・離脱監視の対象外で、従来の修復動作を維持する。
- LM Link自動検出では、同じ`modelKey`のPC間で翻訳・修復キャッシュを共有する。PCの増減で同一文章を再翻訳せず、項目ごとの保存件数も増やさない。従来のモデルインスタンスID別キャッシュも読み取り可能じゃ。明示的な`--plamo-models`のキャッシュは従来どおりインスタンスID別とする。
- 原文の重複排除と構文修復用LFMは従来どおりじゃ。

LM Studio公式の [LM Link REST APIの仕様](https://lmstudio.ai/docs/developer/core/lmlink) では、複数端末で同じモデルIDが使われる場合、要求は優先デバイスへ送られる。起動エラーを回避することと、同一IDの複数端末を独立して並列利用することは別じゃ。後者には端末別にアクセスできる独立したAPI接続先などが必要となる。

### LM Linkクラスター（Windows・Linux・Colab共通／localhostのみ）

LM StudioまたはllmsterとLM Linkが使える端末なら、OSや台数に関係なくクラスターへ参加できる。**同じ`modelKey`のPLaMoを各PCでロードし、端末ごとに異なる`identifier`を付ける**。翻訳を実行するPCが`lms ps --json`を監視し、追加・離脱した端末へ共有キューから仕事を分配する。LM Link以外のネットワーク公開は不要じゃ。

**各Windows/Linux PCで、モデルがロード済みの場合：**

```bash
python3 plamo_identifier.py --join --yes
```

Windowsの既存仮想環境からなら`venv\\Scripts\\python.exe plamo_identifier.py --join --yes`でもよい。モデルIDは端末名と固有識別子から作るため、Windows PC・Linux PCが増えても手動で別名を考える必要はない。同じPCで再実行してもIDが同じなら変更しない。

**そのPCではまだPLaMoをロードしていない場合：**

```bash
python3 plamo_identifier.py --join --model-key "pfnet/plamo-3-translate-8b-GGUF/plamo-3-translate-8b-Q4_K_M.gguf" --yes
```

`--model-key`にはそのPCの`lms ls`で確認できる**実際のモデルキー**を指定する。別のモデルを推測して選択することはない。

- Windows対話メニュー: `start.ps1`の`[5] このPCをLM Link翻訳クラスターへ参加させて翻訳する`でID自動設定と翻訳開始が可能。
- Colabの設定GUI: `run_colab_server.ipynb`の`MODEL_IDENTIFIER`で端末固有ID（例: `plamo-3-translate-8b-colab`）を指定。空欄なら従来の標準ID。
- 各OS共通のCLI: `python3 plamo_identifier.py --list`でモデル一覧、`--interactive`で任意のIDへ変更、`--join`で端末固有IDを自動設定。必要に応じて`--current-id`・`--new-id`・`--yes`も利用できる。
- 翻訳の実行: 参加端末すべてで翻訳ツールを動かす必要はない。任意の1台から従来どおり`--engine plamo`を実行するだけで、同じ`modelKey`のロード済み端末を5秒間隔で自動検出する。
- 端末が離脱しても残存モデルへ未処理分を再割当し、ETAは稼働中のPC別実測速度を反映する。LFMなどの構文修復モデルは対象外。ID変更時にローカルREST APIが未起動なら公式`lms ps`の情報で再ロードし、失敗したら元のIDへ復元する。
- 同一`identifier`を複数PCで共有するとLM Linkは優先デバイスへルーティングするため、クラスター参加コマンドで個別IDにする。実機での各端末への配送はまだ検証が必要じゃ。

### 同じモデルIDの複数PCで実際に並列推論する

LM Linkの単一REST接続先では、複数端末で同じIDを使う場合に優先デバイスへルーティングされる。**同じIDのまま複数PCへ確実に分散させる場合は、PCごとの独立したLM Studio APIアドレスを指定する**。

```powershell
python mod_translator.py --engine plamo --model plamo-3-translate-8b --plamo-hosts "http://127.0.0.1:1234,http://100.64.0.2:1234" --repair-model lfm3-1.7b --workers 2 --input "C:\Minecraft\mods" --output "Output_Pack"
```

- `--plamo-hosts`はそれぞれ独立したLM Studio APIのURLをカンマで指定する。指定先ではAPIサーバーが起動し、Windowsから到達できる必要がある。例の`100.64.0.2`は実際にアクセスできる端末のプライベートIPへ置き換える。
- 全接続先で**同じ`--model`のインスタンスID**と、同じ`modelKey`・量子化形式・ファイルサイズを確認する。端末ごとのID変更は不要。異なるモデルは混ぜない。
- 各接続先へ`--workers`件まで並列リクエストを送り、速度差は共有キューで吸収する。動作中の接続先の復帰・離脱も検出する。追加の接続先は次回起動時に`--plamo-hosts`へ含める必要がある。
- 構文修復用LFMは従来どおり`--repair-api-url`を使い、この分散対象には含めない。
- `--plamo-hosts`は`--exclude-devices`および`--plamo-models`との併用不可。未指定なら従来のLM Link自動検出を使う。
- LM Linkは他のアプリ向けに端末のHTTPサーバーを公開する機能ではない。Colabで同じ方式を使用するには、別途Windowsから到達できるプライベート接続が必要じゃ。

### PLaMo 3 Translateの翻訳品質を高める設定

PLaMo 3 Translate公式の**参考文脈（context）・用語集（glossary）・対訳履歴（translation history）**を、`/v1/completions`へ送るPFML3に組み込んでおる。LM Studioはこれまでどおり利用可能じゃ。

- **自動参考文脈:** Mod名と各言語ファイルの共通文脈を利用する。キーごとの文脈を含めると共通プレフィックスが変化するため、既定では省き、必要な場合だけ`--plamo-key-context`で有効化する。独自の背景説明は`--plamo-context`または`--plamo-context-file`で追加できる。
- **用語集:** `plamo_glossary.example.json`をコピー・編集して`--plamo-glossary`へ指定する。原語と訳語を固定できる。**一般用語は指定された用語集のみ使用する。`%s`等の書式指定子・改行・装飾コードの保護タグは、必要な文章だけ内部の用語集に自動追加する。**
- **対訳履歴:** 同一言語ファイルで直前に翻訳した短い文章を最大3件参考にする（`--plamo-history 0`で無効化、最大10）。プロンプトキャッシュを効かせるため、対訳履歴は既定で16件翻訳するごとに更新する（`--plamo-history-refresh 1`で従来の毎回更新に戻せる）。履歴と訳語の一貫性を保ちながら、共通プロンプトの再評価を減らす。
- **堅牢性:** 番号付き`%1$s`・`%2$s`の語順入替を許容し、番号なしの書式、`<amount>`の変数、改行の欠落を防ぐ。`%s`など書式のみの項目は推論せずそのまま保存する。本文中の書式指定子は一時タグに置換して保護する。`Anvil Cost: %s`など末尾に書式がある設定ラベルは文字部分だけ翻訳し、書式と区切り記号を後から復元する。Java版の`§a`・`§l`などの装飾コードに加え、実際の改行・文字列の`\\n`も一時的なプレースホルダーに置き換え、文章全体を一度に翻訳してから復元する。保護タグを原語＝訳語としてPLaMo公式用語集にも追加し、全文翻訳を優先する。タグの欠落や順序変更が起きた場合は、改行単位で再翻訳して元の改行を保持する。`&a`などはプラグイン等による代替表記であり、Mod・シェーダー向けの保護対象には含めない。0.8Bモデルが書式指定子を余分に生成した場合は同一条件での再試行を省き、原文を保持する。長文は出力上限を拡張し、打切り時は増やして再試行する。
- **失敗診断:** 出力先の`plamo_failures.json`に、未解決の翻訳項目をMod名・言語ファイル・翻訳キーごとに記録する。原文（省略なし）、PLaMoの失敗訳と生応答、翻訳モデル、補助モデル、LFMの生応答・終了理由・解析エラーを保存し、成功後は該当項目を自動削除する。LFMが空文字を返した場合も`""`として記録し、問い合わせ自体がなければ`null`とする。
- **事前スキャン:** 翻訳前に全Modの言語ファイルを検査し、残りのユニーク翻訳件数と全体の推定時間を表示する。解析結果は出力先の`mod_scan_cache.json`に保存し、次回以降はサイズ・更新日時が変わらないModを再解析しない。追加・更新したModだけを新規解析し、削除したModはスキャン結果から除外する。既存の翻訳キャッシュは引き続き独立して判定する。
- **速度履歴・完了予定:** `plamo_speed.json`に使用モデルとモデルごとの同時実行数に対応した実測速度を保存する。再開時は前回の実測値から開始前に予測時間と完了予定日時を表示する。処理中はMod単位で計測をリセットせず、全Modの累積進捗と実測速度を用いて残り時間・完了予定日時を更新する。
- **キャッシュ:** PLaMo専用`plamo_cache.json`にMod・キー・モデル・用語集・文脈ごとに保存する。翻訳が1件成功するたびに保存するので途中でサーバーが切れてもそれまでの訳文が残る。既存`trans_cache.json`は従来のエンジン用として保持する。
- **翻訳言語:** Modの同一名前空間では日本語以外の言語ファイルから項目数の多いものを翻訳元に採用するため、ロシア語（`ru_ru`）などが翻訳元になる場合がある。PLaMoの出力言語は常に日本語（`ja`）。生成結果がロシア語だけなら再翻訳し、同じ誤訳をキャッシュから再利用しない。
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

### PLaMoの書式指定子と日本語の語順

`%d`・`%s`など番号なし引数がある英文では、日本語の自然な語順で引数が逆転する場合がある。PLaMoが保護マーカーを並べ替えたとき、引数の値が入れ替わらないように**原文の引数番号に対応する位置指定形式**に置き換えるのじゃ。

例：`%d slots of type %s have been added to %s` → `%3$sに%2$sタイプのスロットが%1$d個追加されました`。この形式はJavaの位置指定書式を利用する。引数が逆転しなければ元の`%d`・`%s`を維持する。欠落・重複・型違いの書式指定子は従来どおり不採用じゃ。

LFMによる構文修復で日本語の語順に合わせた挿入位置が逆順になっても、対象がprintf引数だけなら位置指定形式で復元できる。色コードなどが混在する場合は勝手に並べ替えない。PLaMoが生成した日本語本文の変更は従来どおり禁止する。

### PLaMo専用：2モデルによる構文修復

PLaMoの翻訳で書式が破損した場合に限り、別のLM Studioモデルへ修復を依頼できる。修復モデルは固定ではなく、`--repair-model`でロード済みの任意のLLMを指定できる（LFM2.5など）。省略すると従来のPLaMo単独動作となる。汎用の`lmstudio`・`ollama`エンジンには適用しない。

- PLaMoと修復モデルはLM Studioで**両方とも手動ロード**する。CPU/GPUオフロードの設定はLM Studio側で行う。
- モデルのロード状態は`/api/v1/models`（旧版は`/api/v0/models`）で確認し、本ツールからロードAPIは呼ばない。
- 未ロード時は**手動ロードされるまで自動待機**し、手動ロード後に処理を再開する（`--model-load-policy wait`と同じ）。エラー終了の選択は不要。
- モデルを切り替える場合は`--repair-model`のIDを変更する。修復結果はモデル別に`plamo_cache.json`へ保存する。
- 構文修復に失敗した場合、標準出力にも英語原文・翻訳キー・PLaMo生応答・LFM生応答・終了理由・失敗理由を表示する。補助モデルによる日本語の書き換えは行わない。
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

