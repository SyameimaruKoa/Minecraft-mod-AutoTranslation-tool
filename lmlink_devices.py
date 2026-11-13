import json
import subprocess
import time


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

    model_list = []
    model_owners = {}
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
        if device_id in selected_exclusions:
            continue
        if identifier in model_owners:
            raise RuntimeError(
                f"モデルID[{identifier}]が複数デバイスに存在します。"
                "REST APIで端末を確実に区別できません。"
                "各端末で異なるモデルインスタンスIDを設定してください。"
            )
        model_owners[identifier] = device_id
        model_list.append(identifier)

    if not model_list:
        raise RuntimeError("除外後に使用可能なロード済みPLaMoモデルがありません")
    return model_list
