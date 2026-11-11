import json
import time
import requests


def _lm_studio_base_url(api_url):
    if "/v1/" not in api_url:
        raise ValueError("LM Studio API URLは /v1/... を含む必要があります")
    return api_url.split("/v1/", 1)[0].rstrip("/")


def get_loaded_lm_studio_models(api_url):
    base_url = _lm_studio_base_url(api_url)
    try:
        response = requests.get(base_url + "/api/v1/models", timeout=10)
        if response.status_code == 404:
            response = requests.get(base_url + "/api/v0/models", timeout=10)
            response.raise_for_status()
            loaded = {}
            for model in response.json().get("data", []):
                if model.get("state") == "loaded" and isinstance(model.get("id"), str):
                    loaded[model["id"]] = model["id"]
            return loaded
        response.raise_for_status()
        loaded = {}
        for model in response.json().get("models", []):
            if model.get("type") != "llm":
                continue
            instances = model.get("loaded_instances", [])
            key = model.get("key")
            for instance in instances:
                instance_id = instance.get("id")
                if isinstance(instance_id, str) and instance_id:
                    loaded[instance_id] = instance_id
                    if key and len(instances) == 1:
                        loaded[key] = instance_id
        return loaded
    except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError) as error:
        raise RuntimeError(
            f"LM Studioのロード状態を確認できません: {base_url} ({error})"
        ) from error


def require_loaded_lm_studio_model(model, api_url, policy="error", poll_seconds=3, cancel_event=None):
    if policy not in ("error", "wait"):
        raise ValueError("モデルの未ロード時の動作はerrorまたはwaitで指定してください")
    announced = False
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError(f"モデル[{model}]のロード待機を中断しました")
        loaded = get_loaded_lm_studio_models(api_url)
        if model in loaded:
            if announced:
                print(f"情報: モデル[{model}]の手動ロードを確認しました")
            return loaded[model]
        if not announced:
            available = ", ".join(sorted(set(loaded.values()))) or "なし"
            message = (
                f"モデル[{model}]がLM Studioにロードされていません。"
                "LM Studioで手動ロードしてください（本ツールは自動ロードしません）。"
                f" ロード済み: {available}"
            )
            if policy == "error":
                raise RuntimeError(message)
            print("情報: " + message + " ロードされるまで待機します（Ctrl+Cで中断）")
            announced = True
        time.sleep(poll_seconds)


def repair_plamo_translation(source, rejected, model, api_url, load_policy="error", cancel_event=None):
    active_model = require_loaded_lm_studio_model(model, api_url, load_policy, cancel_event=cancel_event)
    payload = {
        "model": active_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are repairing an English-to-Japanese localization for a Minecraft mod. "
                    "Use the English source as the authority and the rejected Japanese result only "
                    "as an optional draft. Return a natural Japanese translation, not explanations. "
                    "Preserve every format argument (%s, %d, %1$s, etc.), variable (<name>, {name}), "
                    "Minecraft § color code, and newline exactly as in the English source. "
                    "Never add or remove format arguments. Return JSON matching the response schema."
                )
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"english_source": source, "rejected_japanese": rejected or ""},
                    ensure_ascii=False
                )
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "minecraft_translation_repair",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"translation": {"type": "string"}},
                    "required": ["translation"],
                    "additionalProperties": False
                }
            }
        },
        "temperature": 0,
        "max_tokens": max(256, min(4096, len(source) * 2)),
        "stream": False
    }
    try:
        response = requests.post(api_url, json=payload, timeout=(10, 180))
        if response.status_code >= 400:
            raise RuntimeError(
                f"修復モデルのAPIエラー HTTP {response.status_code}: {response.text[:400]}"
            )
        message = response.json()["choices"][0]["message"]["content"]
        translated = json.loads(message)["translation"]
        if not isinstance(translated, str):
            raise ValueError("修復応答のtranslationが文字列ではありません")
        return translated
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
        print(f"警告: 修復モデルの応答を採用できません: {error}")
        return None
