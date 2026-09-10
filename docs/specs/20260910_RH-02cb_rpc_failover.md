# RH-02cb — 采集器接主备端点（单端点刚刚造成了实际损害）

## 背景（都是实测，不用重新验证）

2026-09-10 上游端点 `rpc.mainnet.chain.robinhood.com` 大面积超时，
采集器**没有任何备用可切**，后果是 Stage A 的两个 blocker 同时恶化：

```
coverage            0.9984 -> 0.9584
fee_growth 非空率   跌破 0.99 的 key-field 阈值（读不到就写 NULL）
采样间隔            15s -> ~45s
40 轮实测成功率     37.5%
```

主脑已穷尽调研（`reports/AUDIT_rh_rpc_endpoints_20260910.md`），
chain 4663 全网**只有两个实测可用的独立端点**：

```
https://robinhood-rpc.publicnode.com   100% 成功  p50 308ms   （当前主端点）
https://rpc.ordofi.network             100% 成功  p50 681ms
```

`SINGLE_PROVIDER_NOT_ALLOWED_FOR_LIVE` 是 PRD 的 LIVE 硬前提。
它要的不是「有两个端点」，是「真的会切」。

## 要做的事

只改 `scripts/lp_rh_collector_v1_readonly.py`。

### 1. 读第二个端点

```python
RH_RPC_PRIMARY = os.environ.get(
    "RH_RPC_PRIMARY", "https://rpc.mainnet.chain.robinhood.com")
RH_RPC_SECONDARY = os.environ.get("RH_RPC_SECONDARY", "").strip()
```

**默认空串 = 不启用备用**，此时行为必须与现在**逐字相同**。
这一条由测试钉死（见测试第 1 条）。

`scripts/lp_rh_capabilities_v1_readonly.py:306` 已经在读这个变量名，
沿用它，不要另起名字。

### 2. `rpc()` 内部按序尝试

现在（约 L175）：

```python
def rpc(method, params=None, *, url: str = RH_RPC_PRIMARY,
        timeout: int = RPC_TIMEOUT_SECS) -> Tuple[Any, Any, int]:
```

改成：主端点失败（transport 异常 **或** JSON-RPC error）且配了备用时，
用备用再试一次。

**签名约束**：
- 保留 `url` 参数。**显式传了 `url` 就只用那一个，不做切换**
  （测试和单端点探测依赖这个行为）。
- 返回值仍是三元组 `(result, error, latency_ms)`，
  **不要改成四元组**——调用方不止一处，改签名会牵连一片。
- `latency_ms` 在发生切换时返回**两次尝试之和**（真实耗时，不是只算成功那次）。

「实际用了哪个端点」通过**新增一个可选的输出参数**传出，例如：

```python
def rpc(method, params=None, *, url=None, timeout=RPC_TIMEOUT_SECS,
        used: Optional[dict] = None) -> Tuple[Any, Any, int]:
    """... 若传入 used（dict），回填 used["provider"] 与 used["failover"]。"""
```

**不要用模块级可变全局变量记录当前端点**——
`scripts/lp_silent_failure_lint_v1_readonly.py` 的规则 4 专门抓这个，
而且并发下会串。

### 3. `rh_rpc_health` 记真实端点

L285 附近的写入把 `"provider"` 硬写成 `RH_RPC_PRIMARY`。
改成**这一轮实际取到数据的那个端点**。

并在 `error` 字段里，当发生过切换时**追加一条痕迹**，例如
`primary_failover:<主端点错误摘要>`，与已有的错误串用 `; ` 连接。

**切到备用绝不能是静默的**：本仓库已确认 27 例「静默假绿」，
一个悄悄降级的采集器会让人以为数据一直来自同一个源。

### 4. 两个都失败才算失败

主备都失败时，返回的 `error` 要能看出**两个都试过了**，
形如 `{"primary": {...}, "secondary": {...}}`。
现有的 DEGRADED / NORMAL 判定逻辑不要改。

## 不许动

- 不要改 `collect_once` 的整体流程、`rh_market_states` 的任何字段、
  DEGRADED/NORMAL 的判定条件。
- 不要改 `RPC_TIMEOUT_SECS`（12 秒）。若想让备用用不同超时，
  **本包不做**，留给后续。
- 不要引入重试次数、退避、熔断器等额外机制——本包只做「主失败就试备用，一次」。
- 不要碰 `scripts/lp_rh_shadow_daemon_v1_readonly.py`（另一条线正在改）。
- **不要重启或 kill 采集器进程（PID 1168725 正在生产采集）。**
  本包只改代码；是否部署由主脑与用户决定。
- **不要真的写 `reports/lp_rh/scanner.db`**；测试用内存库或 `tmp_path`。
- **不要在测试里发真实网络请求**——所有 RPC 用假函数/monkeypatch 注入。
- **不要执行任何 git 命令。**
- 单次 Write/Edit ≤150 行或 6000 字符。

## 测试（`tests/test_lp_rh_collector_v1_readonly.py`，已存在，追加）

1. **`RH_RPC_SECONDARY` 未设置时，`rpc()` 只发一次请求**
   （monkeypatch urlopen 计数），且行为与现状一致。
   **这条是向后兼容的保证，最重要。**
2. 主端点 transport 异常 + 配了备用 → 备用成功 → 返回备用的 result，
   `used["provider"]` 是备用地址，`used["failover"] is True`。
3. 主端点返回 JSON-RPC error + 配了备用 → 同样触发切换。
4. 显式传 `url=` 时**不切换**，即使配了备用（只发一次请求）。
5. 主备都失败 → `error` 里同时含两者的信息，`result is None`。
6. 发生切换时 `latency_ms` 是两次之和（不是只算成功那次）。
7. `rh_rpc_health` 行的 `provider` 等于实际取到数据的端点，
   且切换发生时 `error` 含 `primary_failover` 痕迹。
8. 主端点成功时**不发第二次请求**（备用不被无谓调用）。

## 验收标准（主脑会逐条查）

1. `python3 -m pytest tests/test_lp_rh_collector_v1_readonly.py -q` 全绿，新增 ≥8 条。
2. 全量 `python3 -m pytest tests/ -q` 通过。
3. `grep -nE "^_?[A-Z_]*(CURRENT|ACTIVE)_(RPC|PROVIDER)" scripts/lp_rh_collector_v1_readonly.py`
   **无输出**（没有引入模块级可变端点状态）。
4. 真实探测一次两个端点仍然可用（只读，不写库）：
   ```
   python3 -c "
   import importlib.util
   s=importlib.util.spec_from_file_location('c','scripts/lp_rh_collector_v1_readonly.py')
   m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
   for u in ('https://robinhood-rpc.publicnode.com','https://rpc.ordofi.network'):
       r,e,ms=m.rpc('eth_chainId', url=u); print(u, r, e, ms)
   "
   ```
   两个都应返回 `0x1237`（=4663）。把输出贴进总结。
5. `git status --short` 里只有
   `scripts/lp_rh_collector_v1_readonly.py` 和
   `tests/test_lp_rh_collector_v1_readonly.py` 被改动。
