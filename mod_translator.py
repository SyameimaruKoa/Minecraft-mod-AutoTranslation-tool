import os, sys, json, zipfile, argparse, time, collections
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from deep_translator import GoogleTranslator

# ==========================================
# 設定・定数
# ==========================================
CACHE_FILE = "trans_cache.json"
PROGRESS_FILE = "progress_log.json"
DEFAULT_FORMAT_FALLBACK = 34  # 検知できなかった場合のデフォルト (1.21.x)

translator = GoogleTranslator(source='auto', target='ja')

# ==========================================
# 関数定義
# ==========================================

def load_json(filepath):
    """JSON読み込み（エラーハンドリング付き）"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {} if "cache" in filepath else []
    return {} if "cache" in filepath else []

def save_json(filepath, data):
    """JSON保存"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def translate_text(text, cache):
    """翻訳処理（キャッシュ・スリープ付き）"""
    if not text or not isinstance(text, str) or len(text.strip()) < 1:
        return text
    if text in cache:
        return cache[text]
    
    # 翻訳不要な文字列（数字や記号のみ）はスキップ
    if text.replace(".", "").replace(",", "").replace("/", "").replace(" ", "").isdigit():
        return text

    try:
        res = translator.translate(text)
        cache[text] = res
        time.sleep(0.2) # API制限回避
        return res
    except Exception:
        return text

def find_ja_path(en_path):
    """英語ファイルパスから日本語ファイルパスを推測"""
    if "en_us.json" in en_path: return en_path.replace("en_us.json", "ja_jp.json")
    elif "en_US.json" in en_path: return en_path.replace("en_US.json", "ja_jp.json")
    return None

def detect_pack_format(jar_paths):
    """
    複数のJarファイルをサンプリングして、最適なpack_formatを推定する
    """
    formats = []
    print("Detecting pack format from mods...")
    
    # 全てチェックすると遅いので、最大20個または全体の3割をチェック
    sample_size = min(20, len(jar_paths))
    if sample_size < 1: return DEFAULT_FORMAT_FALLBACK

    # サンプリング対象
    import random
    # 毎回同じ結果になるようソートしてから選ぶ（ランダム性を排除したい場合は先頭からでも良いが、偏りを防ぐためシャッフルもあり）
    # ここではシンプルに先頭から順にチェックする（主要なModはだいたい準拠しているため）
    target_jars = jar_paths[:sample_size]

    for jar_path in target_jars:
        try:
            with zipfile.ZipFile(jar_path, 'r') as z:
                if "pack.mcmeta" in z.namelist():
                    with z.open("pack.mcmeta") as f:
                        meta = json.load(f)
                        fmt = meta.get("pack", {}).get("pack_format")
                        if fmt is not None:
                            formats.append(fmt)
        except:
            continue
    
    if not formats:
        print(f"  -> Could not detect format. Using default: {DEFAULT_FORMAT_FALLBACK}")
        return DEFAULT_FORMAT_FALLBACK
    
    # 最頻値（最も多くのModが使っているバージョン）を採用
    most_common = collections.Counter(formats).most_common(1)[0][0]
    print(f"  -> Detected format: {most_common} (Found in {formats.count(most_common)}/{len(formats)} checked mods)")
    return most_common

def process_jar(jar_path, output_dir, cache, pbar, force_mode=False):
    """
    Jarファイルを処理する
    """
    try:
        with zipfile.ZipFile(jar_path, 'r') as z:
            all_files = z.namelist()
            en_files = [f for f in all_files if f.lower().endswith("en_us.json")]
            
            if not en_files: return True

            for en_file_path in en_files:
                # Mod IDなどのパス解析
                parts = en_file_path.split('/')
                mod_id = "unknown"
                if 'assets' in parts:
                    try: mod_id = parts[parts.index('assets') + 1]
                    except: pass

                # 英語読み込み
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
                
                # 翻訳対象の抽出
                keys_to_translate = {}
                for k, v in en_data.items():
                    should_translate = False
                    
                    if force_mode:
                        should_translate = True
                    elif k not in final_data:
                        should_translate = True
                    elif final_data[k] == v:
                        should_translate = True

                    if should_translate:
                        keys_to_translate[k] = v

                # 保存処理
                if keys_to_translate:
                    target_dir = os.path.join(output_dir, "assets", mod_id, "lang")
                    os.makedirs(target_dir, exist_ok=True)

                    pbar.set_description(f"[{mod_id}] Translating...")
                    for k, v in keys_to_translate.items():
                        final_data[k] = translate_text(v, cache)
                        pbar.update(1)

                    with open(os.path.join(target_dir, "ja_jp.json"), 'w', encoding='utf-8') as out:
                        json.dump(final_data, out, ensure_ascii=False, indent=4)

        return True
    except Exception as e:
        return False

def show_help():
    print("""
Usage: python mod_translator.py [OPTIONS]

Description:
  MinecraftのMod(.jar)から言語ファイルを抽出し、翻訳リソースパックを作成します。
  Mod内の pack.mcmeta を解析し、最適な pack_format を自動設定します。

Options:
  -i, --input DIR    Modが入っているフォルダのパス (必須)
  -o, --output DIR   生成するリソースパックの出力先 (デフォルト: Output_Pack)
  -f, --format INT   pack.mcmetaのバージョンを手動指定 (指定しない場合は自動検知)
  --force            既存の日本語訳を無視して全て強制翻訳するモード
  --reset            進捗ログをリセットして最初からやり直す
  -h, --help         このヘルプを表示
    """)

def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        show_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-i", "--input", required=True)
    parser.add_argument("-o", "--output", default="Output_Pack")
    # デフォルトを -1 に設定し、指定がなければ自動検知に回す
    parser.add_argument("-f", "--format", type=int, default=-1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reset", action="store_true")
    
    try:
        args = parser.parse_args()
    except:
        show_help()
        sys.exit(1)

    # ファイル探索（先に行う必要がある）
    if not os.path.exists(args.input):
        print(f"Error: Mod folder '{args.input}' not found.")
        sys.exit(1)

    all_jars = [f for f in os.listdir(args.input) if f.endswith(".jar")]
    full_jar_paths = [os.path.join(args.input, f) for f in all_jars]

    # pack_format の決定
    final_format = args.format
    if final_format == -1:
        if not all_jars:
            final_format = DEFAULT_FORMAT_FALLBACK
        else:
            final_format = detect_pack_format(full_jar_paths)
    
    print(f"Using pack_format: {final_format}")

    # 出力先作成
    if not os.path.exists(args.output): os.makedirs(args.output)
    
    # pack.mcmeta生成（決定したフォーマットを使用）
    with open(os.path.join(args.output, "pack.mcmeta"), 'w', encoding='utf-8') as f:
        json.dump({"pack": {"pack_format": final_format, "description": "Auto Translated Pack"}}, f, indent=4)

    cache = load_json(CACHE_FILE)
    
    # 進捗リセット確認
    if args.reset and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
    
    processed = load_json(PROGRESS_FILE)
    target_jars = [p for p in full_jar_paths if os.path.basename(p) not in processed]

    print(f"Target Mods: {len(target_jars)} / Total: {len(all_jars)}")
    
    # 翻訳処理実行
    with tqdm(total=0, unit="keys", dynamic_ncols=True) as pbar:
        for jar_path in target_jars:
            jar_name = os.path.basename(jar_path)
            pbar.set_description(f"Scanning {jar_name}")
            
            if process_jar(jar_path, args.output, cache, pbar, args.force):
                processed.append(jar_name)
                save_json(PROGRESS_FILE, processed)
                if len(cache) % 50 == 0: save_json(CACHE_FILE, cache)

    save_json(CACHE_FILE, cache)
    print(f"\nCompleted! Resource Pack: {os.path.abspath(args.output)}")

if __name__ == "__main__":
    main()