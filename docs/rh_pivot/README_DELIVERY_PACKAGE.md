# RH LP-Bot 增量转向交付包 v1.1

日期：2026-09-07。

## 使用顺序

先阅读 `PRD_RH_LP_Bot_v1.1_CN.md` 的 §0–§6，确认工程、授权与资金政策边界；随后将 `AGENT_START_AND_TASKS_CN.md` 中的主指令交给现有项目主控Agent，先执行RH-00，不直接开启live。

## 包内文件

| 文件 | 用途 |
|---|---|
| `PRD_RH_LP_Bot_v1.1_CN.md` | 完整PRD：真实工程映射、三桶政策、数据／策略／风控／会计／执行、任务包、60项验收、25组来源 |
| `AGENT_START_AND_TASKS_CN.md` | 可直接粘贴的第一条任务指令、分包纪律、报告格式 |
| `config.rh.shadow.example.toml` | 待实现的READONLY／SHADOW配置契约；不是旧程序可直接运行的live配置 |
| `ACCEPTANCE_FIXTURES_SYNTHETIC.json` | 股币乘数、USDG比价、PnL、资本冲突与退出状态的合成测试样本 |
| `validate_delivery.py` | 本交付包一致性／安全默认值／合成算术检查，不访问网络、钱包或原仓库 |
| `DELIVERY_VALIDATION.json` | 此包本地检查结果；不等于用户原项目测试通过 |
| `INPUT_MANIFEST.json` | 两份原始输入的SHA-256指纹 |
| `inputs/` | 用户上传的两份原始Markdown，原样保留 |
| `RESEARCH_SCOPE.md` | 本次核对范围、未完成链上验证及资料时点 |

## 复核本包

需要Python 3.11及以上，仅使用标准库：

```bash
python3 validate_delivery.py
```

输出PASS只表示这份文档包的结构、TOML安全默认值与合成算术一致，不表示机器人已经实现、公开协议已被完整审计、真实池适合交易或具备盈利证据。

## 默认边界

真实签名／广播／密钥生成：未授权；付费服务：未授权；旧进程重启：未授权；六常量与100U旧资本规则：不变。新50/30/20政策可做明确标识的虚拟研究，但其LIVE_READINESS仍被政策冲突与未授权阻断。

主PRD引用`[B1]`与`[B2]`指原始输入，`[R01]`至`[R25]`的URL与核对范围在§27。所有代码路径均须在RH-00复核，不要把文档中的旧HEAD当成强制reset指令。
