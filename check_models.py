import os
import google.generativeai as genai
from dotenv import load_dotenv
import sys

# コード引用元
# https://zenn.dev/croco_82/articles/30a4112805c5dd

# .envファイルから環境変数を読み込む
load_dotenv()

# APIキーを設定
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEYが設定されていません。", file=sys.stderr)
    sys.exit(1)

genai.configure(api_key=api_key)

print("利用可能なモデルの一覧を取得します...\n")

# 利用可能なモデルをリストアップ
for model in genai.list_models():
    # 'generateContent'（文章生成）が可能なモデルのみを表示する
    if 'generateContent' in model.supported_generation_methods:
        print(model.name)