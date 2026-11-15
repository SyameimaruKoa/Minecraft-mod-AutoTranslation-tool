import collections
import queue
import threading
import time


class PLaMoUnavailableError(RuntimeError):
    pass


def translate_dynamic_model_pool_batches(
    text_dict, workers, batch_size, translator, models, discover_models,
    label, on_progress=None, refresh_seconds=5.0, hedge_after_seconds=2.0
):
    if workers < 1 or batch_size < 1:
        raise ValueError("ワーカー数とバッチサイズは1以上にしてください")
    if refresh_seconds <= 0 or hedge_after_seconds <= 0:
        raise ValueError("監視間隔と再割当待機時間は正数にしてください")
    if not models or len(models) != len(set(models)):
        raise ValueError("起動時の翻訳モデルIDは一意である必要があります")
    if not text_dict:
        return {}

    keys = list(text_dict)
    batches = [
        {key: text_dict[key] for key in keys[index:index + batch_size]}
        for index in range(0, len(keys), batch_size)
    ]
    pending = collections.deque(
        (index, models[index % len(models)] if index < len(models) else None)
        for index in range(len(batches))
    )
    condition = threading.Condition()
    completions = queue.Queue()
    stopping = threading.Event()
    active = {}
    attempts = {}
    results = {}
    completed_batches = set()
    hedged_batches = set()
    rates = {}
    quarantined = {}
    statistics = collections.defaultdict(lambda: [0, 0.0])
    completed = 0
    started = time.monotonic()
    next_check = started
    missing_checks = 0
    discovery_failures = 0

    def take_pending(model):
        for offset, (index, preferred) in enumerate(pending):
            if preferred is None or preferred == model:
                del pending[offset]
                return index
        return None

    def model_worker(model, generation):
        while not stopping.is_set():
            with condition:
                while not stopping.is_set() and active.get(model) is generation:
                    index = take_pending(model)
                    if index is not None:
                        token = threading.Event()
                        token.set()
                        assignment = {
                            "model": model, "token": token,
                            "started": time.monotonic()
                        }
                        attempts[index] = assignment
                        break
                    condition.wait(timeout=0.2)
                else:
                    return
            began = time.monotonic()
            try:
                translated = translator(
                    batches[index], model,
                    lambda: token.is_set() and not stopping.is_set()
                )
                if not isinstance(translated, dict):
                    raise ValueError(f"{label}の翻訳結果は辞書である必要があります")
                completions.put((index, assignment, translated, None, time.monotonic() - began))
            except Exception as error:
                completions.put((index, assignment, None, error, time.monotonic() - began))
                return

    def reconcile(discovered):
        if not isinstance(discovered, (list, tuple)):
            raise RuntimeError("LM Linkの動的モデル一覧が不正です")
        if len(discovered) != len(set(discovered)):
            raise RuntimeError("LM LinkモデルIDが重複しています")
        with condition:
            previous = set(active)
            current = set(discovered)
            removed = previous - current
            added = [model for model in discovered if model not in active]
            for position, (index, preferred) in enumerate(pending):
                if preferred is not None and preferred not in current:
                    pending[position] = (index, None)
            for model in removed:
                del active[model]
            for index, assignment in list(attempts.items()):
                if assignment["model"] in removed:
                    assignment["token"].clear()
                    del attempts[index]
                    if index not in completed_batches:
                        pending.appendleft((index, None))
            for model in added:
                generation = object()
                active[model] = generation
                for slot in range(workers):
                    thread = threading.Thread(
                        target=model_worker, args=(model, generation),
                        name=f"plamo-{model}-{slot}", daemon=True
                    )
                    thread.start()
            condition.notify_all()
        if added:
            print(f"情報: 翻訳用PLaMoを追加: {', '.join(added)}", flush=True)
        if removed:
            print(
                f"警告: 翻訳用PLaMoを除外し未完了分を再割当: {', '.join(sorted(removed))}",
                flush=True
            )

    def refresh():
        nonlocal next_check, missing_checks, discovery_failures
        try:
            discovered = discover_models()
            current = time.monotonic()
            for model in list(quarantined):
                if model not in discovered or quarantined[model] <= current:
                    del quarantined[model]
            eligible = [
                model for model in discovered if model not in quarantined
            ]
            reconcile(eligible)
            discovery_failures = 0
        except (OSError, RuntimeError, ValueError) as error:
            discovery_failures += 1
            if discovery_failures == 1:
                print(f"警告: LM Linkのモデル一覧取得に失敗、再確認します: {error}", flush=True)
            if discovery_failures >= 3:
                raise RuntimeError("翻訳中のLM Linkモデル一覧を確認できません") from error
            next_check = time.monotonic() + refresh_seconds
            return
        missing_checks = missing_checks + 1 if not eligible else 0
        if missing_checks >= 2:
            raise RuntimeError(
                "稼働中の翻訳用PLaMoが0台になったため停止します。"
                "保存済みの翻訳は次回実行時に再利用できます"
            )
        next_check = time.monotonic() + refresh_seconds

    def hedge_slow_tail():
        if pending or len(active) < 2 or not rates:
            return
        fastest = min(
            (model for model in rates if model in active),
            key=lambda model: rates[model], default=None
        )
        if fastest is None:
            return
        busy = sum(
            assignment["model"] == fastest for assignment in attempts.values()
        )
        if busy >= workers:
            return
        for index, assignment in list(attempts.items()):
            if assignment["model"] == fastest or index in hedged_batches:
                continue
            threshold = max(
                hedge_after_seconds,
                rates[fastest] * len(batches[index]) * 2.5
            )
            if time.monotonic() - assignment["started"] < threshold:
                continue
            assignment["token"].clear()
            del attempts[index]
            hedged_batches.add(index)
            pending.appendleft((index, fastest))
            print(
                f"情報: 遅延中の{label}バッチを{fastest}へ再割当",
                flush=True
            )
            condition.notify_all()
            return

    try:
        refresh()
        while len(completed_batches) < len(batches):
            with condition:
                hedge_slow_tail()
            try:
                wait = max(0.001, min(0.2, next_check - time.monotonic()))
                index, assignment, translated, error, duration = completions.get(timeout=wait)
            except queue.Empty:
                if time.monotonic() >= next_check:
                    refresh()
                continue
            with condition:
                if attempts.get(index) is not assignment:
                    continue
            if error is not None:
                if isinstance(error, PLaMoUnavailableError):
                    model = assignment["model"]
                    quarantined[model] = time.monotonic() + 30
                    print(
                        f"警告: {label} [{model}] の通信に失敗。"
                        "残存モデルへ処理を引き継ぎます",
                        flush=True
                    )
                    reconcile([
                        current for current in active if current != model
                    ])
                    refresh()
                    continue
                refresh()
                with condition:
                    if attempts.get(index) is not assignment:
                        continue
                    del attempts[index]
                    assignment["token"].clear()
                    condition.notify_all()
                raise error
            with condition:
                del attempts[index]
                assignment["token"].clear()
                condition.notify_all()
            completed_batches.add(index)
            model = assignment["model"]
            results.update({
                key: translated[key] for key in batches[index] if key in translated
            })
            count = len(batches[index])
            completed += count
            statistics[model][0] += count
            statistics[model][1] += duration
            sample = duration / count
            rates[model] = sample if model not in rates else rates[model] * 0.7 + sample * 0.3
            remaining = max(0, int(
                (time.monotonic() - started) / completed * (len(keys) - completed)
            ))
            eta = f"{remaining}秒" if remaining < 60 else f"{remaining // 60}分{remaining % 60}秒"
            print(
                f"  進捗: {completed}/{len(keys)} ({completed / len(keys) * 100:.1f}%) "
                f"- 残り予想: {eta} - 使用中: {label} [{model}]",
                flush=True
            )
            if on_progress is not None:
                on_progress(completed, len(keys))
            if time.monotonic() >= next_check:
                refresh()
        for model, (count, seconds) in statistics.items():
            print(
                f"情報: {label} [{model}] {count}項目 / {seconds:.1f}秒（推論時間の合計）",
                flush=True
            )
    finally:
        stopping.set()
        with condition:
            for assignment in attempts.values():
                assignment["token"].clear()
            condition.notify_all()
    return {key: results[key] for key in keys if key in results}
