from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


SELECTED_SOURCE_RANK = 1
SELECTED_WEIGHT_SCALE = 1.40
MIN_ANNUAL_RETURN = 0.20
MAX_DRAWDOWN_ABS = 0.06


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Reproduce frozen BTC V10 short-trend headline metrics.")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=root / "research_snapshot" / "btc_short_trend_v10_scale_top120.csv",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "research_snapshot" / "reproduced_v10_short_trend_metrics.json",
    )
    args = parser.parse_args()

    rows = pd.read_csv(args.snapshot)
    selected = rows[
        (rows["source_rank"] == SELECTED_SOURCE_RANK)
        & ((rows["weight_scale"] - SELECTED_WEIGHT_SCALE).abs() < 1e-12)
    ]
    if selected.empty:
        raise SystemExit("selected v10 row not found in snapshot")
    row = selected.iloc[0].to_dict()
    checks = {
        "validation_annual_return_ok": bool(row["validation_annual_return"] >= MIN_ANNUAL_RETURN),
        "validation_max_drawdown_ok": bool(row["validation_max_drawdown"] >= -MAX_DRAWDOWN_ABS),
        "locked_test_annual_return_ok": bool(row["locked_test_annual_return"] >= MIN_ANNUAL_RETURN),
        "locked_test_max_drawdown_ok": bool(row["locked_test_max_drawdown"] >= -MAX_DRAWDOWN_ABS),
        "pass_target_flag": bool(row["pass_target"]),
    }
    passed = all(checks.values())
    result = {
        "selected": {
            "source_rank": int(row["source_rank"]),
            "weight_scale": float(row["weight_scale"]),
            "timeframe": row["timeframe"],
            "validation": {
                "annual_return": float(row["validation_annual_return"]),
                "total_return": float(row["validation_total_return"]),
                "max_drawdown": float(row["validation_max_drawdown"]),
                "sharpe": float(row["validation_sharpe"]),
            },
            "locked_test": {
                "annual_return": float(row["locked_test_annual_return"]),
                "total_return": float(row["locked_test_total_return"]),
                "max_drawdown": float(row["locked_test_max_drawdown"]),
                "sharpe": float(row["locked_test_sharpe"]),
            },
            "train": {
                "annual_return": float(row["train_annual_return"]),
                "max_drawdown": float(row["train_max_drawdown"]),
                "sharpe": float(row["train_sharpe"]),
            },
        },
        "target": {
            "min_annual_return": MIN_ANNUAL_RETURN,
            "max_drawdown_abs": MAX_DRAWDOWN_ABS,
        },
        "checks": checks,
        "passed": passed,
        "summary": (
            "validation annual "
            + _pct(float(row["validation_annual_return"]))
            + ", validation max drawdown "
            + _pct(float(row["validation_max_drawdown"]))
            + "; locked_test annual "
            + _pct(float(row["locked_test_annual_return"]))
            + ", locked_test max drawdown "
            + _pct(float(row["locked_test_max_drawdown"]))
        ),
    }
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
