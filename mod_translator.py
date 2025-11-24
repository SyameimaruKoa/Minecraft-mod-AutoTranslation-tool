import os
import json
import time
import re
import argparse
import zipfile
import requests
import traceback
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator

# --- 定数設定 ---
DEFAULT_FORMAT_FALLBACK = 34  # pack.mcmetaが見つからない場合のデフォルトバージョン
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
)
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models?key={}"
OLLAMA_API_URL = "http://localhost:11434/api/chat"
LMSTUDIO_API_URL = "http://localhost:1234/v1/chat/completions"

# 翻訳除外キー（これらは翻訳しない）
IGNORE_KEYS = [
    "pack.mcmeta",
    "pack.description",
    "_comment",
    "language.name",
    "language.region",
    "language.code",
]

# エラー検出用キーワード（これらが含まれていたら翻訳失敗とみなして削除・再翻訳する）
ERROR_KEYWORDS = [
    "Error 504",
    "HTTP 429",
    "Model overloaded",
    "Internal Server Error",
    "quota exceeded",
    "Too Many Requests",
    "Service Unavailable",
]

# 優先モデルリスト（ユーザー指定）
# デフォルトの優先順位（RPD > TPM > RPM の順）
# 更新されたレート制限に基づき、RPD（スタミナ）とRPM（速度）のバランスで再構成
DEFAULT_PRIORITY = [
    # 1. Gemini 2.5 Flash-Lite (RPD 1,000 / RPM 15)
    # バランス最高。まずはこれから消費する。
    "gemini-2.5-flash-lite",
    # 2. Gemini 2.0 Flash-Lite (RPD 200 / RPM 30)
    # 速度は最速だが、回数制限がきつい。2.5 Liteが尽きたら、バッチサイズ特大で回す。
    "gemini-2.0-flash-lite",
    # 3. Gemma 3系 (RPD 14,400 / TPM 15,000)
    # Lite系が尽きた後の長期戦用
    "gemma-3n-e2b-it",
    "gemma-3n-e4b-it",
    "gemma-3-27b-it",
    "gemma-3-12b-it",
    "gemma-3-8b-it",
    "gemma-3-4b-it",
    "gemma-3-1b-it",
    # 4. Gemini 2.5 Flash (RPD 250 / RPM 10)
    # 標準モデル。速度はそこそこ。
    "gemini-2.5-flash",
    # 5. その他・旧世代
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

# --- ヘルパー関数 ---


def get_model_settings(model_name):
    """
    モデル名に基づいて、最適なバッチサイズ（行数）とリクエスト間隔（秒）を返す。
    2025/11/24 時点の最新レート制限表に基づき調整。
    """
    if not model_name:
        return 45, 2.0  # デフォルト

    name = model_name.lower()

    # デフォルト値
    batch_size = 40
    interval = 5.0

    if "gemma" in name:
        # Gemma 3 (RPM 30 / TPM 15,000 / RPD 14,400)
        # TPM 15kがボトルネック。1リクエストあたりのトークンを抑えないとエラーになる。
        # 行数を極端に減らし、回転数(RPM 30=2秒間隔)で稼ぐ。
        batch_size = 5  # 安全圏
        interval = 2.1  # RPM 30 ギリギリより少し余裕を持つ

    elif "gemini-2.5-flash-lite" in name:
        # RPD 1k, TPM 250k.
        # Max tokens per req ~16k. Batch 300 is safe and efficient.
        batch_size = 300
        interval = 5.0

    elif "gemini-2.0-flash-lite" in name:
        # RPD 200, TPM 1M.
        # Extremely high throughput allowed.
        batch_size = 400
        interval = 4.0

    elif "gemini-2.5-flash" in name:
        # Gemini 2.5 Flash (RPM 10 / TPM 250,000 / RPD 250)
        # RPM 10 (6秒間隔) と遅め。
        batch_size = 50
        interval = 6.2  # RPM 10 (6秒) + マージン

    elif "gemini-2.0-flash" in name:
        # RPD 200, TPM 1M.
        batch_size = 350
        interval = 5.0

    elif "pro" in name:
        batch_size = 60
        interval = 32.0

    return batch_size, interval


def get_available_gemini_models(api_key):
    """APIキーを使用して現在利用可能なモデル一覧を取得する"""
    try:
        url = GEMINI_MODELS_URL.format(api_key)
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = [m["name"].replace("models/", "") for m in data.get("models", [])]
            return models
        else:
            print(f"警告: モデル一覧の取得に失敗しました (HTTP {response.status_code})")
            return []
    except Exception as e:
        print(f"警告: モデル一覧取得中にエラーが発生: {e}")
        return []


def get_prioritized_models(api_key, lite_only=False):
    """
    優先順位リストと利用可能なモデルを照らし合わせて、
    利用可能なモデルのリストを優先度順に返す。
    """
    print("情報: 利用可能なGeminiモデルを探索中...")
    available_models = get_available_gemini_models(api_key)

    if not available_models:
        fallback = [DEFAULT_PRIORITY[0]]
        print(
            f"警告: モデル一覧が取得できなかったため、デフォルトの {fallback[0]} を使用します。"
        )
        return fallback

    valid_models = []

    # 優先リスト順にチェック
    for candidate in DEFAULT_PRIORITY:
        if lite_only and "lite" not in candidate.lower():
            continue
        if candidate in available_models:
            valid_models.append(candidate)

    if not valid_models:
        if lite_only:
            print(
                "警告: Liteモデルが見つかりませんでした。gemini-2.5-flash-lite を強制使用します。"
            )
            return ["gemini-2.5-flash-lite"]
        else:
            print(
                "警告: 優先リスト内のモデルが見つかりませんでした。gemini-2.0-flash を使用します。"
            )
            return ["gemini-2.0-flash"]

    print(f"情報: {len(valid_models)} 個の有効なモデルが見つかりました。")
    return valid_models


class ModelSelector:
    """
    モデルの選択、切り替え、無効化、復帰を管理するクラス
    """

    def __init__(self, models):
        self.models = models  # 優先度順のモデルリスト
        self.current_idx = 0
        self.disabled_models = set()  # 使用不可になったモデル
        self.failure_counts = {m: 0 for m in models}  # モデルごとの連続失敗回数
        self.fallback_start_time = None  # フォールバック開始時刻

    def get_current_model(self):
        """現在使用すべきモデルを返す。必要に応じて復帰やスキップを行う。"""

        # 1. 復帰チェック: フォールバック中で30分経過していれば、優先度の高いモデルへの復帰を試みる
        if self.fallback_start_time and (time.time() - self.fallback_start_time > 1800):
            self._try_recover_priority()

        # 2. 無効なモデルをスキップして、使えるモデルを探す
        original_idx = self.current_idx
        while self.current_idx < len(self.models):
            model = self.models[self.current_idx]
            if model not in self.disabled_models:
                return model
            self.current_idx += 1

        # 3. もし最後まで到達してしまったら（全滅）
        # 一時的に全モデルの無効化を解除して、最初から再試行させる（無限ループ防止）
        print(
            "警告: 全てのモデルが使用不可になりました。制限をリセットして再試行します。"
        )
        self.disabled_models.clear()
        self.failure_counts = {m: 0 for m in self.models}
        self.current_idx = 0
        self.fallback_start_time = None
        return self.models[0]

    def _try_recover_priority(self):
        """より優先度の高い（インデックスが小さい）モデルが使えるか確認し、戻す"""
        best_available_idx = -1
        for i, m in enumerate(self.models):
            if m not in self.disabled_models:
                best_available_idx = i
                break

        if best_available_idx != -1 and best_available_idx < self.current_idx:
            print(
                f"情報: 1分経過。優先度の高いモデル [{self.models[best_available_idx]}] に復帰を試みます。"
            )
            self.current_idx = best_available_idx
            self.fallback_start_time = None
            # 復帰したモデルの失敗カウントはリセットしておく
            self.failure_counts[self.models[best_available_idx]] = 0

    def report_success(self):
        """成功を報告。カウントをリセットする。"""
        model = self.models[self.current_idx]
        self.failure_counts[model] = 0

        # もし現在、最高優先度のモデルを使っているなら、フォールバックタイマーをクリア
        if self.current_idx == 0 or all(
            self.models[i] in self.disabled_models for i in range(self.current_idx)
        ):
            self.fallback_start_time = None

    def report_failure(self):
        """
        失敗を報告。
        Returns:
            str: "continue" (そのまま再試行), "switched" (モデル切り替え), "disabled" (無効化して切り替え)
        """
        if self.current_idx >= len(self.models):
            return "continue"

        model = self.models[self.current_idx]
        self.failure_counts[model] += 1
        count = self.failure_counts[model]

        # 10回連続失敗 -> 使用不可
        if count >= 10:
            print(
                f"エラー: モデル [{model}] は10回連続で失敗したため、使用不可フラグを立てます。"
            )
            self.disabled_models.add(model)
            self._switch_to_next()
            return "disabled"

        # 3回連続失敗 -> 一時的に次へ
        if count >= 3:
            print(
                f"警告: モデル [{model}] で連続エラー({count}回)。次のモデルへ切り替えます。"
            )
            self._switch_to_next()
            return "switched"

        return "continue"

    def _switch_to_next(self):
        """次のモデルへインデックスを進める"""
        self.current_idx += 1
        # 初めてフォールバックに入った場合のみ時刻を記録
        if self.fallback_start_time is None:
            self.fallback_start_time = time.time()


# --- ユーティリティ関数 ---


def load_json(filepath):
    """JSONファイルを読み込む。失敗したら空辞書を返す。"""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"警告: JSON読み込みエラー {filepath}: {e}")
        return {}


def save_json(filepath, data):
    """JSONファイルを保存する。"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def is_valid_translation(original, translated):
    """翻訳結果が妥当かチェックする（エラーメッセージの混入などを防ぐ）"""
    if not translated:
        return False
    for keyword in ERROR_KEYWORDS:
        if keyword in translated:
            return False
    return True


def clean_cache(cache_data):
    """キャッシュ内の汚染データ（エラーメッセージ）を削除する"""
    cleaned_count = 0
    keys_to_remove = []
    for key, value in cache_data.items():
        if not is_valid_translation(key, value):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del cache_data[key]
        cleaned_count += 1

    if cleaned_count > 0:
        print(
            f"情報: キャッシュから {cleaned_count} 件のエラー済みデータを削除しました。これらは再翻訳されます。"
        )
    return cache_data


def format_time(seconds):
    """秒数を m分s秒 形式に変換"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    else:
        return f"{int(seconds // 60)}分{int(seconds % 60)}秒"


# --- ファイル解析関連 ---


def detect_pack_format(mod_path):
    """Mod内のpack.mcmetaからバージョン情報を取得する"""
    try:
        with zipfile.ZipFile(mod_path, "r") as zf:
            if "pack.mcmeta" in zf.namelist():
                with zf.open("pack.mcmeta") as f:
                    data = json.load(f)
                    return data.get("pack", {}).get(
                        "pack_format", DEFAULT_FORMAT_FALLBACK
                    )
    except:
        pass
    return DEFAULT_FORMAT_FALLBACK


def extract_lang_files(mod_path, is_shader_mode=False):
    """Mod/Shaderから言語ファイル(en_us.json / .lang)を抽出する"""
    extracted = {}  # {filename: content_dict}
    try:
        with zipfile.ZipFile(mod_path, "r") as zf:
            for file in zf.namelist():
                # JSON言語ファイル (Mod)
                if (
                    not is_shader_mode
                    and file.endswith("en_us.json")
                    and "assets" in file
                ):
                    with zf.open(file) as f:
                        try:
                            content = json.load(f)
                            extracted[file] = content
                        except:
                            continue

                # .langファイル (Shader / 古いMod)
                elif file.endswith(".lang") or (
                    is_shader_mode and file.endswith("en_US.lang")
                ):
                    with zf.open(file) as f:
                        try:
                            # key=value 形式をパース
                            content = {}
                            for line in (
                                f.read().decode("utf-8", errors="ignore").splitlines()
                            ):
                                line = line.strip()
                                if "=" in line and not line.startswith("#"):
                                    k, v = line.split("=", 1)
                                    content[k.strip()] = v.strip()
                            if content:
                                extracted[file] = content
                        except:
                            continue
    except Exception as e:
        print(f"エラー: ファイル読み込み失敗 {mod_path}: {e}")
    return extracted


# --- 翻訳エンジン ---


def translate_google_batch(text_list):
    """Google翻訳 (Deep Translator) を使用"""
    try:
        # Google翻訳は文字数制限があるため、適度に分割が必要だが
        # deep_translatorは内部である程度よしなにやってくれる
        translator = GoogleTranslator(source="auto", target="ja")
        return translator.translate_batch(text_list)
    except Exception as e:
        print(f"Google翻訳エラー: {e}")
        return text_list  # 失敗時は原文を返す


def translate_with_gemini(text_dict, api_key, selector):
    """
    Gemini APIを使用した翻訳（ModelSelectorによる動的制御版）
    リスト返却時の救済ロジック追加版
    """
    if not text_dict:
        return {}

    translated_results = {}
    keys = list(text_dict.keys())
    total = len(keys)
    current_idx = 0

    start_time = time.time()

    print(f"情報: モデル [{selector.get_current_model()}] で開始します。")

    while current_idx < total:
        current_model = selector.get_current_model()
        batch_size, interval = get_model_settings(current_model)

        batch_keys = keys[current_idx : current_idx + batch_size]
        batch_dict = {k: text_dict[k] for k in batch_keys}

        # プロンプト強化: 必ずJSONオブジェクト(Dict)で返すよう念押しする
        prompt = (
            "あなたはMinecraftのMod翻訳の専門家です。以下のJSONオブジェクトの値を日本語に翻訳してください。\n"
            "Minecraft特有の用語（Redstone, Mobなど）は文脈に合わせて適切に訳してください。\n"
            "**重要: 必ず元のキー(Key)を維持したJSONオブジェクト形式で出力してください。配列(List)で返さないでください。**\n"
            "フォーマットはJSONのみ。Markdownのコードブロックは不要です。\n"
            "色コード（§rなど）やフォーマット指定子（%sなど）は維持してください。\n\n"
            f"{json.dumps(batch_dict, ensure_ascii=False)}"
        )

        batch_success = False
        retry_count = 0
        max_retries = 2

        while not batch_success:
            try:
                url = GEMINI_API_URL.format(current_model) + f"?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                }

                response = requests.post(
                    url, headers=headers, json=payload, timeout=90
                )  # タイムアウト延長

                if response.status_code == 200:
                    try:
                        result_json = response.json()
                        content_text = result_json["candidates"][0]["content"]["parts"][
                            0
                        ]["text"]
                        translated_batch = json.loads(content_text)

                        # --- ここが修正ポイント ---
                        # もしAIがリスト(配列)で返してきた場合の救済措置
                        if isinstance(translated_batch, list):
                            # 数が合っていれば、順番通りにキーとマッピングして辞書に直す
                            if len(translated_batch) == len(batch_keys):
                                temp_dict = {}
                                for i, k in enumerate(batch_keys):
                                    # リストの中身が文字列ならそのまま、オブジェクトならvaluesから取るなどの分岐も可だが
                                    # 2.0 Flash Liteは文字列のリストを返す傾向がある
                                    val = translated_batch[i]
                                    if isinstance(
                                        val, dict
                                    ):  # 万が一 {"translated": "..."} みたいなのが入っていた場合
                                        val = list(val.values())[0]
                                    temp_dict[k] = str(val)
                                translated_batch = temp_dict
                            else:
                                # 数が合わない場合は信頼できないのでエラー扱い
                                raise ValueError(
                                    f"List length mismatch: got {len(translated_batch)}, expected {len(batch_keys)}"
                                )

                        # ここで update
                        if isinstance(translated_batch, dict):
                            translated_results.update(translated_batch)
                            selector.report_success()
                            batch_success = True
                            current_idx += len(batch_keys)
                        else:
                            raise ValueError("Response is not a dict or valid list")

                    except (KeyError, json.JSONDecodeError, ValueError) as e:
                        print(f"警告: Gemini応答の解析失敗: {e}")
                        retry_count += 1
                        time.sleep(2)

                elif response.status_code == 429:
                    print(f"警告: レート制限 (429) 発生。")
                    action = selector.report_failure()
                    if action in ["switched", "disabled"]:
                        time.sleep(2)
                        break
                    else:
                        time.sleep(interval * 2)

                else:
                    print(f"APIエラー: {response.status_code} - {response.text}")
                    action = selector.report_failure()
                    if action in ["switched", "disabled"]:
                        time.sleep(2)
                        break
                    time.sleep(2)

            except Exception as e:
                print(f"通信エラー: {e}")
                retry_count += 1
                time.sleep(2)

            if (
                not batch_success
                and retry_count >= max_retries
                and response.status_code != 429
            ):
                print(f"エラー: このバッチの翻訳をスキップします。")
                current_idx += len(batch_keys)
                break

        processed = current_idx
        percent = (processed / total) * 100
        elapsed_time = time.time() - start_time

        if processed > 0:
            avg_time_per_item = elapsed_time / processed
            remaining_items = total - processed
            eta_seconds = remaining_items * avg_time_per_item
            if remaining_items > 0:
                eta_seconds += interval
            eta_str = format_time(eta_seconds)
        else:
            eta_str = "計算中..."

        print(
            f"  進捗: {processed}/{total} ({percent:.1f}%) - 残り予想: {eta_str} - 使用中: {current_model}"
        )

        if batch_success:
            time.sleep(interval)

    return translated_results


def translate_local_llm(text_dict, engine, model_name):
    """ローカルLLM (Ollama/LM Studio) を使用した翻訳"""
    BATCH_SIZE = 20
    url = OLLAMA_API_URL if engine == "ollama" else LMSTUDIO_API_URL

    translated_results = {}
    keys = list(text_dict.keys())
    total = len(keys)
    processed = 0
    start_time = time.time()

    for i in range(0, len(keys), BATCH_SIZE):
        batch_keys = keys[i : i + BATCH_SIZE]
        batch_dict = {k: text_dict[k] for k in batch_keys}

        prompt = f"Translate the values of this JSON to Japanese for Minecraft Mod. Keep keys unchanged. JSON only:\n{json.dumps(batch_dict, ensure_ascii=False)}"

        try:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
            }

            response = requests.post(url, json=payload, timeout=120)

            if response.status_code == 200:
                res_data = response.json()
                content = ""
                if engine == "ollama":
                    content = res_data.get("message", {}).get("content", "{}")
                else:
                    content = (
                        res_data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "{}")
                    )

                try:
                    batch_res = json.loads(content)
                    translated_results.update(batch_res)
                except:
                    print("警告: ローカルLLMの応答がJSONではありませんでした。")
            else:
                print(f"ローカルLLMエラー: {response.status_code}")

        except Exception as e:
            print(f"ローカルLLM通信エラー: {e}")

        processed += len(batch_keys)
        elapsed_time = time.time() - start_time
        if processed > 0:
            avg = elapsed_time / processed
            rem = total - processed
            eta = format_time(rem * avg)
            print(f"  進捗: {processed}/{total} - 残り予想: {eta}")

    return translated_results


# --- メイン処理クラス ---


class ModTranslator:
    def __init__(self, args):
        self.input_dir = args.input
        self.output_dir = args.output
        self.engine = args.engine
        self.api_key = args.key
        self.model_name = args.model
        self.lite_only = args.lite_only
        self.force = args.force

        self.is_shader_mode = "shader" in os.path.basename(self.input_dir).lower()
        if self.is_shader_mode:
            print(
                "情報: フォルダ名に'shader'が含まれているため、シェーダーパック翻訳モードで動作します。"
            )

        os.makedirs(self.output_dir, exist_ok=True)
        self.cache_file = os.path.join(self.output_dir, "trans_cache.json")
        self.log_file = os.path.join(self.output_dir, "progress_log.json")

        self.cache = load_json(self.cache_file)
        self.cache = clean_cache(self.cache)

        # セレクターの初期化
        self.selector = None

        if self.engine == "gemini":
            if self.api_key:
                if self.model_name:
                    # ユーザー指定時はそのモデル1つだけのリスト
                    models = [self.model_name]
                    print(f"使用モデル (固定): {self.model_name}")
                else:
                    # 自動探索
                    models = get_prioritized_models(self.api_key, self.lite_only)
                    print(f"優先モデルリスト: {models}")

                self.selector = ModelSelector(models)
            else:
                print("エラー: Geminiを使用するにはAPIキーが必要です。")
                exit(1)

    def run(self):
        print(f"翻訳開始: {self.input_dir} -> {self.output_dir}")

        files = [f for f in os.listdir(self.input_dir) if f.endswith((".jar", ".zip"))]
        total_files = len(files)

        print(f"対象ファイル数: {total_files}")

        for idx, filename in enumerate(files):
            file_path = os.path.join(self.input_dir, filename)
            print(f"\n[{idx+1}/{total_files}] 処理中: {filename}")

            lang_files = extract_lang_files(file_path, self.is_shader_mode)
            if not lang_files:
                print("  -> 言語ファイルが見つかりませんでした。スキップ。")
                continue

            pack_format = detect_pack_format(file_path)

            for lang_path, content in lang_files.items():
                to_translate = {}
                for k, v in content.items():
                    if k in IGNORE_KEYS or not isinstance(v, str):
                        continue
                    if not self.force and v in self.cache:
                        continue
                    to_translate[k] = v

                if not to_translate:
                    print("  -> 新規翻訳項目なし。完了。")
                    translated_data = {
                        k: self.cache.get(v, v)
                        for k, v in content.items()
                        if isinstance(v, str)
                    }
                else:
                    print(f"  -> 翻訳対象: {len(to_translate)} 項目")

                    new_translations = {}
                    if self.engine == "google":
                        keys = list(to_translate.keys())
                        values = list(to_translate.values())
                        translated_values = translate_google_batch(values)
                        for k, tv in zip(keys, translated_values):
                            new_translations[to_translate[k]] = tv

                    elif self.engine == "gemini":
                        # セレクターを渡して実行
                        new_translations_raw = translate_with_gemini(
                            to_translate, self.api_key, self.selector
                        )

                        for k, v in new_translations_raw.items():
                            original_text = content.get(k)
                            if original_text:
                                new_translations[original_text] = v

                    elif self.engine in ["ollama", "lmstudio"]:
                        new_translations_raw = translate_local_llm(
                            to_translate, self.engine, self.model_name
                        )
                        for k, v in new_translations_raw.items():
                            original_text = content.get(k)
                            if original_text:
                                new_translations[original_text] = v

                    self.cache.update(new_translations)
                    save_json(self.cache_file, self.cache)

                    translated_data = content.copy()
                    for k, v in content.items():
                        if isinstance(v, str) and v in self.cache:
                            translated_data[k] = self.cache[v]

                self.write_output(filename, lang_path, translated_data, pack_format)

    def write_output(self, original_filename, lang_internal_path, data, pack_format):
        mod_name = os.path.splitext(original_filename)[0]

        if self.is_shader_mode:
            dirname = os.path.dirname(lang_internal_path)
            filename = os.path.basename(lang_internal_path)

            if filename.lower().endswith(".json"):
                new_filename = "ja_jp.json"
            elif filename.lower().endswith(".lang"):
                new_filename = "ja_JP.lang"
            else:
                base, ext = os.path.splitext(filename)
                new_filename = f"ja_JP{ext}"

            out_path = os.path.join(self.output_dir, mod_name, dirname, new_filename)

        else:
            path_parts = lang_internal_path.replace("\\", "/").split("/")
            if "assets" in path_parts:
                idx = path_parts.index("assets")
                base_parts = path_parts[idx:-1]
                dest_dir = os.path.join(self.output_dir, *base_parts)
                out_path = os.path.join(dest_dir, "ja_jp.json")

                mcmeta_path = os.path.join(self.output_dir, "pack.mcmeta")
                if not os.path.exists(mcmeta_path):
                    meta = {
                        "pack": {
                            "pack_format": pack_format,
                            "description": "Auto Translated Resource Pack",
                        }
                    }
                    save_json(mcmeta_path, meta)
            else:
                return

        final_data = {}
        for k, v in data.items():
            if is_valid_translation(k, v):
                final_data[k] = v

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        if out_path.endswith(".json"):
            save_json(out_path, data)
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                for k, v in data.items():
                    f.write(f"{k}={v}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minecraft Mod 自動翻訳ツール")
    parser.add_argument("-i", "--input", required=True, help="入力フォルダ")
    parser.add_argument("-o", "--output", default="Output_Pack", help="出力フォルダ")
    parser.add_argument(
        "--engine", choices=["google", "gemini", "ollama", "lmstudio"], default="google"
    )
    parser.add_argument("--key", help="Gemini APIキー")
    parser.add_argument("--model", help="使用モデル名")
    parser.add_argument("--lite-only", action="store_true", help="Liteモデル限定")
    parser.add_argument("--force", action="store_true", help="強制再翻訳")

    args = parser.parse_args()

    translator = ModTranslator(args)
    translator.run()
