# Prompt: Root Playbook Import

请直接把这个 GitHub 仓库根目录当作完整 GetAgent Playbook package：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

不要进入任何子目录，不要读取其它候选目录，不要从零 authoring，不要使用单文件源码导入。

仓库根目录已经包含标准 GetAgent Playbook 文件：

```text
README.md
manifest.yaml
backtest.yaml
src/main.py
src/features.py
src/decision_logic.py
src/strategy.py
```

请直接对仓库根目录执行 package validation，然后上传 Cloud backtest。

必须保持：

```yaml
backtest_support: full
execution_mode: follow_trade
follow_trade_supported: true
```

不要改写 Nautilus 策略类，不要生成新的持仓管理模板，不要新增 requests、ccxt、DuckDB、API key 或交易所私有 SDK。

本仓库根目录已经通过本地 GetAgent 校验：

```text
Validation PASSED
```

如果出现：

```text
name 'positions' is not defined
stage: authoring_runtime
artifact_ref: ""
```

说明你仍然走错流程：你在从零 authoring。请停止 authoring，直接把仓库根目录作为 Playbook package 校验和上传。

