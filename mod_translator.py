import os, sys, json, zipfile, argparse, time, collections, re
import requests
from tqdm import tqdm
from deep_translator import GoogleTranslator

# ==========================================
# 設定・定数
# ==========================================
CACHE_FILENAME = "trans_cache.json"
PROGRESS_FILENAME = "progress_log.json"
DEFAULT_FORMAT_FALLBACK = 34
BATCH_SIZE = 10

# API制限対策: リクエスト間の待機時間
REQUEST_INTERVAL = 5.0 

# エラー判定用ワード
ERROR_KEYWORDS = [
    "Error 504", "Server Error", "That’s an error", 
    "429 Too Many Requests", "MYMEMORY WARNING",
    "Error 502", "Bad Gateway"
]

# ==========================================
# 関数定義
# ==========================================

def is_valid_translation(text):
    if not text: return True
    text_str = str(text)
    for kw in ERROR_KEYWORDS:
        if kw in text_str: return False
    return True

def load_json(filepath, default_type=dict):
    default_val = default_type()
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and "trans_cache.json" in filepath:
                clean_data = {}
                dirty_count = 0
                for k, v in data.items():
                    if is_valid_translation(v):
                        clean_data[k] = v
                    else:
                        dirty_count += 1
                if dirty_count > 0:
                    pass 
                return clean_data
            return data
        except:
            return default_val
    return default_val

def save_json(filepath, data):
    parent_dir = os.path.dirname(filepath)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_translator_google():
    return GoogleTranslator(source='auto', target='ja')

def translate_google_single(text, translator, cache):
    if not text or str(text).strip() == "": return text
    if text in cache: return cache[text]
    if str(text).replace(".", "").isdigit(): return text
    try:
        res = translator.translate(text)
        if not is_valid_translation(res):
            time.sleep(1.0)
            return text
        cache[text] = res
        time.sleep(0.5)
        return res
    except:
        return text

# --- JSON抽出用ヘルパー ---
def extract_json_from_response(text):
    """
    モデルの出力からJSONブロックだけを正規表現で抜き出す
    <think>タグやMarkdown記法が含まれていても対応可能にする
    """
    try:
        # 最も外側の {} を探す (DOTALLで改行も含める)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        
        # 正規表現で見つからない場合、従来のクリーニングを試す
        cleaned = text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except:
        return None

# --- Gemini API ---
def get_available_models(api_key):
    url = f"[https://generativelanguage.googleapis.com/v1beta/models?key=](https://generativelanguage.googleapis.com/v1beta/models?key=){api_key}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: return []
        data = res.json()
        models = []
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    models.append(m['name'].replace('models/', ''))
        return models
    except: return []

def call_gemini_rest(model_name, api_key, prompt):
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model_name}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        try:
            return response.json(), response.status_code
        except:
            return None, response.status_code
    except Exception as e:
        return None, 0

def translate_gemini_batch_rest(key_value_dict, models_list, api_key, cache):
    to_translate = {k: v for k, v in key_value_dict.items() if v not in cache and str(v).strip() and not str(v).replace(".", "").isdigit()}
    if not to_translate: return True
    items = list(to_translate.items())
    
    total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE
    current_model_idx = 0
    
    with tqdm(total=total_batches, desc="    Translating", leave=False, unit="batch") as batch_pbar:
        for i in range(0, len(items), BATCH_SIZE):
            batch = dict(items[i : i + BATCH_SIZE])
            input_text = json.dumps(batch, ensure_ascii=False)
            prompt = f"""Translate Minecraft Mod JSON to Japanese. Output JSON only. No markdown. JSON: {input_text}"""
            
            batch_success = False
            
            while True:
                if current_model_idx >= len(models_list):
                    batch_pbar.write("    [Wait] All models busy. Cooling down for 60s...")
                    time.sleep(60)
                    current_model_idx = 0 
                    batch_pbar.write("    [Resume] Retrying...")
                    continue 

                active_model = models_list[current_model_idx]
                
                result_json, status_code = call_gemini_rest(active_model, api_key, prompt)
                
                if status_code == 200 and result_json and 'candidates' in result_json:
                    raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    # ここで抽出関数を使う
                    translated_batch = extract_json_from_response(raw_text)
                    
                    if translated_batch:
                        for k, original_v in batch.items():
                            if k in translated_batch and is_valid_translation(translated_batch[k]):
                                cache[original_v] = translated_batch[k]
                        time.sleep(REQUEST_INTERVAL)
                        batch_success = True
                        break
                    else:
                        batch_pbar.write(f"    [Warn] {active_model} invalid JSON structure. Switching...")
                        current_model_idx += 1
                        time.sleep(1)
                
                elif status_code == 429:
                    batch_pbar.write(f"    [Limit] {active_model} (429). Switching...")
                    current_model_idx += 1
                    time.sleep(1)

                else:
                    batch_pbar.write(f"    [Error {status_code}] {active_model} failed. Switching...")
                    current_model_idx += 1
                    time.sleep(1)
            
            if not batch_success:
                return False
            
            batch_pbar.update(1)

    return True

# --- LM Studio ---
def call_lmstudio_rest(prompt):
    url = "http://localhost:1234/v1/chat/completions"
    headers = {'Content-Type': 'application/json'}
    messages = [
        {"role": "system", "content": "You are a translator. Output only valid JSON. No markdown, no explanations."},
        {"role": "user", "content": prompt}
    ]
    data = {
        "model": "local-model",
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": -1,
        "stream": False
    }
    try:
        # LM Studioは遅い場合があるので少し長めに待つが、タイムアウトしたら諦める
        response = requests.post(url, headers=headers, json=data, timeout=300)
        if response.status_code != 200: return None
        return response.json()
    except: return None

def translate_lmstudio_batch(key_value_dict, cache):
    to_translate = {k: v for k, v in key_value_dict.items() if v not in cache and str(v).strip() and not str(v).replace(".", "").isdigit()}
    if not to_translate: return True
    items = list(to_translate.items())
    
    total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE
    with tqdm(total=total_batches, desc="    Translating", leave=False, unit="batch") as batch_pbar:
        for i in range(0, len(items), BATCH_SIZE):
            batch = dict(items[i : i + BATCH_SIZE])
            input_text = json.dumps(batch, ensure_ascii=False)
            prompt = f"""Translate the values in the following JSON to Japanese. Keys must remain unchanged. Output strictly valid JSON. Input: {input_text}"""
            
            result = call_lmstudio_rest(prompt)
            if result and 'choices' in result:
                raw_text = result['choices'][0]['message']['content']
                
                # ここで抽出関数を使う（<think>タグ対策）
                translated_batch = extract_json_from_response(raw_text)
                
                if translated_batch:
                    for k, original_v in batch.items():
                        if k in translated_batch and is_valid_translation(translated_batch[k]):
                            cache[original_v] = translated_batch[k]
                else:
                    # 失敗した内容を少し表示してデバッグしやすくする
                    sample = raw_text[:50].replace('\n', ' ')
                    batch_pbar.write(f" [Warn] LM Studio JSON parse failed. Start with: {sample}...")
            else:
                batch_pbar.write(" [Warn] No response from LM Studio.")
            
            batch_pbar.update(1)
    return True

# --- 共通処理 ---
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

def process_jar(jar_path, output_dir, cache, engine, api_key=None, active_models_list=None, force=False):
    try:
        with zipfile.ZipFile(jar_path, 'r') as z:
            all_files = z.namelist()
            en_files = [f for f in all_files if f.lower().endswith("en_us.json")]
            if not en_files: return True
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
                ja_file_path = find_ja_path(en_file_path)
                final_data = {}
                if ja_file_path in all_files:
                    try:
                        with z.open(ja_file_path) as ja_src:
                            final_data = json.load(ja_src)
                    except: pass
                keys_to_translate = {}
                for k, v in en_data.items():
                    should = False
                    if force: should = True
                    elif k not in final_data: should = True
                    elif final_data[k] == v: should = True 
                    if should: keys_to_translate[k] = v
                    else:
                        if k not in final_data: final_data[k] = v
                if not keys_to_translate: continue
                target_dir = os.path.join(output_dir, "assets", mod_id, "lang")
                os.makedirs(target_dir, exist_ok=True)
                
                if engine == "gemini" and active_models_list:
                    translate_gemini_batch_rest(keys_to_translate, active_models_list, api_key, cache)
                elif engine == "lmstudio":
                    translate_lmstudio_batch(keys_to_translate, cache)
                
                for k, v in keys_to_translate.items():
                    if v in cache: final_data[k] = cache[v]
                    else: final_data[k] = translate_google_single(v, translator_google, cache)
                with open(os.path.join(target_dir, "ja_jp.json"), 'w', encoding='utf-8') as out:
                    json.dump(final_data, out, ensure_ascii=False, indent=4)
        return True
    except: return False

def select_gemini_models(api_key, manual_mode=False):
    print("Fetching available models from Google API...")
    models = get_available_models(api_key)
    if not models: return None
    
    if manual_mode:
        for i, m in enumerate(models): print(f"  [{i+1}] {m}")
        try:
            idx = int(input(f"Select (1-{len(models)}) > ")) - 1
            if 0 <= idx < len(models): return [models[idx]]
        except: pass
    
    selected_models = []
    lite_candidates = [m for m in models if "lite" in m.lower()]
    
    if lite_candidates:
        priority_lite = ["gemini-2.0-flash-lite", "gemini-2.5-flash-lite"]
        for p in priority_lite:
            if p in models:
                selected_models.append(p)
        for m in lite_candidates:
            if m not in selected_models:
                selected_models.append(m)
        print(f"\n[INFO] Lite Mode Active: Restricting fallbacks to {len(selected_models)} Lite models.")
    else:
        priority_order = ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-flash-002", "gemini-1.5-flash-8b"]
        for p in priority_order:
            if p in models: selected_models.append(p)
        for m in models:
            if m not in selected_models and "flash" in m: selected_models.append(m)

    if not selected_models and models: selected_models = [models[0]]
        
    print(f"[INFO] Model Priority: {' -> '.join(selected_models[:3])} ...\n")
    return selected_models

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", required=True)
    parser.add_argument("-o", "--output", default="Output_Pack")
    parser.add_argument("-f", "--format", type=int, default=-1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--engine", choices=["google", "gemini", "lmstudio", "ollama"], default="google")
    parser.add_argument("--key", help="Gemini API Key", default="")
    parser.add_argument("--model", help="Ollama model", default="gemma2:9b")
    parser.add_argument("--manual-model", action="store_true")
    try: args = parser.parse_args()
    except: sys.exit(1)
    
    active_models_list = None
    if args.engine == "gemini":
        if not args.key: sys.exit(1)
        active_models_list = select_gemini_models(args.key, args.manual_model)
    elif args.engine == "lmstudio":
        print("[INFO] Using LM Studio. Ensure Server is running at port 1234.")
    elif args.engine == "ollama":
        active_models_list = [args.model]
        
    if not os.path.exists(args.input): sys.exit(1)
    all_files = os.listdir(args.input)
    all_jars = [f for f in all_files if f.lower().endswith((".jar", ".zip"))]
    full_jar_paths = [os.path.join(args.input, f) for f in all_jars]
    fmt = args.format
    if fmt == -1: fmt = detect_pack_format(full_jar_paths) if all_jars else DEFAULT_FORMAT_FALLBACK
    if not os.path.exists(args.output): os.makedirs(args.output)
    mcmeta_path = os.path.join(args.output, "pack.mcmeta")
    if not os.path.exists(mcmeta_path) or args.force:
        with open(mcmeta_path, 'w', encoding='utf-8') as f:
            json.dump({"pack": {"pack_format": fmt, "description": f"Translated by {args.engine}"}}, f, indent=4)
    cache_file_path = os.path.join(args.output, CACHE_FILENAME)
    progress_file_path = os.path.join(args.output, PROGRESS_FILENAME)
    cache = load_json(cache_file_path, dict)
    if args.reset and os.path.exists(progress_file_path): os.remove(progress_file_path)
    processed = load_json(progress_file_path, list)
    target_jars = [p for p in full_jar_paths if os.path.basename(p) not in processed]
    
    abs_output_path = os.path.abspath(args.output)
    print(f"\n[Project Info]")
    print(f"  Output Dir: {abs_output_path}")
    print(f"  Cache File: {os.path.join(abs_output_path, CACHE_FILENAME)}")
    print(f"  Remaining : {len(target_jars)} jars")
    
    with tqdm(total=len(target_jars), unit="mod", dynamic_ncols=True) as pbar:
        for jar_path in target_jars:
            jar_name = os.path.basename(jar_path)
            pbar.set_description(f"{jar_name[:20]}...")
            process_jar(jar_path, args.output, cache, args.engine, args.key, active_models_list, args.force)
            processed.append(jar_name)
            save_json(progress_file_path, processed)
            save_json(cache_file_path, cache)
            pbar.update(1)
    print("Done!")

if __name__ == "__main__":
    main()