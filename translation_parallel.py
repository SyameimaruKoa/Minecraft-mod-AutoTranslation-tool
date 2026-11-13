import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def translate_parallel_batches(text_dict, workers, batch_size, translator, label):
    if workers < 1:
        raise ValueError("並列数は1以上を指定してください")
    if batch_size < 1:
        raise ValueError("バッチサイズは1以上を指定してください")
    if not text_dict:
        return {}
    keys = list(text_dict)
    batches = [
        {key: text_dict[key] for key in keys[index:index + batch_size]}
        for index in range(0, len(keys), batch_size)
    ]
    results = {}
    completed = 0
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(workers, len(batches))) as executor:
        futures = {executor.submit(translator, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            translated = future.result()
            if not isinstance(translated, dict):
                raise ValueError(f"{label}の並列翻訳結果は辞書である必要があります")
            results.update({
                key: translated[key] for key in batch if key in translated
            })
            completed += len(batch)
            remaining = int((time.monotonic() - start) / completed * (len(keys) - completed))
            print(
                f"  並列進捗[{label}]: {completed}/{len(keys)} "
                f"- 残り予想: {remaining // 60}分{remaining % 60}秒 "
                f"- 同時実行: {min(workers, len(batches))}"
            )
    return {key: results[key] for key in keys if key in results}


class SynchronizedModelSelector:
    def __init__(self, selector):
        self.selector = selector
        self.lock = threading.RLock()
        self.context = threading.local()

    def get_current_model(self):
        with self.lock:
            model = self.selector.get_current_model()
            self.context.model = model
            return model

    def report_success(self):
        with self.lock:
            return self.selector.report_success(self.context.model)

    def report_failure(self):
        with self.lock:
            return self.selector.report_failure(self.context.model)


class SharedRequestPacer:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_at = {}

    def wait(self, model, interval):
        with self.lock:
            now = time.monotonic()
            scheduled = max(now, self.next_at.get(model, now))
            self.next_at[model] = scheduled + max(0, interval)
        delay = scheduled - now
        if delay > 0:
            time.sleep(delay)
