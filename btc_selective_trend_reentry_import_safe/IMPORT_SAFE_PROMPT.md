# Import Safe Prompt

请使用 GitHub 仓库里的这个单文件源码构建 GetAgent 策略：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

只读取这个文件：

```text
btc_selective_trend_reentry_import_safe/btc_selective_trend_reentry_single.py
```

不要读取其它旧策略文件，不要重写成新的持仓管理模板，不要删除顶部的兼容兜底：

```python
positions = []
```

这个变量不是交易逻辑，只是为了避免 authoring_runtime 在构建阶段出现未定义变量错误。

策略名称：

```text
BTC Selective Trend Re-Entry Signal
```

策略核心：

1. BTCUSDT 永续合约。
2. 4h 周期。
3. 低换手、趋势优先、选择性再入场。
4. 空头趋势再入场是主要分支。
5. 多头只作为很小的防御恢复分支。
6. 使用波动率缩放目标仓位。
7. 使用反弹过滤，避免在强反弹时继续做空。
8. 不引入 requests、ccxt、DuckDB、API key 或交易所私有 SDK。

如果 authoring_runtime 仍然报未定义变量错误，请确认生成代码中保留了：

```python
positions = []
```

最终 Cloud 结果必须以 GetAgent 官方策略卡片为准，不要把本地研究指标说成 Cloud 官方结果。
