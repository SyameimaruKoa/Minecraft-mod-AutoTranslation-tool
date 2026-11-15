import json
import os
import tempfile
import time
from datetime import datetime, timedelta
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
                and not any(
                    os.path.splitext(os.path.basename(path.replace("\\", "/")))[0].casefold() == "en_ud"
                    for path in old["language_files"]
                )
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


class TranslationETA:
    def __init__(self, total, prior_seconds_per_item=None, clock=None, wall_clock=None):
        self.total = max(0, total)
        self.prior = prior_seconds_per_item
        self.clock = clock or time.monotonic
        self.wall_clock = wall_clock or (lambda: datetime.now().astimezone())
        self.started = self.clock()

    def estimate(self, completed):
        remaining = max(0, self.total - completed)
        if not remaining:
            seconds = 0
        elif completed <= 0:
            seconds = (
                round(remaining * self.prior)
                if self.prior is not None else None
            )
        else:
            elapsed = max(0, self.clock() - self.started)
            observed = elapsed / completed
            if self.prior is None:
                rate = observed
            else:
                observed_weight = completed / (completed + 64)
                rate = (
                    self.prior * (1 - observed_weight)
                    + observed * observed_weight
                )
            seconds = round(rate * remaining)
        if seconds is None:
            return None, None
        finished = self.wall_clock() + timedelta(seconds=seconds)
        return seconds, finished.strftime("%Y-%m-%d %H:%M")


class ClusterETA(TranslationETA):
    def __init__(self, total, prior_seconds_per_item=None, clock=None, wall_clock=None):
        super().__init__(total, prior_seconds_per_item, clock, wall_clock)
        self.active = ()
        self.workers = 1
        self.rates = {}
        self.sampled_items = 0
        self.calibration = 1.0
        self.epoch_started = self.started
        self.epoch_items = 0

    def set_active(self, models, workers):
        updated = tuple(dict.fromkeys(models))
        if updated == self.active and workers == self.workers:
            return False
        self.active = updated
        self.workers = workers
        self.epoch_started = self.clock()
        self.epoch_items = 0
        return True

    def observe(self, model, items, duration):
        if items <= 0 or duration <= 0:
            return
        speed = items / duration
        old = self.rates.get(model)
        self.rates[model] = speed if old is None else old * 0.8 + speed * 0.2
        self.sampled_items += items
        self.epoch_items += items
        interval = self.clock() - self.epoch_started
        baseline = sum(
            self.rates[member] * self.workers
            for member in self.active if member in self.rates
        )
        if interval >= 5 and self.epoch_items >= self.workers * 2 and baseline > 0:
            ratio = min(1.5, max(0.1, self.epoch_items / interval / baseline))
            self.calibration = self.calibration * 0.8 + ratio * 0.2

    def estimate(self, completed):
        remaining = max(0, self.total - completed)
        if remaining == 0:
            return 0, self.wall_clock().strftime("%Y-%m-%d %H:%M")
        rate = sum(
            self.rates[member] * self.workers
            for member in self.active if member in self.rates
        ) * self.calibration
        if rate <= 0:
            return super().estimate(completed)
        if self.prior is not None:
            weight = min(1, self.sampled_items / 16)
            rate = rate * weight + (1 / self.prior) * (1 - weight)
        seconds = round(remaining / rate)
        finish = self.wall_clock() + timedelta(seconds=seconds)
        return seconds, finish.strftime("%Y-%m-%d %H:%M")


class TranslationSpeedProfile:
    def __init__(self, output_dir, models, workers):
        self.path = os.path.join(output_dir, "plamo_speed.json")
        self.data = read_json(self.path)
        self.key = json.dumps([list(models), workers], ensure_ascii=False)
        self.seconds_per_item = self.data.get(self.key)
        if not isinstance(self.seconds_per_item, (float, int)) or self.seconds_per_item <= 0:
            self.seconds_per_item = None
        self.last_recorded_items = 0

    def estimate(self, remaining):
        if self.seconds_per_item is None:
            return None
        return max(0, round(remaining * self.seconds_per_item))

    def observe_cumulative(self, completed, elapsed_seconds):
        if completed <= self.last_recorded_items or elapsed_seconds <= 0:
            return
        self.last_recorded_items = completed
        self.observe(completed, elapsed_seconds)

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
