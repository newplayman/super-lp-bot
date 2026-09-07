# 给执行 Agent 的首条总任务与分包纪律

任务名：`LP_BOT_RH_INCREMENTAL_PIVOT_V1_1`

## 1. 可直接粘贴的主指令

```text
你接手的是已经有大量研究代码的LP-bot，不是空仓库。目标：在现有工程基础上，新增Robinhood Chain三资金桶研究／策略支线；先证明小资金经济可行性与退出能力，再申请真实资金权限。

先完整阅读本交付包：
1. inputs/PROJECT_STATE_AND_ARCHITECTURE_20260907_CN.md
2. inputs/Robinhood_Chain_LP_Bot_50_30_20_全面转向设计文档_v1.0.md
3. PRD_RH_LP_Bot_v1.1_CN.md
4. 本任务文件

版本关系：v1.1对v1.0的变更以D01–D14和实际工程基线为准。仓库已有RISK_INVARIANTS、PRD v2.1与操作权限仍有效；发现冲突必须显式报告，不能自行选择更宽规则。

唯一预期活仓库：/opt/lpbot/lp-bot-v3-origin-check
文档中的预期HEAD：1e1d9bd
预期分支：feat/prd-v2.1-m0-shadow
这些是待复核信息，不是让你reset到这个commit的指令。

第一包只完成RH-00：
A. 只读复核HEAD、分支、未提交改动、保护进程、实际Python入口与依赖；不得重启任何原进程。
B. 建立当前文件→字段生产者→存储writer→consumer→终闸→测试的映射。
C. 使用SQLite一致性备份诊断factory_registry_probe_incomplete；不对活库执行VACUUM，不直接cp活库和WAL。
D. 按“真实经济失败／输入不可用／协议不支持／政策阻挡”拆分零候选原因。
E. 重现至少一个已知可计算的阳性对照和一个失败样本；保留原始请求／响应、输入和退出码。
F. 核对Go层冻结、Python＋SQLite活跃的真实边界；不得重建Go/Rust/PostgreSQL/NATS架构。
G. 输出最小文件改动计划、测试基线、未授权操作、RH-01的确定性输入与blocker。

首包输出到 reports/rh_pivot/<UTC_RUN_ID>/：
P0_EXISTING_CODE_MAP.md
BASELINE_RAW.log
FIELD_PRODUCER_MAP.md
LEGACY_FAILURE_AUTOPSY.json
PERMISSION_MATRIX.md
VERDICT.json

第一包完成前禁止大规模重构，禁止删除／削弱旧测试。

保留以下硬边界：
- 不生成生产私钥、不读旧keystore、不签名、不广播、不转钱。
- LIVE_TRADING保持false，不enable任何旧executor/sidecar/canary。
- 不改六常量：0.7、1.0、1.5、0.0005、0.001、LVR模型系数0.50，按对应名称核对。
- 不改现有100U／单仓50–60U／reserve40U／日亏5U／总回撤10U资金规则。
- 新三桶仅为SHADOW_SCENARIO政策；LIVE_READINESS必须保留CAPITAL_POLICY_CONFLICT或NOT_AUTHORIZED。
- 不重启／kill原paper、scanner、watchdog、断链记录器。
- 不碰封存 /opt/lpbot/lp-bot-v3 和冻结 scripts/lp_long_horizon/。
- 不接付费服务，不git push，不并发两个写入worker操作同一仓库。

允许范围内的只读脚本使用lp_<domain>_<version>_readonly.py和配对测试。研究代码不得import signer／公网广播能力。

不得把缺失输入填0，不得用网页APR替代净收益，不得把旧paper收益当全成本实盘证据，不得用降低阈值解决accepted=0。

实际代码与文档不一致时先报告差异，保留现场，继续做安全可完成的只读诊断；不要reset、checkout覆盖脏改动或重启进程去“对齐”文档。

每包必须输出PASS/WARN/FAIL及原始证据；“没有运行”不得写PASS。生产未授权必须明确显示，与文档／测试PASS分开。
```

## 2. RH-00 安全核对建议

下列仅为已有工程的只读示例；先确认路径存在，不会自动切分支或改代码：

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
pwd
git rev-parse --show-toplevel
git rev-parse HEAD
git branch --show-current
git status --short
git diff --stat
# 只读取原记录，不把多行JSON直接当单个JSON对象解析。
tail -n 3 /opt/lpbot/TPF_WATCH.jsonl
```

进程以当前只读快照为准，旧PID仅为定位线索。不要执行启动／停止命令；不要把含敏感关键词的审计命令误认成真实广播，也不要为消除宿主敏感测试误报而削弱真正的隔离测试。

SQLite备份要放在新报告目录，不能覆盖旧库或旧报告。应使用项目已有安全备份工具；没有工具时使用Python标准库`sqlite3`的只读source连接与`backup()`，并验证目标新文件、available disk与source指纹。备份成功后立即使用固定目标做全部新旧比较，不能每次重新拉取移动的活库。

运行全量测试需遵守现有资源和任务纪律，保存原始输出与所有skip原因。测试通过数量可以与文档不同，但必须解释新增、环境跳过与真实退化，不能为了吻合3109而删测试。

## 3. 后续任务包分派表

| 包 | 前置 | 实施目标 | 明确不做 |
|---|---|---|---|
| RH-01 | RH-00基线清楚 | RPC能力、资产schema、V3/V4身份、attestation | 不根据symbol／网页地址直接交易 |
| RH-02 | RH-01契约稳定 | 有限采集、独立SQLite、session／oracle／health writer-reader | 不无限全链扫描、不重启旧daemon |
| RH-03 | 数据可复现 | NetCover装配、三桶情景、终闸合取、零候选解释 | 不放宽六常量，不实际改变旧资本授权 |
| RH-04 | RH-03＋基本数据 | 单CORE Shadow、NAV／HODL／fee会计、数学差分 | 不为完善功能跳过净收益验证 |
| RH-05 | RH-02／03／04 | 股票schema、乘数、假日／halt／pause、退出quote | 不把AMC热度或oracle折价当无风险套利 |
| RH-06 | 会计与退出模型可用 | MEME可选审计／Shadow | 不强制20%部署，不制造虚假APR |
| RH-07 | 有实质经济候选＋开发权限 | 受限RH执行构造、本地fork、nonce与退出恢复 | 不生成生产密钥，不广播公网交易 |
| RH-08 | 对应模块完成 | 面板、资源预算、故障注入、全回归、毕业报告 | 不把文档通过等同实盘授权 |
| RH-09 | profile毕业＋运营就绪 | Tiny Live审批请求包 | 不自动签署／解锁／加资 |

同仓库写入串行。主控可以让另一代理读取不可变副本做审计，但不能让两个worker各自改同一shared cost文件。实施工具按当前项目纪律使用`qwen-task`，只读研究按现有只读权限配置；无需为本任务恢复别的代理或客户端。

## 4. 每包标准产物目录

```text
reports/rh_pivot/<UTC_RUN_ID>/<TASK_ID>/
  SCOPE.md
  INPUT_MANIFEST.json
  CODE_MAP.md
  FIELD_PRODUCER_MAP.md         # 涉及新字段时必须
  RAW_COMMANDS.log
  RAW_TEST_OUTPUT.log
  BASE_INVARIANCE_DIFF.json     # 涉及共享模型时必须
  MUTATION_RESULTS.json        # 涉及新硬闸时必须
  ECONOMIC_RESULTS.json        # 涉及策略时必须
  PNL_RECONCILIATION.json       # 涉及头寸／费用时必须
  KNOWN_BLOCKERS.md
  VERDICT.json
```

`VERDICT.json` 至少包含：task_id、mode、repo_head、dirty_diff_hash、source_snapshot_hashes、policy/model/schema版本、tests_passed/failed/skipped、未运行测试、未批准行为、候选原因分类、签名／广播计数、下一允许任务。

对没做的检查填`NOT_RUN`，不以空数组代表“无问题”。真实source未取得时保留错误类型；容器DNS失败不能当链停机。

## 5. 配置样例的使用边界

`config.rh.shadow.example.toml`是**待实现的配置契约**，不能直接拷贝覆盖原`configs/config.live.toml`／canary，也不保证旧CLI认识这些字段。

实现新的config parser时：拒绝未知危险字段／矛盾开关；`live=false`与`capital_policy_approved=false`为不可省略的默认；把`READONLY`、`SHADOW_SCENARIO`、`LIVE_READINESS`区分。初始可以在不接钱包的前提下比较100／300／1000／3000U虚拟情景，但所有结果仍明确生产未授权。

在只读阶段，配套`ACCEPTANCE_FIXTURES_SYNTHETIC.json`仅用于预期算术和分类场景。它不是链上数据，不是执行器测试替代品，不构成收益证据。

## 6. 第一份汇报不要用这类句子糊弄

不要说“架构完整，建议继续开发”，要给出真实待改文件和具体blocker。

不要说“0候选说明无机会”，要列已计算／缺输入／未支持／政策阻挡。

不要说“全部测试通过可以开仓”，要分别给出工程、数据、经济、资金授权四个状态。

不要说“已撤池所以风险解除”，要给出LP余额、钱包风险库存、可退出报价与净值。

不要说“配置50/30/20已实现”，要证明预算原子预占、风险库存聚合与禁止跨桶借资。

**本轮优先完成一条可信的经济闭环，不以新增模块数量、代码量或APR排名作为工作完成标准。**
