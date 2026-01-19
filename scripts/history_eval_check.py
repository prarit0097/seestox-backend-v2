import json
import os
from pathlib import Path


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "manage.py").exists():
            return parent
    return None


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.getenv("SEESTOX_PREDICTION_HISTORY_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / "prediction_history.json")
    repo_root = _find_repo_root()
    if repo_root:
        candidates.append(repo_root / "prediction_history.json")
        candidates.append(repo_root / "core_engine" / "prediction_history.json")
        candidates.append(repo_root / "core_engine" / "ml_engine" / "prediction_history.json")
    return candidates


def _load_history(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    records: list[dict] = []
    if isinstance(data, list):
        records = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        records.append(item)
    return records


def _select_path() -> Path | None:
    for candidate in _candidate_paths():
        if candidate.exists():
            return candidate
    return None


def _has_expected_range(record: dict) -> bool:
    expected = record.get("expected_range")
    if isinstance(expected, dict) and expected.get("low") is not None and expected.get("high") is not None:
        return True
    prediction = record.get("prediction")
    return isinstance(prediction, dict) and prediction.get("low") is not None and prediction.get("high") is not None


def _has_actual_close(record: dict) -> bool:
    return (
        record.get("actual_close") is not None
        or record.get("close") is not None
        or record.get("actual") is not None
    )


def main() -> int:
    path = _select_path()
    if not path:
        print("history_path=None")
        print("total_flat=0 evaluated_true=0 has_expected_range=0 has_prediction_lowhigh=0 has_actual_close=0")
        return 0

    records = _load_history(path)
    total = len(records)
    evaluated_true = sum(1 for r in records if r.get("evaluated") is True)
    has_expected_range = sum(1 for r in records if _has_expected_range(r))
    has_prediction_lowhigh = sum(
        1 for r in records
        if isinstance(r.get("prediction"), dict)
        and r.get("prediction", {}).get("low") is not None
        and r.get("prediction", {}).get("high") is not None
    )
    has_actual_close = sum(1 for r in records if _has_actual_close(r))

    print(f"history_path={path}")
    print(
        f"total_flat={total} evaluated_true={evaluated_true} "
        f"has_expected_range={has_expected_range} has_prediction_lowhigh={has_prediction_lowhigh} "
        f"has_actual_close={has_actual_close}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
