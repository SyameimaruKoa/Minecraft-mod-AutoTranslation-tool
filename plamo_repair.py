import json
import time
import requests
import re


FORMAT_PATTERN = re.compile(
    r"§[0-9a-fk-orA-FK-OR]|(?<!\d)%(?:\d+\$)?(?:[-+#0,(]*\d*(?:\.\d+)?[a-zA-Z%]| \d*(?:\.\d+)?[dfeEgGaA](?![A-Za-z]))|\{[\w.:-]+\}|<[A-Za-z_][\w.:-]*>"
)
SYNTAX_PATTERN = re.compile(FORMAT_PATTERN.pattern + r"|\r\n|\r|\n|\\n")


def syntax_free_text(value):
    return SYNTAX_PATTERN.sub("", value).strip()


def syntax_text_unchanged(draft, repaired):
    return (
        isinstance(draft, str) and isinstance(repaired, str)
        and syntax_free_text(draft) == syntax_free_text(repaired)
    )


def _format_matches(source, repaired):
    expected = FORMAT_PATTERN.findall(source)
    actual = FORMAT_PATTERN.findall(repaired)

    def numbered(tokens):
        return sorted(token for token in tokens if re.match(r"%\d+\$", token))

    def unnumbered(tokens):
        return [token for token in tokens if token.startswith("%") and not re.match(r"%\d+\$", token)]

    def others(tokens):
        return sorted(token for token in tokens if not token.startswith("%"))

    return (
        numbered(expected) == numbered(actual)
        and unnumbered(expected) == unnumbered(actual)
        and others(expected) == others(actual)
        and re.findall(r"§[0-9a-fk-orA-FK-OR]", source)
        == re.findall(r"§[0-9a-fk-orA-FK-OR]", repaired)
        and re.findall(r"\r\n|\r|\n|\\n", source)
        == re.findall(r"\r\n|\r|\n|\\n", repaired)
    )


def restore_simple_syntax(source, draft):
    if not draft or not draft.strip():
        return None

    tokens = list(SYNTAX_PATTERN.finditer(source))
    plain_draft = SYNTAX_PATTERN.sub("", draft).strip()
    if not plain_draft:
        return None

    if not tokens:
        return plain_draft if syntax_text_unchanged(draft, plain_draft) else None

    prefix_end = 0
    suffix_start = len(source)
    for match in tokens:
        if match.start() == prefix_end:
            prefix_end = match.end()
        else:
            break
    for match in reversed(tokens):
        if match.end() == suffix_start:
            suffix_start = match.start()
        else:
            break

    middle = source[prefix_end:suffix_start]
    if SYNTAX_PATTERN.search(middle):
        return None

    suffix_prefix = ""
    if suffix_start < len(source):
        delimiter = re.search(r"[ \t]+$", middle)
        if delimiter and not plain_draft.endswith((" ", "\t")):
            suffix_prefix = delimiter.group()
    repaired = source[:prefix_end] + plain_draft + suffix_prefix + source[suffix_start:]
    if syntax_text_unchanged(draft, repaired) and _format_matches(source, repaired):
        return repaired
    return None



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


def repair_plamo_translation(source, rejected, model, api_url, load_policy="wait", cancel_event=None):
    if not isinstance(rejected, str) or not syntax_free_text(rejected):
        print("警告: PLaMoの日本語訳がないため、構文だけでは修復できません")
        return None

    deterministic = restore_simple_syntax(source, rejected)
    if deterministic is not None:
        return deterministic

    active_model = require_loaded_lm_studio_model(model, api_url, load_policy, cancel_event=cancel_event)
    required_syntax = SYNTAX_PATTERN.findall(source)
    payload = {
        "model": active_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a syntax-only editor, NOT a translator. "
                    "The Japanese draft is immutable user content. "
                    "Your only task is to place, remove, or reorder the exact formatting "
                    "tokens found in the English source (printf, {0}, Minecraft section-sign codes, "
                    "and newline escapes). Never translate, paraphrase, correct spelling, "
                    "add new Japanese words, or change any existing Japanese characters. "
                    "Remove invented formatting tokens that are absent from the source. "
                    "Return one JSON object with the repaired_text property."
                )
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "english_source_for_syntax_only": source,
                        "japanese_draft_do_not_retranslate": rejected,
                        "required_syntax_tokens": required_syntax,
                        "japanese_text_must_remain_exactly": syntax_free_text(rejected)
                    },
                    ensure_ascii=False
                )
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "minecraft_syntax_repair",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"repaired_text": {"type": "string"}},
                    "required": ["repaired_text"],
                    "additionalProperties": False
                }
            }
        },
        "temperature": 0,
        "max_tokens": max(256, min(4096, len(rejected) * 2 + 128)),
        "stream": False
    }
    try:
        response = requests.post(api_url, json=payload, timeout=(10, 180))
        if response.status_code >= 400:
            raise RuntimeError(
                f"構文修復モデルのAPIエラー HTTP {response.status_code}: {response.text[:400]}"
            )
        message = response.json()["choices"][0]["message"]["content"]
        repaired = json.loads(message)["repaired_text"]
        if not isinstance(repaired, str):
            raise ValueError("構文修復応答が文字列ではありません")
        if not syntax_text_unchanged(rejected, repaired):
            print("警告: 補助モデルが日本語本文を変更したため、修復結果を不採用")
            return None
        if not _format_matches(source, repaired):
            print("警告: 補助モデルが構文を復元できませんでした")
            return None
        return repaired
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
        print(f"警告: 構文修復モデルの応答を採用できません: {error}")
        return None
