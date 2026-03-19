import os
import sys
from dotenv import load_dotenv
from google import genai

# コード引用元
# https://zenn.dev/croco_82/articles/30a4112805c5dd
# 事前準備
# pip install google-genai python-dotenv

load_dotenv(encoding="utf-8-sig")
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEYが設定されていません。", file=sys.stderr)
    sys.exit(1)
client = genai.Client(api_key=api_key)
for model in client.models.list():
    print(model.model_dump())
    break