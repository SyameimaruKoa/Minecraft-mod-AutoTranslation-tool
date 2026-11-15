import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def plamo_model_priority(model_key):
    match = re.search(
        r"plamo-3-translate-(\d+(?:\.\d+)?)b(?:\b|[-_])",
        model_key.casefold()
    )
    return float(match.group(1)) if match else -1.0


def parse_excluded_devices(value):
    if not value:
        return []
    devices = value.split(",") if isinstance(value, str) else list(value)
    if any(not isinstance(device, str) or not device.strip() for device in devices):
        raise ValueError("除外デバイスに空欄を含められません")
    normalized = [device.strip() for device in devices]
    if len(normalized) != len(set(device.casefold() for device in normalized)):
        raise ValueError("除外デバイスが重複しています")
    return normalized


IS_WINDOWS = os.name == "nt"


def find_lms_executable():
    executable = shutil.which("lms.exe") if IS_WINDOWS else shutil.which("lms")
    if executable:
        return executable
    if not IS_WINDOWS:
        for root in (Path.home() / ".lmstudio", Path.home() / ".cache" / "lm-studio"):
            candidate = root / "bin" / "lms"
            if candidate.is_file():
                return str(candidate)
        raise FileNotFoundError("LM Studio CLI (lms) が見つかりません。~/.lmstudio/bin/lmsまたはPATHを確認してください。")

    executable = shutil.which("lms")
    if executable:
        return executable

    home = Path.home()
    roots = [home / ".lmstudio", home / ".cache" / "lm-studio"]
    pointer = home / ".lmstudio-home-pointer"
    if pointer.is_file():
        try:
            selected = Path(pointer.read_text(encoding="utf-8-sig").strip()).expanduser()
            if selected.is_absolute():
                roots.insert(0, selected)
        except (OSError, UnicodeError, ValueError):
            pass

    for root in roots:
        candidate = root / "bin" / "lms.exe"
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(
        "LM Studio CLI (lms.exe) が見つかりません。"
        "LM Studioを起動し、~/.lmstudio/bin または ~/.cache/lm-studio/bin の"
        "lms.exeを確認してください。"
    )


def _lms_json(*arguments, required=True):
    try:
        process = subprocess.run(
            [find_lms_executable(), *arguments, "--json"],
            capture_output=True, text=True, encoding="utf-8-sig",
            errors="replace", timeout=20, check=False
        )
        if process.returncode:
            raise RuntimeError(process.stderr.strip() or process.stdout.strip())
        return json.loads(process.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, RuntimeError) as error:
        if required:
            raise RuntimeError(
                f"LM Linkの状態を取得できません: lms {' '.join(arguments)} --json ({error})"
            ) from error
        return None


def discover_plamo_models(
    excluded_devices=None, model_filter=None, expected_model_key=None,
    allow_empty=False, return_model_key=False, ignore_missing_exclusions=False
):
    excluded = parse_excluded_devices(excluded_devices)
    loaded = _lms_json("ps")
    if not isinstance(loaded, list):
        raise RuntimeError("lms ps --jsonの形式が不明です")
    link = _lms_json("link", "status", required=bool(excluded)) if excluded else None
    if link is not None and not isinstance(link, dict):
        raise RuntimeError("lms link status --jsonの形式が不明です")
    devices = {"local": None, "this device": None}
    peer_ids = set()
    if link:
        local_name = link.get("deviceName")
        if isinstance(local_name, str):
            devices[local_name.casefold()] = None
        for peer in link.get("peers", []):
            if not isinstance(peer, dict):
                continue
            device_id = peer.get("deviceIdentifier")
            name = peer.get("deviceName")
            if not isinstance(device_id, str) or not device_id:
                continue
            peer_ids.add(device_id)
            devices[device_id.casefold()] = device_id
            if isinstance(name, str) and name:
                key = name.casefold()
                if key in devices and devices[key] != device_id:
                    raise ValueError(f"同名のLM Linkデバイスが存在します: {name}（デバイスIDで指定してください）")
                devices[key] = device_id

    for item in loaded:
        if isinstance(item, dict):
            device_id = item.get("deviceIdentifier")
            if isinstance(device_id, str) and device_id:
                devices[device_id.casefold()] = device_id

    selected_exclusions = []
    for excluded_name in excluded:
        key = excluded_name.casefold()
        if key not in devices:
            if ignore_missing_exclusions:
                continue
            raise ValueError(f"除外デバイスが見つかりません: {excluded_name}")
        selected_exclusions.append(devices[key])

    ranked_models = []
    all_model_owners = {}
    selected_device_models = {}
    selected_identifiers = set()
    duplicate_identifiers = set()
    selected_identifier_owners = {}
    excluded_identifier_owners = {}
    selected_model_key = expected_model_key
    for item in loaded:
        if not isinstance(item, dict):
            continue
        model_key = item.get("modelKey")
        identifier = item.get("identifier")
        device_id = item.get("deviceIdentifier")
        if not isinstance(model_key, str) or not isinstance(identifier, str):
            continue
        if not model_key or not identifier:
            continue
        if model_filter:
            if model_filter not in (model_key, identifier):
                continue
        elif "plamo-3-translate" not in model_key.casefold():
            continue
        previous_key = all_model_owners.get(identifier)
        if previous_key is not None and previous_key != model_key:
            raise RuntimeError(
                f"モデルID[{identifier}]が異なるPLaMoのmodelKeyに使われています: "
                f"{previous_key} != {model_key}"
            )
        if previous_key is not None:
            duplicate_identifiers.add(identifier)
        all_model_owners[identifier] = model_key
        if expected_model_key is not None and model_key != expected_model_key:
            continue
        if device_id in selected_exclusions:
            excluded_identifier_owners.setdefault(identifier, set()).add(device_id)
        else:
            selected_identifier_owners.setdefault(identifier, set()).add(device_id)
            if device_id in selected_device_models:
                previous = selected_device_models[device_id]
                label = device_id if device_id is not None else "local"
                raise RuntimeError(
                    f"同一端末[{label}]に複数の翻訳用PLaMoがロードされています: "
                    f"{previous}, {identifier}。"
                    "1端末につき翻訳用PLaMoを1つだけロードしてください。"
                    "修復用LFMはこの制限の対象外です。"
                )
            if selected_model_key is not None and model_key != selected_model_key:
                raise RuntimeError(
                    "複数端末での分散翻訳には同じPLaMoモデルID（modelKey）が必要です: "
                    f"{selected_model_key} != {model_key}。"
                    "同じモデルを各端末でロードするか、異なるモデルの端末を除外してください。"
                    "モデルインスタンスID（identifier）は端末ごとに異なる値が必要です。"
                )
            selected_model_key = model_key
            selected_device_models[device_id] = identifier
            if identifier not in selected_identifiers:
                selected_identifiers.add(identifier)
                ranked_models.append((plamo_model_priority(model_key), identifier))

    shared_with_excluded = (
        set(selected_identifier_owners) & set(excluded_identifier_owners)
    )
    if shared_with_excluded:
        identifiers = ", ".join(sorted(shared_with_excluded))
        raise RuntimeError(
            "除外端末と使用端末で同じモデルIDを共有しているため、"
            f"LM Link REST APIでは送信先を保証できません: {identifiers}"
        )
    if duplicate_identifiers and not allow_empty:
        print(
            "情報: 同じモデルIDを複数端末で検出。"
            "LM LinkのREST APIは優先デバイスへ送信するため、"
            "端末数を推論先の数としては数えません。",
            flush=True
        )

    if not ranked_models and not allow_empty:
        raise RuntimeError("除外後に使用可能なロード済みPLaMoモデルがありません")
    identifiers = [
        identifier for _, identifier in sorted(
            ranked_models, key=lambda item: item[0], reverse=True
        )
    ]
    if return_model_key:
        return identifiers, selected_model_key
    return identifiers
