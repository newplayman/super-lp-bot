# RH-09a：跨规模一致性审计（专杀「精度类静默错误」）

## 背景（源自今天第五个 bug 的教训）

`reports/rh_pivot/20260907T124500Z/COST_MODEL_PRICE_SCALE_BUG.md`：装配器把 `sqrtPriceX96²` 的**原始比值**当归一价格传给成本模型，18/6 精度对差 10¹²，换腿成本高估 **940 倍**，把一个 NetCover 2.79 的池判成 0.028「不可行」。

**它比今天另外四个精度陷阱都危险**：那四个给出荒谬值（1e77、0.000000、算成 0），一眼可见；这条给出的 $4.70 **看起来完全合理**，只有在三个仓位规模上对比才露馅。

教训：**任何跨精度边界的数值传递都必须有跨规模一致性测试；单点验证抓不住比例错误。**

本包把这条教训做成可复用的审计工具，并对全部 RH 模块系统排查。

## 只新建两个文件

1. `scripts/lp_rh_scale_audit_v1_readonly.py`（≤280 行）
   - `scale_invariance_check(fn, *, base_kwargs, scale_key: str, scales: Sequence[Decimal], expected: str) -> dict`：
     对 `fn` 在多个规模下求值，`expected` 取 `"LINEAR"`（结果应与规模成正比）、`"CONSTANT"`（结果应不随规模变）、`"SUBLINEAR"`（增速慢于规模，如含价格冲击的成本占比）。
     返回 `{"scales", "values", "ratios", "expected", "verdict": "OK"|"VIOLATION", "detail"}`。
     - `LINEAR`：`value/scale` 在各点相对偏差 <5% 才 OK。
     - `CONSTANT`：各点相对偏差 <5%。
     - `SUBLINEAR`：`value/scale` 单调不减但最大/最小 <5 倍。
     **任一点为 `None` → `verdict="INPUTS_UNAVAILABLE"`，不得当 0 参与比较。**
   - `decimals_roundtrip_check(*, sqrt_price_x96: int, dec0: int, dec1: int) -> dict`：把归一价格反算回 raw 比值，验证 `raw * 10**dec0 / 10**dec1 == human`（Decimal 精确）。返回 `{"raw","human","ratio","expected_ratio": 10**(dec0-dec1), "ok": bool}`。**这条能直接抓住本次 bug。**
   - `audit_module_prices(module_name: str, source: str) -> list[dict]`：静态扫描源码，找出所有 `(sqrt_price_x96 / 2.0 ** 96) ** 2` 或等价写法，检查**同一表达式所在行的上下 5 行内是否出现 `10 ** dec0` / `10 ** d0` 之类的精度缩放**。未出现 → 报 `{"line", "snippet", "risk": "RAW_RATIO_USED_AS_PRICE"}`。**这是启发式，可能误报，返回值须标 `heuristic: True`。**
   - `audit_all(scripts_dir) -> dict`：对 `scripts/lp_rh_*.py` 全部跑 `audit_module_prices`，汇总。
   - `main()`：`--scripts-dir --out`，不联网、不写活库。
2. `tests/test_lp_rh_scale_audit_v1_readonly.py`（≤280 行，≥18 测试）
   - **重现本次 bug**：构造两个函数，一个用 raw ratio、一个用归一价格，调 `scale_invariance_check` 检查「成本占仓位比例」，**用 raw 的那个必须 `VIOLATION`，用归一的必须 `OK`**。
   - `decimals_roundtrip_check`：`sqrt_price_x96=3953938817749275760872870, dec0=18, dec1=6` → `ratio == 10**12`、`human` 落在 2490–2491、`ok is True`；把 `dec1` 误设为 18 → `ratio == 1`、与真实池价不符。
   - `LINEAR` / `CONSTANT` / `SUBLINEAR` 三种期望各两例（一个 OK 一个 VIOLATION）。
   - 某点返回 `None` → `verdict == "INPUTS_UNAVAILABLE"`，**断言不是 VIOLATION 也不是 OK**。
   - `audit_module_prices`：喂一段含 `(sqrt_price_x96 / 2.0 ** 96) ** 2` 且**无**精度缩放的源码 → 报 `RAW_RATIO_USED_AS_PRICE`；喂含缩放的 → 不报。断言返回项含 `heuristic: True`。
   - **真实回归**：对当前仓库的 `scripts/lp_rh_netcover_inputs_v1_readonly.py`（已修复）跑 `audit_module_prices`，断言**不再**报 `RAW_RATIO_USED_AS_PRICE`。
   - 对 `scripts/lp_rh_collector_v1_readonly.py`（含 `compute_price_human`，有缩放）同样不报。

## 不许动
不改任何现有脚本/测试；不联网；不写活库（采集器正在写）。不要用 TaskCreate/TaskUpdate。单次 Write ≤120 行，写完 `ast.parse` 自检。

## 验收
`pytest tests/test_lp_rh_scale_audit_v1_readonly.py -q` 全绿且 ≥18；全量 0 failed / 14 skipped；`git diff --stat` 为空。
