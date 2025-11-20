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
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models?key={}"
OLLAMA_API_URL = "http://localhost:11434/api/chat"
LMSTUDIO_API_URL = "http://localhost:1234/v1/chat/completions"

# 優先モデルリスト（ユーザー指定）
# デフォルトの優先順位（RPD > TPM > RPM の順）
# ユーザー要望により 2.0 Lite を Gemma より優先し、Pro を除外
DEFAULT_PRIORITY = [
    # 1. Gemini 2.5 Lite (RPD 1,000 - 最優先主力)
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite-preview-09-2025",

    # 2. Gemini 2.0 Lite (RPD 200 / RPM 30 - 高速サブ)
    # Gemmaより先にこちらを使って速度を稼ぐ
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash-lite-preview",
    "gemini-2.0-flash-lite-preview-02-05",

    # 3. Gemma 3n/3系 (RPD 14,400 - 鉄壁のスタミナ)
    # Lite系が尽きた後の長期戦用
    "gemma-3n-e2b-it",
    "gemma-3n-e4b-it",
    "gemma-3-27b-it",
    "gemma-3-12b-it",
    "gemma-3-8b-it",
    "gemma-3-4b-it",
    "gemma-3-1b-it",

    # # 4. Gemini 2.5 Flash (RPD 250 - 標準枠)
    # "gemini-2.5-flash-preview-09-2025",
    # "gemini-2.5-flash",

    # # 5. Gemini 2.0 Flash Exp (Proは除外済み)
    # "gemini-2.0-flash-exp",
    # "gemini-2.0-flash",
    # "gemini-2.0-flash-001",

    # 6. 旧世代・その他 (予備)
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-flash-002",
    "gemini-flash-lite-latest",
    "gemini-flash-latest"
]

# 翻訳除外キー
IGNORE_KEYS = [
    "pack.mcmeta", "pack.description", "_comment", 
    "language.name", "language.region", "language.code"
]

# エラー検出用キーワード
ERROR_KEYWORDS = [
    "Error 504", "HTTP 429", "Model overloaded", "Internal Server Error",
    "quota exceeded", "Too Many Requests", "Service Unavailable"
]

def get_model_settings(model_name):
    """
    モデル名に基づいて、最適なバッチサイズ（行数）とリクエスト間隔（秒）を返す。
    
    戦略:
    - Gemini 2.5 Flash-Lite: RPD(1000)は多いがTPM(250k)がボトルネック -> バッチ小さめ、回転数で稼ぐ。RPM15なので4s待機。
    - Gemini 2.0 Flash-Lite: TPM(1M)は多いがRPD(200)が少ない -> バッチ特大、回数を減らす。
    - Gemma 3: TPM(15k)が極端に少ない -> バッチ極小。
    - Pro: RPM(2)が極端に遅い -> 待機時間特大。
    """
    if not model_name:
        return 45, 2.0  # デフォルト

    name = model_name.lower()
    
    # デフォルト値
    batch_size = 45
    interval = 2.0

    if "gemma" in name:
        # Gemma 3 (TPM 15,000 / RPD 14,400)
        # トークンが極端に少ないため、極小バッチで刻む必要がある
        batch_size = 7 
        interval = 1.5 

    elif "gemini-2.0-flash-lite" in name:
        # Gemini 2.0 Flash-Lite (TPM 1,000,000 / RPD 200 / RPM 30)
        # リクエスト回数(RPD 200)が貴重。トークンは余っているので限界まで詰め込む。
        batch_size = 75 
        interval = 3.0 

    elif "gemini-2.0-flash" in name:
        # Gemini 2.0 Flash (TPM 1,000,000 / RPD 200 / RPM 15)
        batch_size = 60
        interval = 5.0 

    elif "gemini-2.5-flash-lite" in name:
        # Gemini 2.5 Flash-Lite (TPM 250,000 / RPD 1,000 / RPM 15)
        # RPDは潤沢だが、TPMが少し低い。バッチを小さくしてバーストを防ぐ。
        batch_size = 30
        interval = 5.0 

    elif "gemini-2.5-flash" in name:
        # Gemini 2.5 Flash (TPM 250,000 / RPD 250 / RPM 10)
        batch_size = 40
        interval = 7.0 

    elif "pro" in name:
        # Gemini 2.5 Pro (RPM 2)
        # とにかく遅い。
        batch_size = 50
        interval = 32.0 

    return batch_size, interval

def get_available_gemini_models(api_key):
    """APIキーを使用して現在利用可能なモデル一覧を取得する"""
    try:
        url = GEMINI_MODELS_URL.format(api_key)
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # "models/gemini-..." という形式で返ってくるので "gemini-..." だけ抽出
            models = [m["name"].replace("models/", "") for m in data.get("models", [])]
            return models
        else:
            print(f"警告: モデル一覧の取得に失敗しました (HTTP {response.status_code})")
            return []
    except Exception as e:
        print(f"警告: モデル一覧取得中にエラーが発生: {e}")
        return []

def select_best_model(api_key, lite_only=False):
    """優先順位リストと利用可能なモデルを照らし合わせて、最適なモデルを選択する"""
    print("情報: 利用可能なGeminiモデルを探索中...")
    available_models = get_available_gemini_models(api_key)
    
    if not available_models:
        # API通信に失敗した場合は、優先リストのトップを強制的に返す（イチかバチか）
        fallback = DEFAULT_PRIORITY[0]
        print(f"警告: モデル一覧が取得できなかったため、デフォルトの {fallback} を使用します。")
        return fallback

    # 利用可能なモデルを表示（デバッグ用）
    # print(f"DEBUG: Available models: {available_models}")

    for candidate in DEFAULT_PRIORITY:
        # Lite限定モードなら "lite" が含まれていないモデルはスキップ
        if lite_only and "lite" not in candidate.lower():
            continue
            
        # 候補が利用可能リストに存在するかチェック
        if candidate in available_models:
            return candidate
    
    # 見つからなかった場合
    if lite_only:
        print("警告: Liteモデルが見つかりませんでした。gemini-2.5-flash-lite を強制使用します。")
        return "gemini-2.5-flash-lite"
    else:
        print("警告: 優先リスト内のモデルが見つかりませんでした。gemini-2.0-flash を使用します。")
        return "gemini-2.0-flash"

# --- ユーティリティ関数 ---

def load_json(filepath):
    """JSONファイルを読み込む。失敗したら空辞書を返す。"""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {}

def save_json(filepath, data):
    """JSONファイルを保存する。"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
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
        print(f"情報: キャッシュから {cleaned_count} 件のエラー済みデータを削除しました。")
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
        with zipfile.ZipFile(mod_path, 'r') as zf:
            if "pack.mcmeta" in zf.namelist():
                with zf.open("pack.mcmeta") as f:
                    data = json.load(f)
                    return data.get("pack", {}).get("pack_format", DEFAULT_FORMAT_FALLBACK)
    except:
        pass
    return DEFAULT_FORMAT_FALLBACK

def extract_lang_files(mod_path, is_shader_mode=False):
    """Mod/Shaderから言語ファイル(en_us.json / .lang)を抽出する"""
    extracted = {} # {filename: content_dict}
    try:
        with zipfile.ZipFile(mod_path, 'r') as zf:
            for file in zf.namelist():
                # JSON言語ファイル (Mod)
                if not is_shader_mode and file.endswith("en_us.json") and "assets" in file:
                    with zf.open(file) as f:
                        try:
                            content = json.load(f)
                            extracted[file] = content
                        except:
                            continue
                
                # .langファイル (Shader / 古いMod)
                elif file.endswith(".lang") or (is_shader_mode and file.endswith("en_US.lang")):
                    with zf.open(file) as f:
                        try:
                            content = {}
                            for line in f.read().decode('utf-8', errors='ignore').splitlines():
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
        translator = GoogleTranslator(source='auto', target='ja')
        return translator.translate_batch(text_list)
    except Exception as e:
        print(f"Google翻訳エラー: {e}")
        return text_list

def translate_with_gemini(text_dict, api_key, model_name, lite_only=False):
    """Gemini APIを使用した翻訳（動的バッチサイズ対応）"""
    if not text_dict:
        return {}
    
    # モデル設定の取得
    batch_size, interval = get_model_settings(model_name)
    print(f"情報: モデル [{model_name}] 設定 -> バッチサイズ: {batch_size}行, 待機時間: {interval}秒")

    translated_results = {}
    keys = list(text_dict.keys())
    
    total = len(keys)
    processed = 0
    start_time = time.time() # 測定開始

    for i in range(0, total, batch_size):
        batch_keys = keys[i : i + batch_size]
        batch_dict = {k: text_dict[k] for k in batch_keys}
        
        prompt = (
            "あなたはMinecraftのMod翻訳の専門家です。以下のJSONオブジェクトの値を日本語に翻訳してください。\n"
            "Minecraft特有の用語（Redstone, Mobなど）は文脈に合わせて適切に訳してください。\n"
            "フォーマットはJSONのまま出力してください。キーは変更しないでください。\n"
            "色コード（§rなど）やフォーマット指定子（%sなど）は維持してください。\n\n"
            f"{json.dumps(batch_dict, ensure_ascii=False)}"
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                url = GEMINI_API_URL.format(model_name) + f"?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"}
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    result_json = response.json()
                    try:
                        content_text = result_json["candidates"][0]["content"]["parts"][0]["text"]
                        translated_batch = json.loads(content_text)
                        translated_results.update(translated_batch)
                        break
                    except (KeyError, json.JSONDecodeError) as e:
                        print(f"警告: Gemini応答の解析失敗 (試行 {attempt+1}): {e}")
                
                elif response.status_code == 429:
                    print(f"警告: レート制限 (429) 発生。{interval * 2}秒待機して再試行します...")
                    time.sleep(interval * 2)
                else:
                    print(f"APIエラー: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"通信エラー (試行 {attempt+1}): {e}")
                time.sleep(2)
        
        processed += len(batch_keys)
        
        # 進捗とETAの計算
        elapsed_time = time.time() - start_time
        percent = (processed / total) * 100
        
        if processed > 0:
            # 1アイテムあたりの平均時間
            avg_time_per_item = elapsed_time / processed
            # 残りアイテム数
            remaining_items = total - processed
            # 現在のインターバルも加味したETA計算
            eta_seconds = remaining_items * avg_time_per_item
            # 最後のバッチ後の待機時間は不要だが、概算としては含めても良い
            
            # より正確にするために、次の待機時間分を足す（ループ継続する場合）
            if remaining_items > 0:
                eta_seconds += interval
            
            eta_str = format_time(eta_seconds)
        else:
            eta_str = "計算中..."

        # プログレスバー表示
        # \r を使って同じ行を更新したいところだが、ログが見えなくなるので改行する
        print(f"  進捗: {processed}/{total} ({percent:.1f}%) - 残り予想: {eta_str}")
        
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
                "format": "json"
            }
            
            response = requests.post(url, json=payload, timeout=120)
            
            if response.status_code == 200:
                res_data = response.json()
                content = ""
                if engine == "ollama":
                    content = res_data.get("message", {}).get("content", "{}")
                else:
                    content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                try:
                    batch_res = json.loads(content)
                    translated_results.update(batch_res)
                except:
                    print("警告: ローカルLLMの応答がJSONではありませんでした。スキップします。")
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
        
        # シェーダーモード判定
        self.is_shader_mode = "shader" in os.path.basename(self.input_dir).lower()
        if self.is_shader_mode:
            print("情報: フォルダ名に'shader'が含まれているため、シェーダーパック翻訳モードで動作します。")
        
        # キャッシュとログのパス設定
        os.makedirs(self.output_dir, exist_ok=True)
        self.cache_file = os.path.join(self.output_dir, "trans_cache.json")
        self.log_file = os.path.join(self.output_dir, "progress_log.json")
        
        self.cache = load_json(self.cache_file)
        self.cache = clean_cache(self.cache) # 起動時に汚染データをクリーニング

        # モデルの決定（Geminiの場合）
        if self.engine == "gemini":
            if not self.model_name:
                # APIを使って優先リストから最適なモデルを選択
                if self.api_key:
                    self.model_name = select_best_model(self.api_key, self.lite_only)
                else:
                    print("エラー: Geminiを使用するにはAPIキーが必要です。")
                    exit(1)
            print(f"使用モデル: {self.model_name}")

    def run(self):
        print(f"翻訳開始: {self.input_dir} -> {self.output_dir}")
        
        files = [f for f in os.listdir(self.input_dir) if f.endswith(('.jar', '.zip'))]
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
                    translated_data = {k: self.cache.get(v, v) for k, v in content.items() if isinstance(v, str)}
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
                        new_translations_raw = translate_with_gemini(to_translate, self.api_key, self.model_name, self.lite_only)
                        for k, v in new_translations_raw.items():
                            original_text = content.get(k)
                            if original_text:
                                new_translations[original_text] = v

                    elif self.engine in ["ollama", "lmstudio"]:
                        new_translations_raw = translate_local_llm(to_translate, self.engine, self.model_name)
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
        """リソースパックとしてファイルを書き出す"""
        mod_name = os.path.splitext(original_filename)[0]
        
        if self.is_shader_mode:
            out_path = os.path.join(self.output_dir, mod_name, lang_internal_path)
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
                            "description": "Auto Translated Resource Pack"
                        }
                    }
                    save_json(mcmeta_path, meta)
            else:
                return

        final_data = {}
        for k, v in data.items():
            if is_valid_translation(k, v):
                final_data[k] = v
            else:
                pass

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        
        if out_path.endswith(".json"):
            save_json(out_path, data)
        else:
            with open(out_path, 'w', encoding='utf-8') as f:
                for k, v in data.items():
                    f.write(f"{k}={v}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minecraft Mod 自動翻訳ツール")
    parser.add_argument("-i", "--input", required=True, help="入力フォルダ（Mod/Shaderが入っている場所）")
    parser.add_argument("-o", "--output", default="Output_Pack", help="出力フォルダ（リソースパック保存先）")
    parser.add_argument("--engine", choices=["google", "gemini", "ollama", "lmstudio"], default="google", help="翻訳エンジン")
    parser.add_argument("--key", help="Gemini APIキー")
    parser.add_argument("--model", help="使用するモデル名 (Gemini/Ollama用)")
    parser.add_argument("--lite-only", action="store_true", help="GeminiのLiteモデルのみを使用する")
    parser.add_argument("--force", action="store_true", help="キャッシュを無視して強制的に再翻訳")
    
    args = parser.parse_args()
    
    translator = ModTranslator(args)
    translator.run()