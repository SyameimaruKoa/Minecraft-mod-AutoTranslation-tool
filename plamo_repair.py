import json
import time
import requests
import re
from collections import Counter


FORMAT_PATTERN = re.compile(
    r"§[0-9a-fk-orA-FK-OR]|(?<!\d)%(?:\d+\$)?(?:[-+#0,(]*\d*(?:\.\d+)?[a-zA-Z%]| \d*(?:\.\d+)?[dfeEgGaA](?![A-Za-z]))|\{[\w.:-]+\}|<[A-Za-z_][A-Za-z0-9_.:-]*>"
)
SYNTAX_PATTERN = re.compile(FORMAT_PATTERN.pattern + r"|\r\n|\r|\n|\\n")


def _printf_uses_argument(token):
    return token.startswith("%") and not token.endswith("%") and token != "%n"


def indexed_printf_token(token, position):
    if not _printf_uses_argument(token) or re.match(r"%\d+\$", token):
        return token
    return "%" + str(position) + "$" + token[1:]


def printf_argument_signatures(tokens):
    implicit_index = 0
    signatures = []
    for token in tokens:
        if not token.startswith("%"):
            continue
        if not _printf_uses_argument(token):
            signatures.append(("literal", token))
            continue
        numbered = re.match(r"%(\d+)\$(.+)", token)
        if numbered:
            signatures.append((int(numbered.group(1)), numbered.group(2)))
        else:
            implicit_index += 1
            signatures.append((implicit_index, token[1:]))
    return Counter(signatures)


def format_tokens_preserved(source, translated, pattern=FORMAT_PATTERN):
    expected = pattern.findall(source)
    actual = pattern.findall(translated)
    return (
        printf_argument_signatures(expected) == printf_argument_signatures(actual)
        and Counter(t for t in expected if not t.startswith("%"))
        == Counter(t for t in actual if not t.startswith("%"))
    )


def restore_ordered_format_markers(text, markers):
    argument_markers = [
        marker for marker, original in markers
        if _printf_uses_argument(original) and not re.match(r"%\d+\$", original)
    ]
    reorder = (
        all(text.count(marker) == 1 for marker in argument_markers)
        and any(
            text.index(first) > text.index(second)
            for first, second in zip(argument_markers, argument_markers[1:])
        )
    )
    implicit_index = 0
    for marker, original in markers:
        replacement = original
        if _printf_uses_argument(original) and not re.match(r"%\d+\$", original):
            implicit_index += 1
            if reorder:
                replacement = indexed_printf_token(original, implicit_index)
        text = text.replace(marker, replacement)
    return text



def syntax_free_text(value):
    return SYNTAX_PATTERN.sub("", value).strip()


def has_japanese_translation(value):
    return (
        isinstance(value, str)
        and re.search(r"[\u3040-\u30ff\u3400-\u9fff]", syntax_free_text(value)) is not None
    )


def apply_syntax_offsets(japanese, tokens, offsets, allow_reordering=False):
    if (
        not isinstance(japanese, str)
        or not isinstance(offsets, list)
        or len(tokens) != len(offsets)
    ):
        return None
    if any(
        type(offset) is not int or offset < 0 or offset > len(japanese)
        for offset in offsets
    ):
        return None
    reordered = offsets != sorted(offsets)
    if reordered and (
        not allow_reordering
        or not all(_printf_uses_argument(token) for token in tokens)
    ):
        return None
    insertions = {}
    implicit_index = 0
    for token, offset in zip(tokens, offsets):
        if reordered and _printf_uses_argument(token) and not re.match(r"%\d+\$", token):
            implicit_index += 1
            token = indexed_printf_token(token, implicit_index)
        insertions.setdefault(offset, []).append(token)
    return "".join(
        "".join(insertions.get(index, [])) + (japanese[index] if index < len(japanese) else "")
        for index in range(len(japanese) + 1)
    )


def syntax_text_unchanged(draft, repaired):
    return (
        isinstance(draft, str) and isinstance(repaired, str)
        and syntax_free_text(draft) == syntax_free_text(repaired)
    )


def _format_matches(source, repaired):
    return (
        format_tokens_preserved(source, repaired)
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
    if not has_japanese_translation(plain_draft):
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
    if not has_japanese_translation(rejected):
        print("警告: PLaMoの日本語本文がないため、構文だけでは修復できません")
        return None

    deterministic = restore_simple_syntax(source, rejected)
    if deterministic is not None:
        return deterministic

    active_model = require_loaded_lm_studio_model(model, api_url, load_policy, cancel_event=cancel_event)
    japanese = syntax_free_text(rejected)
    syntax_tokens = SYNTAX_PATTERN.findall(source)
    if not syntax_tokens:
        return None
    indexed_boundaries = "".join(
        f"[{index}]{character}" for index, character in enumerate(japanese)
    ) + f"[{len(japanese)}]"
    payload = {
        "model": active_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a syntax-placement assistant, NOT a translator. "
                    "Return ONLY a JSON array of integer character-boundary offsets. "
                    "Do not produce Japanese text or a revised translation. "
                    "The Japanese text is immutable and will be assembled by Python. "
                    "For each syntax token in source order, choose the zero-based insertion "
                    "boundary in the Japanese string. A boundary is before the character "
                    "of that index; the final index is the end of the string. "
                    "Each offset must be between 0 and text_length inclusive, "
                    "in any order when Japanese word order differs. Python will index reordered "
                    "unnumbered printf arguments. Do not add, remove or change tokens."
                )
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "english_source_for_token_locations": source,
                        "immutable_japanese": japanese,
                        "text_length": len(japanese),
                        "indexed_character_boundaries": indexed_boundaries,
                        "required_tokens_in_source_order": syntax_tokens,
                        "example": {
                            "japanese": "赤い花",
                            "token": "{0}",
                            "offsets": [2],
                            "assembled_by_python": "赤い{0}花"
                        }
                    },
                    ensure_ascii=False
                )
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "minecraft_syntax_positions",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "offsets": {
                            "type": "array",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["offsets"],
                    "additionalProperties": False
                }
            }
        },
        "temperature": 0,
        "max_tokens": max(128, min(1024, len(syntax_tokens) * 20 + 64)),
        "stream": False
    }
    try:
        response = requests.post(api_url, json=payload, timeout=(10, 180))
        if response.status_code >= 400:
            raise RuntimeError(
                f"構文修復モデルのAPIエラー HTTP {response.status_code}: {response.text[:400]}"
            )
        message = response.json()["choices"][0]["message"]["content"]
        offsets = json.loads(message)["offsets"]
        repaired = apply_syntax_offsets(japanese, syntax_tokens, offsets, allow_reordering=True)
        if repaired is None:
            print("警告: 補助モデルの構文位置が不正なため、修復結果を不採用")
            return None
        if not syntax_text_unchanged(rejected, repaired):
            print("警告: 日本語本文の不変条件を満たさないため、修復結果を不採用")
            return None
        if not _format_matches(source, repaired):
            print("警告: 補助モデルが構文を復元できませんでした")
            return None
        return repaired
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
        print(f"警告: 構文修復モデルの応答を採用できません: {error}")
        return None
