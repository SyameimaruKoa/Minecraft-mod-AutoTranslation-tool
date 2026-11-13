import json
import re
import subprocess
import time


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


def _lms_json(*arguments, required=True):
    try:
        process = subprocess.run(
            ["lms", *arguments, "--json"],
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


def discover_plamo_models(excluded_devices=None, model_filter=None):
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
            raise ValueError(f"除外デバイスが見つかりません: {excluded_name}")
        selected_exclusions.append(devices[key])

    ranked_models = []
    all_model_owners = {}
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
        if identifier in all_model_owners:
            raise RuntimeError(
                f"モデルID[{identifier}]が複数のロード済みモデルに使用されています。"
                "除外した端末へ推論が送られる可能性があるため停止します。"
                "モデルごとに異なるインスタンスIDを設定してください。"
            )
        all_model_owners[identifier] = device_id
        if device_id not in selected_exclusions:
            ranked_models.append((plamo_model_priority(model_key), identifier))

    if not ranked_models:
        raise RuntimeError("除外後に使用可能なロード済みPLaMoモデルがありません")
    return [
        identifier for _, identifier in sorted(
            ranked_models, key=lambda item: item[0], reverse=True
        )
    ]
