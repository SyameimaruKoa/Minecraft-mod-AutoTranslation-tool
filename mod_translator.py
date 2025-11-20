import os, sys, json, zipfile, argparse, time, collections
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from deep_translator import GoogleTranslator
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 設定・定数
# ==========================================
CACHE_FILE = "trans_cache.json"
PROGRESS_FILE = "progress_log.json"
DEFAULT_FORMAT_FALLBACK = 34  # 1.21.x
BATCH_SIZE = 40  # Geminiに一度に投げる行数

# ==========================================
# 関数定義
# ==========================================

def load_json(filepath):
    """JSON読み込み"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(filepath, data):
    """JSON保存"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_translator_google():
    return GoogleTranslator(source='auto', target='ja')

def translate_google_single(text, translator, cache):
    """Google翻訳(従来版)"""
    if not text or str(text).strip() == "": return text
    if text in cache: return cache[text]
    # 数字のみなどはスキップ
    if str(text).replace(".", "").isdigit(): return text

    try:
        res = translator.translate(text)
        cache[text] = res
        time.sleep(0.2) 
        return res
    except:
        return text

def translate_gemini_batch(key_value_dict, model, cache):
    """Geminiによるバッチ翻訳"""
    # キャッシュにあるものは除外
    to_translate = {}
    for k, v in key_value_dict.items():
        if v in cache: continue
        if not v or str(v).strip() == "": continue
        if str(v).replace(".", "").isdigit(): continue
        to_translate[k] = v

    if not to_translate:
        return

    # バッチ分割して送信
    items = list(to_translate.items())
    
    # プロンプト構築
    # JSONであることを強調し、Minecraft特有の翻訳を指示
    
    for i in range(0, len(items), BATCH_SIZE):
        batch = dict(items[i : i + BATCH_SIZE])
        
        # 入力テキスト作成
        input_text = json.dumps(batch, ensure_ascii=False)
        
        try:
            # Geminiへの指示
            prompt = f"""
            You are a professional translator for Minecraft Mods.
            Translate the values in the following JSON from English to Japanese.
            
            Rules:
            1. Output MUST be valid JSON.
            2. Maintain Minecraft terminology (e.g., "Chest" -> "チェスト", "Sneak" -> "スニーク").
            3. Do NOT translate formatting codes like %s, %d, {{0}}, <br>.
            4. Do not output markdown code blocks, just the raw JSON string.
            
            JSON to translate:
            {input_text}
            """

            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            translated_batch = json.loads(response.text)
            
            # キャッシュと結果に反映
            # キーが一致するか確認しつつ保存
            for k, original_v in batch.items():
                if k in translated_batch:
                    cache[original_v] = translated_batch[k]
                else:
                    # 失敗時は原文のまま（次回Google等で埋める余地を残す）
                    pass
            
            time.sleep(1.5) # レート制限考慮 (Flashは早いが念のため)

        except Exception as e:
            # エラー時はコンソールに出すが処理は止めない
            # print(f"  [Gemini Error] Batch failed: {e}")
            time.sleep(2)

def find_ja_path(en_path):
    if "en_us.json" in en_path: return en_path.replace("en_us.json", "ja_jp.json")
    elif "en_US.json" in en_path: return en_path.replace("en_US.json", "ja_jp.json")
    return None

def detect_pack_format(jar_paths):
    formats = []
    print("Detecting pack format...")
    target_jars = jar_paths[:min(20, len(jar_paths))]
    
    for jar_path in target_jars:
        try:
            with zipfile.ZipFile(jar_path, 'r') as z:
                if "pack.mcmeta" in z.namelist():
                    with z.open("pack.mcmeta") as f:
                        meta = json.load(f)
                        fmt = meta.get("pack", {}).get("pack_format")
                        if fmt: formats.append(fmt)
        except: continue
    
    if not formats: return DEFAULT_FORMAT_FALLBACK
    return collections.Counter(formats).most_common(1)[0][0]

def process_jar(jar_path, output_dir, cache, pbar, engine, model=None, force=False):
    try:
        with zipfile.ZipFile(jar_path, 'r') as z:
            all_files = z.namelist()
            en_files = [f for f in all_files if f.lower().endswith("en_us.json")]
            if not en_files: return True

            translator_google = None
            if engine == "google":
                translator_google = get_translator_google()

            for en_file_path in en_files:
                parts = en_file_path.split('/')
                mod_id = "unknown"
                if 'assets' in parts:
                    try: mod_id = parts[parts.index('assets') + 1]
                    except: pass

                with z.open(en_file_path) as src:
                    try: en_data = json.load(src)
                    except: continue

                # 既存日本語チェック
                ja_file_path = find_ja_path(en_file_path)
                final_data = {}
                if ja_file_path in all_files:
                    try:
                        with z.open(ja_file_path) as ja_src:
                            final_data = json.load(ja_src)
                    except: pass
                
                # 翻訳対象抽出
                keys_to_translate = {}
                for k, v in en_data.items():
                    should = False
                    if force: should = True
                    elif k not in final_data: should = True
                    elif final_data[k] == v: should = True # 原文と同じなら未翻訳とみなす

                    if should: keys_to_translate[k] = v
                    else:
                        if k not in final_data: final_data[k] = v

                if not keys_to_translate:
                    continue

                # 翻訳実行
                target_dir = os.path.join(output_dir, "assets", mod_id, "lang")
                os.makedirs(target_dir, exist_ok=True)

                pbar.set_description(f"[{mod_id}] Translating ({engine})...")

                if engine == "gemini" and model:
                    # バッチで一括翻訳してキャッシュに入れる
                    translate_gemini_batch(keys_to_translate, model, cache)
                    
                    # 結果を適用
                    for k, v in keys_to_translate.items():
                        if v in cache:
                            final_data[k] = cache[v]
                        else:
                            # Gemini失敗時は原文維持
                            final_data[k] = v
                        pbar.update(1)
                else:
                    # Google翻訳 (逐次)
                    for k, v in keys_to_translate.items():
                        final_data[k] = translate_google_single(v, translator_google, cache)
                        pbar.update(1)

                with open(os.path.join(target_dir, "ja_jp.json"), 'w', encoding='utf-8') as out:
                    json.dump(final_data, out, ensure_ascii=False, indent=4)

        return True
    except Exception as e:
        # print(f"Error processing {jar_path}: {e}")
        return False

def show_help():
    print("""
Usage: python mod_translator.py [OPTIONS]

Description:
  Minecraft Mod Auto Translator (Gemini/Google)
  Modの言語ファイル(en_us.json)を抽出し、日本語化リソースパックを生成します。

Options:
  -i, --input DIR     Mod folder path (Required)
  -o, --output DIR    Output pack name (Default: Output_Pack)
  -f, --format INT    pack.mcmeta format version (-1 = Auto Detect)
  --engine STR        Translation engine: 'google' or 'gemini' (Default: google)
  --key STR           Gemini API Key (Required if engine is gemini)
  --force             Force translate all keys
  --reset             Reset progress log
  -h, --help          Show this help
    """)

def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        show_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-i", "--input", required=True)
    parser.add_argument("-o", "--output", default="Output_Pack")
    parser.add_argument("-f", "--format", type=int, default=-1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--engine", choices=["google", "gemini"], default="google")
    parser.add_argument("--key", help="Gemini API Key", default="")
    
    try:
        args = parser.parse_args()
    except:
        show_help()
        sys.exit(1)

    if args.engine == "gemini" and not args.key:
        print("Error: Gemini engine requires --key")
        sys.exit(1)

    # Gemini初期化
    gemini_model = None
    if args.engine == "gemini":
        try:
            genai.configure(api_key=args.key)
            gemini_model = genai.GenerativeModel(
                "gemini-1.5-flash",
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            print("Gemini 1.5 Flash initialized.")
        except Exception as e:
            print(f"Failed to initialize Gemini: {e}")
            sys.exit(1)

    if not os.path.exists(args.input):
        print("Input dir not found")
        sys.exit(1)

    all_jars = [f for f in os.listdir(args.input) if f.endswith(".jar")]
    full_jar_paths = [os.path.join(args.input, f) for f in all_jars]

    # Pack Format
    fmt = args.format
    if fmt == -1:
        fmt = detect_pack_format(full_jar_paths) if all_jars else DEFAULT_FORMAT_FALLBACK
    print(f"Pack Format: {fmt}")

    # 出力準備
    if not os.path.exists(args.output): os.makedirs(args.output)
    with open(os.path.join(args.output, "pack.mcmeta"), 'w', encoding='utf-8') as f:
        json.dump({"pack": {"pack_format": fmt, "description": f"Translated by {args.engine}"}}, f, indent=4)

    cache = load_json(CACHE_FILE)
    if args.reset and os.path.exists(PROGRESS_FILE): os.remove(PROGRESS_FILE)
    processed = load_json(PROGRESS_FILE)
    
    target_jars = [p for p in full_jar_paths if os.path.basename(p) not in processed]
    print(f"Target: {len(target_jars)} mods")

    with tqdm(total=0, unit="keys", dynamic_ncols=True) as pbar:
        for jar_path in target_jars:
            jar_name = os.path.basename(jar_path)
            
            if process_jar(jar_path, args.output, cache, pbar, args.engine, gemini_model, args.force):
                processed.append(jar_name)
                save_json(PROGRESS_FILE, processed)
                # 少し頻繁に保存する
                save_json(CACHE_FILE, cache)

    print("Done!")

if __name__ == "__main__":
    main()