# Fresh Agent Prompt

请基于这个 GitHub 仓库复现、校验并构建 GetAgent Playbook：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

目标目录：

```text
btc_intraday_regime_rotation_signal/
```

目标 GetAgent package：

```text
btc_intraday_regime_rotation_signal/getagent_playbook/
```

策略名称：

```text
BTC HTF Direction 15m Execution Signal
```

这是一个完整 GetAgent Playbook，不是单文件 Python 策略。不要用 GitHub 单文件源码导入方式，不要把它改写成独立脚本。必须保留目录结构：

```text
getagent_playbook/
  README.md
  manifest.yaml
  backtest.yaml
  src/main.py
  src/features.py
  src/decision_logic.py
  src/strategy.py
```

请先阅读：

```text
btc_intraday_regime_rotation_signal/README.md
btc_intraday_regime_rotation_signal/getagent_playbook/README.md
btc_intraday_regime_rotation_signal/getagent_playbook/manifest.yaml
btc_intraday_regime_rotation_signal/getagent_playbook/backtest.yaml
btc_intraday_regime_rotation_signal/getagent_playbook/src/main.py
btc_intraday_regime_rotation_signal/getagent_playbook/src/features.py
btc_intraday_regime_rotation_signal/getagent_playbook/src/decision_logic.py
btc_intraday_regime_rotation_signal/getagent_playbook/src/strategy.py
```

核心策略逻辑：

1. BTCUSDT 永续合约。
2. 使用 15m K 线作为回测和执行 feed。
3. 不让 15m 噪声直接决定方向。
4. 在真实 UTC 4h 边界从 15m bars 中抽取决策 close，构造高一级方向。
5. 当前 Cloud 胜出版为选择性空头趋势再入场。
6. long path 已关闭：`max_long_weight: 0.00`，`long_floor_cap: 0.00`。
7. short trend base 是主要收益来源。
8. range component 只保留极小、严格过滤的辅助分支，不用于强制每天交易。
9. 使用 `_target_position_qty` 跟踪目标仓位，避免重复叠仓。
10. 使用 `max_effective_exposure: 2.36` 控制杠杆后名义敞口。
11. 保持 `backtest_support: full`。
12. 保持 `execution_mode: follow_trade`。
13. 不引入 requests、ccxt、DuckDB、API key 或交易所私有 SDK。
14. 不读取平台真实持仓列表。源码顶部保留 `positions = []` 只是为了避免 authoring runtime 自动改写时出现 `name 'positions' is not defined`。

manifest.yaml / backtest.yaml 中必须确认这些关键字段：

```yaml
timeframe: "15m"
htf_bars_per_decision: 16
weight_scale: 1.75
max_effective_exposure: 2.36
max_short_weight: 1.00
max_long_weight: 0.00
long_floor_cap: 0.00
range_mr_cap: 0.02
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
python C:\Users\wuchuxuan\.codex\skills\getagent\scripts\validate.py btc_intraday_regime_rotation_signal/getagent_playbook
```

必须看到：

```text
Validation PASSED
```

然后上传到 GetAgent Cloud 并运行 Cloud backtest。

已知最终 completed Cloud 证据：

```text
run_id: pbrun-f60c597831b0
version_id: e0c92319-8fb3-47f4-b21c-d9d43f03944f
status: completed
account_total_return_pct: +7.2109%
account_max_drawdown_pct: -5.9878%
fills: 20
positions: 10
win_rate: 50%
profit_factor: 2.228
window: 2025-12-18 -> 2026-06-01
```

注意：如果某次 Cloud run 显示 failed，但 signal_output 已产生结果，仍不能当作最终官方证据。必须重跑直到 status=completed。最终汇报必须诚实区分：

```text
1. local frozen research metrics
2. GetAgent Validation result
3. GetAgent Cloud completed official result
```
