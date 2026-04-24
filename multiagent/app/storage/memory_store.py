from copy import deepcopy
from typing import Any


TASK_STORE: dict[str, dict[str, Any]] = {}


def save_task(task_id: str, state: dict[str, Any]) -> None:
    TASK_STORE[task_id] = deepcopy(state)


def get_task(task_id: str) -> dict[str, Any] | None:
    state = TASK_STORE.get(task_id)
    if state is None:
        return None
    return deepcopy(state)
