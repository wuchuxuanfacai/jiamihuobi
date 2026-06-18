# Prompt: Use Previous Working Package Structure

请不要从零 authoring，也不要使用 GitHub 单文件源码导入。

请基于这个 GitHub 仓库中已有的、曾经能进入 GetAgent Cloud 回测的完整 Playbook 结构来构建：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

先读取这个旧的可运行包结构：

```text
btc_adaptive_short_trend_signal/getagent_playbook/
```

这个目录包含：

```text
README.md
manifest.yaml
backtest.yaml
src/main.py
src/features.py
src/decision_logic.py
src/strategy.py
```

请把它作为 working template。不要重新设计 GetAgent/Nautilus 包结构，不要重新生成持仓管理模板，不要把策略改写成单文件。

然后读取新候选的研究参数和说明：

```text
btc_selective_trend_reentry_signal/README.md
btc_selective_trend_reentry_signal/research_snapshot/reproduced_metrics.json
btc_selective_trend_reentry_signal/getagent_playbook/manifest.yaml
btc_selective_trend_reentry_signal/getagent_playbook/backtest.yaml
btc_selective_trend_reentry_signal/getagent_playbook/src/decision_logic.py
```

目标是做一个沿用旧可运行包结构的新版本：

```text
BTC Selective Trend Re-Entry Signal
```

必须保留旧 working package 的这些结构特征：

1. `backtest_support: full`
2. `execution_mode: follow_trade`
3. `follow_trade_supported: true`
4. `strategy.module: strategy`
5. `strategy.class: AdaptiveShortTrendStrategy`
6. `strategy.config_class: AdaptiveShortTrendStrategyConfig`
7. `instrument.id: BTCUSDT.BINANCE`
8. `bar_type: BTCUSDT.BINANCE-4-HOUR-LAST-EXTERNAL`
9. 使用 `getagent.data` 和 `getagent.backtest`
10. 不引入 requests、ccxt、DuckDB、API key 或交易所私有 SDK

新候选关键参数：

```yaml
weight_scale: 1.75
max_effective_exposure: 1.05
bear_on: 0.56
ret_slow_max: -0.08
ret_mid_max: -0.04
short_sma_mult: 0.98
short_target_vol: 0.35
short_floor_cap: 1.00
max_short_weight: 1.00
max_signal_weight: 1.00
long_on: 0.68
long_floor_cap: 0.10
max_long_weight: 0.10
range_mr_cap: 0.02
range_min_component: 0.00
range_z_entry: 1.50
range_trend_max: 0.30
range_bear_max: 0.30
range_vol_ceiling: 0.28
cloud_fetch_start: "2025-12-18T00:00:00Z"
cloud_trade_start: "2025-12-18T00:00:00Z"
cloud_fetch_end: "2026-06-01T00:00:00Z"
```

本地研究复现：

```bash
cd btc_selective_trend_reentry_signal
python scripts/reproduce_metrics.py
```

必须看到：

```json
"passed": true
```

本地 frozen research metrics 只是研究证据，不是 GetAgent Cloud 官方回测。

构建完成后运行：

```bash
python <getagent_skill_path>/scripts/validate.py <your_playbook_dir>
```

必须看到：

```text
Validation PASSED
```

然后上传 GetAgent Cloud backtest。

如果出现：

```text
name 'positions' is not defined
stage: authoring_runtime
artifact_ref: ""
```

说明你走错了流程：你正在让 authoring runtime 从零改写代码。请停止从零 authoring，回到 `btc_adaptive_short_trend_signal/getagent_playbook/` 这个 working template，只做最小参数替换。

