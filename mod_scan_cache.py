import json
import os
import tempfile
from pathlib import Path


def save_atomic_json(path, data):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=destination.name + ".", suffix=".tmp", delete=False
        ) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=4)
        os.replace(name, destination)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            result = json.load(stream)
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


class ModScanCache:
    VERSION = 1

    def __init__(self, input_dir, output_dir, shader_mode=False):
        self.input_dir = os.path.normcase(os.path.realpath(input_dir))
        self.shader_mode = bool(shader_mode)
        self.path = os.path.join(output_dir, "mod_scan_cache.json")
        existing = read_json(self.path)
        if (
            existing.get("version") != self.VERSION
            or existing.get("input_dir") != self.input_dir
            or existing.get("shader_mode") != self.shader_mode
            or not isinstance(existing.get("files"), dict)
        ):
            existing = {}
        self.files = existing.get("files", {})

    def scan(self, filenames, extract, detect_pack):
        updated = {}
        plan = []
        cached = 0
        rescanned = 0
        for filename in filenames:
            filepath = os.path.join(self.input_dir, filename)
            stat = os.stat(filepath)
            signature = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
            old = self.files.get(filename)
            valid = (
                isinstance(old, dict)
                and old.get("signature") == signature
                and isinstance(old.get("language_files"), dict)
                and isinstance(old.get("pack_format"), int)
            )
            if valid:
                record = old
                cached += 1
            else:
                record = {
                    "signature": signature,
                    "language_files": extract(filepath, self.shader_mode),
                    "pack_format": detect_pack(filepath)
                }
                rescanned += 1
            updated[filename] = record
            plan.append((
                filename, record["language_files"], record["pack_format"]
            ))
        removed = len(set(self.files) - set(updated))
        self.files = updated
        save_atomic_json(self.path, {
            "version": self.VERSION,
            "input_dir": self.input_dir,
            "shader_mode": self.shader_mode,
            "files": self.files
        })
        return plan, {"reused": cached, "rescanned": rescanned, "removed": removed}


class TranslationSpeedProfile:
    def __init__(self, output_dir, models, workers):
        self.path = os.path.join(output_dir, "plamo_speed.json")
        self.data = read_json(self.path)
        self.key = json.dumps([list(models), workers], ensure_ascii=False)
        self.seconds_per_item = self.data.get(self.key)
        if not isinstance(self.seconds_per_item, (float, int)) or self.seconds_per_item <= 0:
            self.seconds_per_item = None

    def estimate(self, remaining):
        if self.seconds_per_item is None:
            return None
        return max(0, round(remaining * self.seconds_per_item))

    def observe(self, unique_items, elapsed_seconds):
        if unique_items <= 0 or elapsed_seconds <= 0:
            return
        sample = elapsed_seconds / unique_items
        if self.seconds_per_item is None:
            self.seconds_per_item = sample
        else:
            self.seconds_per_item = self.seconds_per_item * 0.7 + sample * 0.3
        self.data[self.key] = self.seconds_per_item
        save_atomic_json(self.path, self.data)
