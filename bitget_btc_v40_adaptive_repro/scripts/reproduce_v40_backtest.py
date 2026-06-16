from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


SEGMENTS = {
    "inner_validation": ("2023-07-01", "2024-06-30"),
    "outer_validation": ("2024-07-01", "2025-03-31"),
    "outer_test": ("2025-04-01", "2026-05-13"),
}


def annualized_stats(strategy_return: pd.Series) -> dict[str, float]:
    ret = strategy_return.fillna(0.0)
    equity = 10000.0 * (1.0 + ret).cumprod()
    if not equity.empty:
        equity.iloc[0] = 10000.0
    if len(equity) <= 1:
        return {
            "start_equity": 10000.0,
            "end_equity": float("nan"),
            "total_return": float("nan"),
            "annualized_return": float("nan"),
            "annualized_vol": float("nan"),
            "sharpe": float("nan"),
            "max_drawdown": float("nan"),
        }
    ann_return = float((equity.iloc[-1] / equity.iloc[0]) ** (365 / (len(equity) - 1)) - 1)
    ann_vol = float(ret.std() * np.sqrt(365))
    sharpe = ann_return / ann_vol if ann_vol and np.isfinite(ann_vol) else float("nan")
    max_drawdown = float((equity / equity.cummax() - 1.0).min())
    return {
        "start_equity": 10000.0,
        "end_equity": float(equity.iloc[-1]),
        "total_return": float(equity.iloc[-1] / 10000.0 - 1.0),
        "annualized_return": ann_return,
        "annualized_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }


def segment_stats(detail: pd.DataFrame, start: str, end: str) -> dict[str, float | int | str]:
    sub = detail.loc[(detail.index >= pd.Timestamp(start)) & (detail.index <= pd.Timestamp(end))].copy()
    stats: dict[str, float | int | str] = annualized_stats(sub["strategy_return"])
    target = sub["target_weight"].fillna(0.0)
    applied = sub["applied_weight"].fillna(0.0)
    stats.update(
        {
            "long_entries": int(((target > 0) & (target.shift(1).fillna(0.0) <= 0)).sum()),
            "short_entries": int(((target < 0) & (target.shift(1).fillna(0.0) >= 0)).sum()),
            "turnover_avg": float(target.diff().abs().fillna(target.abs()).mean()),
            "exposure_abs_avg": float(applied.abs().mean()),
            "flat_days": int((applied == 0).sum()),
            "long_days": int((applied > 0).sum()),
            "short_days": int((applied < 0).sum()),
            "start_date": str(sub.index.min().date()) if len(sub) else "",
            "end_date": str(sub.index.max().date()) if len(sub) else "",
        }
    )
    return stats


def max_abs_diff(left: dict, right: dict) -> float:
    diffs: list[float] = []
    for key, value in left.items():
        if isinstance(value, (int, float)) and key in right:
            other = right[key]
            if isinstance(other, (int, float)) and np.isfinite(float(value)) and np.isfinite(float(other)):
                diffs.append(abs(float(value) - float(other)))
    return max(diffs) if diffs else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduce frozen BTC V40 segment metrics.")
    parser.add_argument("--snapshot-dir", type=Path, default=Path(__file__).resolve().parents[1] / "research_snapshot")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "research_snapshot" / "reproduced_v40_metrics.json")
    parser.add_argument("--tolerance", type=float, default=1e-10)
    args = parser.parse_args()

    detail_path = args.snapshot_dir / "v40_best_detail.csv"
    summary_path = args.snapshot_dir / "v40_summary.json"
    detail = pd.read_csv(detail_path, parse_dates=["date"]).set_index("date").sort_index()
    reference = json.loads(summary_path.read_text(encoding="utf-8"))

    reproduced = {name: segment_stats(detail, *window) for name, window in SEGMENTS.items()}
    comparisons = {
        name: {
            "max_abs_numeric_diff_vs_reference": max_abs_diff(stats, reference["stats"][name]),
            "reference_total_return": reference["stats"][name]["total_return"],
            "reproduced_total_return": stats["total_return"],
            "reference_sharpe": reference["stats"][name]["sharpe"],
            "reproduced_sharpe": stats["sharpe"],
            "reference_max_drawdown": reference["stats"][name]["max_drawdown"],
            "reproduced_max_drawdown": stats["max_drawdown"],
        }
        for name, stats in reproduced.items()
    }
    max_diff = max(item["max_abs_numeric_diff_vs_reference"] for item in comparisons.values())
    repo_pack_root = Path(__file__).resolve().parents[1]
    result = {
        "source_detail": str(detail_path.relative_to(repo_pack_root)),
        "source_summary": str(summary_path.relative_to(repo_pack_root)),
        "segments": reproduced,
        "comparisons": comparisons,
        "max_abs_numeric_diff": max_diff,
        "tolerance": args.tolerance,
        "passed": bool(max_diff <= args.tolerance),
    }
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
