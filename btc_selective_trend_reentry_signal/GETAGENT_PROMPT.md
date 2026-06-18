# Fresh Agent Prompt

请基于这个 GitHub 仓库复现、校验并构建一个新的 GetAgent 策略：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

目标目录：

```text
btc_selective_trend_reentry_signal/
```

目标 GetAgent package：

```text
btc_selective_trend_reentry_signal/getagent_playbook/
```

策略名称：

```text
BTC Selective Trend Re-Entry Signal
```

这是一个低换手、趋势优先、选择性再入场的 BTCUSDT 永续合约策略。核心目标是：不要为了减少空仓而强行交易，而是在趋势结构、动量、价格位置、反弹过滤和波动率同时支持时才建立目标仓位。

请先阅读这些文件：

```text
btc_selective_trend_reentry_signal/README.md
btc_selective_trend_reentry_signal/GETAGENT_PROMPT.md
btc_selective_trend_reentry_signal/getagent_playbook/README.md
btc_selective_trend_reentry_signal/getagent_playbook/manifest.yaml
btc_selective_trend_reentry_signal/getagent_playbook/backtest.yaml
btc_selective_trend_reentry_signal/getagent_playbook/src/decision_logic.py
btc_selective_trend_reentry_signal/getagent_playbook/src/features.py
btc_selective_trend_reentry_signal/getagent_playbook/src/strategy.py
btc_selective_trend_reentry_signal/getagent_playbook/src/main.py
btc_selective_trend_reentry_signal/scripts/reproduce_metrics.py
```

本地复现步骤：

```bash
cd btc_selective_trend_reentry_signal
python -m pip install -r requirements.txt
python scripts/reproduce_metrics.py
```

期望输出必须包含：

```json
"passed": true
```

冻结研究候选：

```text
source_rank = 1
weight_scale = 1.75
timeframe = 4h
```

冻结本地研究指标：

```text
validation annual_return approximately 25.36%
validation max_drawdown approximately -5.80%
locked_test annual_return approximately 119.69%
locked_test max_drawdown approximately -3.76%
```

注意：这些只是本地 frozen research metrics，不是 GetAgent Cloud 官方回测结果。最终是否采用必须看 Cloud 官方策略卡片。

策略结构：

1. 使用 BTCUSDT 永续合约。
2. 使用 4h 信号周期。
3. 使用 trend-short base 作为主要收益来源，捕捉清晰下行趋势。
4. 保留很小的 defensive long path，只在恢复结构足够干净时参与。
5. range component 只作为严格过滤和极小辅助，不负责填满所有空仓期。
6. 使用 target-position 目标仓位追踪，避免重复叠仓。
7. 使用 volatility-scaled sizing，在波动过高时自动降低仓位。
8. 使用 rebound filter，避免在强反弹阶段继续开空。
9. 使用 max_effective_exposure 控制杠杆后名义敞口。
10. 策略必须保持 backtest_support: full。
11. 策略必须保持 execution_mode: follow_trade。
12. 策略不得引入 requests、ccxt、DuckDB、API key 或交易所私有 SDK。

manifest.yaml 中必须确认这些关键字段：

```yaml
name: btc-selective-trend-reentry-signal
display_name: "BTC Selective Trend Re-Entry Signal"
version: "0.1.0"
backtest_support: full
execution_mode: follow_trade
weight_scale: 1.75
max_effective_exposure: 1.05
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

运行 GetAgent 本地校验：

```bash
python C:\Users\wuchuxuan\.codex\skills\getagent\scripts\validate.py btc_selective_trend_reentry_signal/getagent_playbook
```

必须看到：

```text
Validation PASSED
```

然后上传到 GetAgent Cloud 并运行 Cloud backtest。

Cloud 采用阈值：

```text
Total Return > +9.2%
Max Drawdown <= 6%
Complete trades not abnormally inflated
```

只有当 Cloud 官方策略卡片同时满足以上条件时，才认为这个新候选胜出。否则只保留为研究候选，不发布。

最终汇报必须诚实区分：

```text
1. local frozen research metrics
2. GetAgent Validation result
3. GetAgent Cloud official backtest result
```
