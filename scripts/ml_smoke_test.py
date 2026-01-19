import sys

from core_engine.ml_engine.expected_range.dataset_builder import build_expected_range_dataset
from core_engine.ml_engine.scheduler.daily_scheduler import run_daily_ml_cycle


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

        print("ml_cycle_keys=OK")
        return 0
    except Exception as exc:
        print("smoke_test_failed=%s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
