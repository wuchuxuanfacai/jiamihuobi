# Prompt

请基于这个 GitHub 仓库构建 GetAgent 策略：

```text
https://github.com/wuchuxuanfacai/jiamihuobi
```

请只使用这个目录：

```text
btc_selective_from_working_template/getagent_playbook/
```

这是从之前能进入 GetAgent Cloud 回测的 working package 复制出来的新候选。请不要从零 authoring，不要使用单文件源码导入，不要改写 GetAgent/Nautilus 包结构。

该目录必须作为完整 Playbook package 使用，包含：

```text
README.md
manifest.yaml
backtest.yaml
src/main.py
src/features.py
src/decision_logic.py
src/strategy.py
```

请直接运行 package validation：

```bash
python <getagent_skill_path>/scripts/validate.py btc_selective_from_working_template/getagent_playbook
```

必须看到：

```text
Validation PASSED
```

然后上传 GetAgent Cloud backtest。

本地研究复现：

```bash
cd btc_selective_from_working_template
python scripts/reproduce_metrics.py
```

必须看到：

```json
"passed": true
```

注意：本地 frozen research metrics 不是 GetAgent Cloud 官方回测结果。最终只以 Cloud 策略卡片为准。

