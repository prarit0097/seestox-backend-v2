import json
import os
import sys

from core_engine.ml_engine.expected_range.dataset_builder import build_expected_range_dataset
from core_engine.ml_engine.scheduler.daily_scheduler import run_daily_ml_cycle
from core_engine.prediction_history import load_history_any


def _compute_evaluated_hit_rate() -> tuple[float, int]:
    history, _, _ = load_history_any()
    evaluated_total = 0
    inside_range = 0

    for record in history:
        if not isinstance(record, dict):
            continue
        expected = record.get("expected_range")
        actual_close = record.get("actual_close")
        if not isinstance(expected, dict):
            continue
        if expected.get("low") is None or expected.get("high") is None:
            continue
        if actual_close is None:
            continue
        try:
            low = float(expected.get("low"))
            high = float(expected.get("high"))
            actual = float(actual_close)
        except Exception:
            continue
        evaluated_total += 1
        if low <= actual <= high:
            inside_range += 1

    hit_rate = (inside_range / evaluated_total) if evaluated_total else 0.0
    return hit_rate, evaluated_total


def _main() -> int:
    try:
        (
            X,
            y_low,
            y_high,
            expected_lows,
            expected_highs,
            actual_closes,
        ) = build_expected_range_dataset()

        print(
            "dataset_size=%s y_low=%s y_high=%s expected_lows=%s expected_highs=%s actual_closes=%s"
            % (
                len(X),
                len(y_low),
                len(y_high),
                len(expected_lows),
                len(expected_highs),
                len(actual_closes),
            )
        )

        report = run_daily_ml_cycle()
        steps = report.get("steps", {})
        required_keys = [
            "evaluation",
            "aggregation",
            "bias_learning",
            "training",
            "scoring",
            "champion",
        ]
        missing = [key for key in required_keys if key not in steps]
        if missing:
            print("missing_keys=%s" % missing)
            return 1

        hit_rate, evaluated_total = _compute_evaluated_hit_rate()
        if evaluated_total > 0 and not (0.0 <= hit_rate <= 1.0):
            print("invalid_hit_rate=%s evaluated_total=%s" % (hit_rate, evaluated_total))
            return 1

        champion_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "core_engine",
            "ml_engine",
            "expected_range",
            "champion.json",
        )
        champion_path = os.path.normpath(champion_path)
        if os.path.exists(champion_path):
            try:
                with open(champion_path, "r") as handle:
                    data = json.load(handle)
                print("champion_json=%s" % data)
            except Exception as exc:
                print("champion_json_read_failed=%s" % exc)
                return 1

        print("ml_cycle_keys=OK")
        return 0
    except Exception as exc:
        print("smoke_test_failed=%s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
