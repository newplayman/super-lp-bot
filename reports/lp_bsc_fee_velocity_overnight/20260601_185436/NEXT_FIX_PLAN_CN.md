# 下一轮修复建议

当前不建议立刻重跑完整 overnight。

## 修复建议

1. 下次启动 VPS tmux 前显式设置：

```bash
export INPUT_REPO_ROOT_OVERRIDE=/opt/lpbot/lp-bot-v3-origin-check
export REPO_ROOT_OVERRIDE=/opt/lpbot/lp-bot-v3-origin-check
```

2. 在启动 full overnight 前，先把必要输入报告复制到 VPS 的预期路径，避免 runner 依赖本地相对路径。

3. 先做 1 个 pool 的 24h smoke：

- `selected_pool_count = 8`
- `first_pool_loaded = yes`
- `eth_getLogs smoke = pass`
- 至少进入 scan pool loop

4. smoke 通过后，再允许 full overnight repeat。

5. 启动新 run 之前，先清理旧 final 留档，避免 stale final 混入新 run 的判断。
