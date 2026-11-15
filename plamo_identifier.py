import argparse
import json
import platform
import re
import subprocess

import requests

from lmlink_devices import find_lms_executable


def model_identifier(value):
    identifier = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
        raise ValueError("モデルIDは英数字で始まり、英数字・ハイフン・アンダースコア・ピリオドのみ使用できます")
    return identifier


def lms(*arguments, json_output=False, required=True):
    command = [find_lms_executable(), *arguments]
    if json_output:
        command.append("--json")
    process = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8-sig",
        errors="replace", timeout=120, check=False
    )
    if process.returncode:
        if required:
            raise RuntimeError(
                f"lms {' '.join(arguments)}: {process.stderr.strip() or process.stdout.strip()}"
            )
        return None
    if json_output:
        return json.loads(process.stdout)
    return process.stdout.strip()


def loaded_plamo_models():
    models = lms("ps", json_output=True)
    if not isinstance(models, list):
        raise RuntimeError("lms ps --jsonの結果が不正です")
    return [
        item for item in models
        if isinstance(item, dict)
        and isinstance(item.get("modelKey"), str)
        and isinstance(item.get("identifier"), str)
        and "plamo-3-translate" in item["modelKey"].casefold()
    ]


def load_configuration(identifier):
    response = requests.get("http://127.0.0.1:1234/api/v1/models", timeout=10)
    response.raise_for_status()
    result = response.json()
    matching = [
        (model, instance)
        for model in result.get("models", [])
        if isinstance(model, dict) and model.get("type") == "llm"
        for instance in model.get("loaded_instances", [])
        if isinstance(instance, dict) and instance.get("id") == identifier
    ]
    if len(matching) != 1:
        raise RuntimeError(f"ローカルPLaMoのロード設定を一意に取得できません: {identifier}")
    model, instance = matching[0]
    return model.get("selected_variant") or model["key"], instance.get("config") or {}


def make_load_command(model_key, identifier, config):
    command = ["load", model_key, "--identifier", identifier, "--gpu", "max"]
    for flag, name in (
        ("--parallel", "parallel"),
        ("--context-length", "context_length")
    ):
        value = config.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            command.extend([flag, str(value)])
    command.append("-y")
    return command


def rename_local_model(old_identifier, new_identifier):
    new_identifier = model_identifier(new_identifier)
    listed = loaded_plamo_models()
    matches = [
        item for item in listed
        if item["identifier"] == old_identifier
        and not item.get("deviceIdentifier")
    ]
    if len(matches) != 1:
        raise RuntimeError(f"このPCのPLaMoモデルが一意に見つかりません: {old_identifier}")
    if old_identifier == new_identifier:
        print("情報: モデルIDは変更されていません")
        return
    collisions = [item for item in listed if item["identifier"] == new_identifier]
    if collisions:
        raise RuntimeError(f"そのモデルIDは既にLM Link上で使用されています: {new_identifier}")

    status = lms("link", "status", json_output=True, required=False)
    link_enabled = isinstance(status, dict) and status.get("status") in (
        "online", "connected", "connecting", "enabled"
    )
    if link_enabled:
        lms("link", "disable")
    try:
        local = loaded_plamo_models()
        if sum(item["identifier"] == old_identifier for item in local) != 1:
            raise RuntimeError("LM Link切断後、対象のローカルPLaMoを識別できません")
        model_key, config = load_configuration(old_identifier)
        new_load = make_load_command(model_key, new_identifier, config)
        old_load = make_load_command(model_key, old_identifier, config)
        lms("unload", old_identifier)
        try:
            lms(*new_load)
        except Exception as error:
            try:
                lms(*old_load)
            except Exception as restore_error:
                raise RuntimeError(
                    f"新しいIDでロード失敗。旧IDの復元にも失敗しました: {restore_error}"
                ) from error
            raise RuntimeError("新IDのロードに失敗したため旧IDへ復元しました") from error
        local_after = loaded_plamo_models()
        if not any(item["identifier"] == new_identifier for item in local_after):
            raise RuntimeError("新しいIDがlms psで確認できません")
        print(f"変更完了: {old_identifier} → {new_identifier}")
    finally:
        if link_enabled:
            lms("link", "enable")


def choose_local_model(models):
    local = [item for item in models if not item.get("deviceIdentifier")]
    if not local:
        raise RuntimeError("このPCでロード済みのPLaMoがありません")
    print("ローカルPLaMoモデル:")
    for index, item in enumerate(local, 1):
        print(f"  [{index}] {item['identifier']}  ({item['modelKey']})")
    if len(local) == 1:
        return local[0]["identifier"]
    choice = input("対象番号: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(local):
        raise ValueError("モデル番号が不正です")
    return local[int(choice) - 1]["identifier"]


def main():
    parser = argparse.ArgumentParser(
        description="ローカルPLaMoのインスタンスIDだけを変更し、LM Linkクラスターから個別に指定できるようにする"
    )
    parser.add_argument("--current-id", help="変更前のローカルPLaMoインスタンスID")
    parser.add_argument("--new-id", help="変更後の一意なインスタンスID")
    parser.add_argument("--list", action="store_true", help="ロード済みPLaMoと現在のIDを一覧表示")
    parser.add_argument("--yes", action="store_true", help="変更確認を省略する")
    parser.add_argument("--interactive", action="store_true", help="画面上で変更するモデルとIDを選ぶ")
    args = parser.parse_args()
    models = loaded_plamo_models()
    if args.list:
        for item in models:
            print(
                f"{item['identifier']} / {item['modelKey']} / "
                f"{item.get('deviceIdentifier') or 'local'}"
            )
        return
    current = args.current_id or choose_local_model(models)
    if not args.new_id:
        if not args.interactive:
            parser.error("ID変更には--new-idが必要です。対話設定には--interactiveを指定してください")
        suffix = re.sub(r"[^a-z0-9-]", "-", platform.node().casefold()).strip("-")
        suggested = f"{current}-{suffix}" if suffix else f"{current}-local"
        proposed = input(f"新しいモデルID [Enter: {suggested}]: ").strip()
        new_id = proposed or suggested
    else:
        new_id = args.new_id
    new_id = model_identifier(new_id)
    if not args.yes:
        answer = input(f"{current} → {new_id} に変更するか？ [y/N]: ").strip().casefold()
        if answer != "y":
            print("変更を中止しました")
            return
    rename_local_model(current, new_id)


if __name__ == "__main__":
    main()
