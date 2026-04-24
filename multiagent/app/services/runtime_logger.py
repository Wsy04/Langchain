from datetime import datetime
from time import perf_counter
from typing import Any


def log_event(task_id: str, stage: str, message: str, **fields: Any) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    details = " ".join(
        f"{key}={_format_value(value)}"
        for key, value in fields.items()
        if value is not None
    )
    line = f"[{timestamp}] task={task_id} stage={stage} {message}"
    if details:
        line = f"{line} {details}"
    print(line, flush=True)


def start_timer() -> float:
    return perf_counter()


def elapsed_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _format_value(value: Any) -> str:
    text = str(value)
    if len(text) > 160:
        text = f"{text[:157]}..."
    return text.replace("\n", " ")
