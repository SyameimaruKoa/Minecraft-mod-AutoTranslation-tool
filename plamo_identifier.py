import argparse
import hashlib
import json
import platform
import re
import subprocess
import uuid
from urllib.error import URLError
from urllib.request import urlopen

from lmlink_devices import find_lms_executable


def model_identifier(value):
    identifier = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
        raise ValueError("モデルIDは英数字で始まり、英数字・ハイフン・アンダースコア・ピリオドのみ使用できます")
    return identifier


def automatic_identifier(model_key):
    match = re.search(r"plamo-3-translate-\d+(?:\.\d+)?b", model_key.casefold())
    if not match:
        raise ValueError(f"PLaMoモデルを識別できません: {model_key}")
    hostname = re.sub(r"[^a-z0-9]+", "-", platform.node().casefold()).strip("-")[:20] or "pc"
    fingerprint = hashlib.sha256(
        f"{platform.node()}:{uuid.getnode():012x}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{match.group()}-{hostname}-{fingerprint}"


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
    local = [
        item for item in loaded_plamo_models()
        if item["identifier"] == identifier and not item.get("deviceIdentifier")
    ]
    if len(local) != 1:
        raise RuntimeError(f"このPCのPLaMoを一意に取得できません: {identifier}")
    fallback = {
        "parallel": local[0].get("parallel"),
        "context_length": local[0].get("contextLength")
    }
    try:
        with urlopen("http://127.0.0.1:1234/api/v1/models", timeout=5) as response:
            inventory = json.load(response)
        matching = [
            (model, instance)
            for model in inventory.get("models", [])
            if isinstance(model, dict) and model.get("type") == "llm"
            for instance in model.get("loaded_instances", [])
            if isinstance(instance, dict) and instance.get("id") == identifier
        ]
        if len(matching) == 1:
            model, instance = matching[0]
            return model.get("selected_variant") or model["key"], instance.get("config") or {}
    except (URLError, OSError, TimeoutError, ValueError, TypeError):
        pass
    print("情報: REST APIでロード設定を取得できないため、公式lms psの情報を使用します")
    return local[0]["modelKey"], fallback


def make_load_command(model_key, identifier, config):
    command = ["load", model_key, "--identifier", identifier]
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
    link_enabled = (
        isinstance(status, dict)
        and status.get("status") in ("online", "offline", "starting")
        and "deviceDisabled" not in (status.get("issues") or [])
        and "notLoggedIn" not in (status.get("issues") or [])
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
            local_after = loaded_plamo_models()
            if not any(
                item["identifier"] == new_identifier
                and not item.get("deviceIdentifier")
                for item in local_after
            ):
                raise RuntimeError("新しいIDがlms psで確認できません")
        except Exception as error:
            lms("unload", new_identifier, required=False)
            try:
                lms(*old_load)
            except Exception as restore_error:
                raise RuntimeError(
                    f"新しいIDでロード失敗。旧IDの復元にも失敗しました: {restore_error}"
                ) from error
            raise RuntimeError("新IDのロードに失敗したため旧IDへ復元しました") from error
        print(f"変更完了: {old_identifier} → {new_identifier}")
    finally:
        if link_enabled:
            lms("link", "enable")


def ensure_link_enabled():
    status = lms("link", "status", json_output=True, required=False)
    if not isinstance(status, dict):
        print("警告: LM Link状態を確認できません。必要ならlms link enableを実行してください")
        return
    issues = status.get("issues") or []
    if "notLoggedIn" in issues:
        raise RuntimeError("LM Linkへ未ログインです。lms loginの後に再実行してください")
    if "noAccess" in issues or "badVersion" in issues:
        raise RuntimeError(f"LM Linkを利用できません: {issues}")
    if "deviceDisabled" in issues:
        lms("link", "enable")
    elif status.get("status") == "offline":
        print("情報: LM Linkは再接続中です。接続後にクラスター参加が反映されます")


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
    parser.add_argument("--join", action="store_true", help="このWindows/Linux PCをLM Linkクラスターへ参加。端末固有のIDを自動設定")
    parser.add_argument("--model-key", help="参加対象PLaMoのmodelKey。未ロードの場合はこのモデルをロードする")
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
    if args.join:
        selected = [
            item for item in models
            if not item.get("deviceIdentifier")
            and (not args.model_key or item["modelKey"] == args.model_key)
        ]
        if args.current_id:
            selected = [item for item in selected if item["identifier"] == args.current_id]
        if not selected:
            if not args.model_key or args.current_id:
                parser.error("このPCにロード済みのPLaMoがありません。--model-keyを指定してロードしてください")
            new_id = model_identifier(args.new_id or automatic_identifier(args.model_key))
            if any(item["identifier"] == new_id for item in models):
                parser.error(f"モデルIDが既に使用されています: {new_id}")
            if not args.yes and input(f"{args.model_key}を{new_id}としてロードするか？ [y/N]: ").strip().casefold() != "y":
                print("参加を中止しました")
                return
            status = lms("link", "status", json_output=True, required=False)
            linked = (
                isinstance(status, dict) and status.get("status") in ("online", "offline", "starting")
                and "deviceDisabled" not in (status.get("issues") or [])
                and "notLoggedIn" not in (status.get("issues") or [])
            )
            if linked:
                lms("link", "disable")
            try:
                try:
                    lms("load", args.model_key, "--identifier", new_id, "-y")
                    local = loaded_plamo_models()
                    if not any(item["identifier"] == new_id and not item.get("deviceIdentifier") for item in local):
                        raise RuntimeError("ロード後にローカルPLaMoを確認できません")
                except Exception:
                    lms("unload", new_id, required=False)
                    raise
            finally:
                if linked:
                    lms("link", "enable")
            ensure_link_enabled()
            print(f"クラスター参加完了: {new_id}")
            return
        if len(selected) != 1:
            parser.error("ロード済みPLaMoが複数あります。--model-keyか--current-idを指定してください")
        current = selected[0]["identifier"]
        new_id = model_identifier(args.new_id or automatic_identifier(selected[0]["modelKey"]))
        if current == new_id:
            ensure_link_enabled()
            print(f"クラスター参加済み: {new_id}")
            return
        if not args.yes and input(f"{current} → {new_id} に変更するか？ [y/N]: ").strip().casefold() != "y":
            print("変更を中止しました")
            return
        rename_local_model(current, new_id)
        ensure_link_enabled()
        print(f"クラスター参加完了: {new_id}")
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
