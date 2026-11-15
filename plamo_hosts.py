from urllib.parse import urlparse

import requests


def parse_plamo_hosts(value):
    if not value:
        return []
    hosts = value.split(",") if isinstance(value, str) else list(value)
    result = []
    for item in hosts:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("PLaMo接続先に空欄は指定できません")
        address = item.strip().rstrip("/")
        parsed = urlparse(address)
        if (
            parsed.scheme not in ("http", "https") or not parsed.netloc
            or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment
        ):
            raise ValueError(f"接続先はhttp(s)://ホスト:ポートで指定してください: {item}")
        if address in result:
            raise ValueError(f"PLaMo接続先が重複しています: {address}")
        result.append(address)
    return result


def loaded_plamo_info(base_url, instance_id, timeout=5):
    response = requests.get(f"{base_url}/api/v1/models", timeout=timeout)
    response.raise_for_status()
    models = response.json().get("models")
    if not isinstance(models, list):
        raise RuntimeError(f"LM Studioのモデル一覧形式が不正です: {base_url}")
    matches = [
        item for item in models
        if isinstance(item, dict) and item.get("type") == "llm"
        and isinstance(item.get("key"), str)
        and isinstance(item.get("loaded_instances"), list)
        and any(
            isinstance(instance, dict) and instance.get("id") == instance_id
            for instance in item["loaded_instances"]
        )
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"同一接続先でモデルID[{instance_id}]が複数のmodelKeyに一致します: {base_url}"
        )
    return matches[0] if matches else None


def plamo_info_signature(item):
    quantization = item.get("quantization")
    quantization_name = (
        quantization.get("name")
        if isinstance(quantization, dict) else quantization
    )
    return (
        item["key"],
        quantization_name,
        item.get("size_bytes")
    )


def available_plamo_hosts(hosts, instance_id, expected_signature=None):
    available = []
    reference = expected_signature
    for host in hosts:
        try:
            info = loaded_plamo_info(host, instance_id)
        except (requests.RequestException, ValueError) as error:
            print(f"警告: PLaMo接続先[{host}]を照会できません: {error}", flush=True)
            continue
        if info is None:
            continue
        signature = plamo_info_signature(info)
        if reference is None:
            reference = signature
        elif signature != reference:
            raise RuntimeError(
                f"PLaMo接続先[{host}]のモデルが一致しません: "
                f"{signature} != {reference}"
            )
        available.append(host)
    return available, reference
