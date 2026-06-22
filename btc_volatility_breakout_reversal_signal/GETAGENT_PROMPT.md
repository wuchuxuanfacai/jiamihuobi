# Fresh Agent Prompt

请基于这个 GitHub 仓库复现、校验并构建 GetAgent Playbook：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

目标目录：

```text
btc_volatility_breakout_reversal_signal/
```

目标 GetAgent package：

```text
btc_volatility_breakout_reversal_signal/getagent_playbook/
```

策略名称：

```text
BTC Volatility Breakout Reversal Signal
```

这是一个独立新策略，不要使用旧的 `btc_intraday_regime_rotation_signal`
冠军版，也不要把它改回 short-only HTF direction 模型。

请先阅读：

```text
btc_volatility_breakout_reversal_signal/README.md
btc_volatility_breakout_reversal_signal/getagent_playbook/README.md
btc_volatility_breakout_reversal_signal/getagent_playbook/manifest.yaml
btc_volatility_breakout_reversal_signal/getagent_playbook/backtest.yaml
btc_volatility_breakout_reversal_signal/getagent_playbook/src/main.py
btc_volatility_breakout_reversal_signal/getagent_playbook/src/features.py
btc_volatility_breakout_reversal_signal/getagent_playbook/src/decision_logic.py
btc_volatility_breakout_reversal_signal/getagent_playbook/src/strategy.py
```

核心逻辑：

1. BTCUSDT 永续合约。
2. 使用 15m K 线作为回测和执行 feed。
3. 直接在 15m 决策层计算趋势、突破、回撤和波动率。
4. 策略包含 long breakout、short breakdown、long pullback、short rebound 四个分支。
5. 仓位由 realized volatility 缩放，并由 max_effective_exposure 限制。
6. 使用 `_target_position_qty` 跟踪目标仓位，避免重复叠仓。
7. 保持 `backtest_support: full`。
8. 保持 `execution_mode: follow_trade`。
9. 不引入 requests、ccxt、DuckDB、API key 或交易所私有 SDK。
10. 源码顶部保留 `positions = []` 只是为了避免 Studio authoring runtime 自动改写时出现 `name 'positions' is not defined`。

运行本地校验：

```bash
python C:\Users\wuchuxuan\.codex\skills\getagent\scripts\validate.py btc_volatility_breakout_reversal_signal/getagent_playbook
```

必须看到：

```text
Validation PASSED
```

然后上传到 GetAgent Cloud 并运行 Cloud backtest。最终汇报必须诚实区分：

```text
1. GetAgent Validation result
2. GetAgent Cloud completed official result
3. failed run 或 signal_output 泄出的指标不能当最终官方证据
```

当前已知 completed Cloud 证据：

```text
run_id: pbrun-845a8c4e34f4
version_id: 84133fdb-a294-4c8f-b3c7-dad209c7a30e
account_total_return_pct: +3.6795%
account_max_drawdown_pct: -3.8193%
fills: 17
positions: 8
win_rate: 87.5%
profit_factor: 9.1336
window: 2025-12-18 -> 2026-06-01
```
