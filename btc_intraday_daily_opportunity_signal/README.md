# BTC Intraday Daily Opportunity Signal

这是一个新的 BTCUSDT 永续合约策略分支，目标是解决旧策略交易频率过低的问题。策略采用 15m 执行、4h 趋势主仓、1h 日内小仓补位。

## 当前 Cloud 候选

GetAgent temporary version:

- version_id: `0289806c-0b34-45d8-a4b6-57a9f805aa4f`
- run_id: `pbrun-98466f83d421`
- execution window: `2025-12-01 -> 2026-06-01`
- trade start: `2025-12-18`
- account return: about `+11.26%`
- account max drawdown: about `-5.78%`
- fills: `405`
- positions: `208`
- signal_output strategy-basis return: about `+22.51%`

注意：该 run 的 `metrics_output.total_return_pct` 顶层字段仍被 GetAgent/Nautilus engine 扁平字段错误覆盖，显示为约 `0.0269%`。真实权益曲线、`account_total_return_pct`、`account_max_drawdown_pct` 和 `signal_output.metrics` 更能反映本轮结果。后续如果要发布，需要继续处理平台卡片展示口径。

## 本地研究脚本

- `scripts/search_fast_daily_opportunity.py`: 搜索纯 15m/1h 日内高频模型。结论是强制每天开仓的纯日内模型扣 taker fee 后多数为负。
- `scripts/quick_hybrid_test.py`: 搜索趋势主仓 + 1h 小仓补位。当前选中结构来自这个脚本。

## GetAgent 包

可提交包位于：

`getagent_playbook/`

本地验证：

```powershell
python C:\Users\wuchuxuan\.codex\skills\getagent\scripts\validate.py btc_intraday_daily_opportunity_signal/getagent_playbook
```

预期：

```text
Validation PASSED
```
