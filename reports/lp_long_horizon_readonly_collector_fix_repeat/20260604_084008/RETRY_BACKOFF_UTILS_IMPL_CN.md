# Stage D — Retry/Backoff/Abort 工具实现 (Retry/Backoff/Abort Utils Implementation)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`

## 0. 实现文件

- `scripts/lp_long_horizon/__init__.py` — package marker
- `scripts/lp_long_horizon/utils/__init__.py` — utils package marker
- `scripts/lp_long_horizon/utils/retry.py` — retry/backoff/timeout/429 helpers
- `scripts/lp_long_horizon/utils/abort.py` — AbortController + ErrorRateMonitor + AbortError

## 1. retry.py API

```python
retry_with_backoff(fn, *, max_retries=3, base_delay_s=1.0,
                   backoff_factor=2.0, is_retryable=None,
                   sleep_fn=time.sleep) -> T
```

- 默认 3 retries (4 attempts total)
- exponential backoff: 1s, 2s, 4s
- 默认重试所有 exception (callers 可 narrow)
- final 失败时 re-raise original exception

```python
classify_429(exc) -> bool
```

- 检查 `exc.status_code == 429` / `exc.code == 429` / `"429" in str(exc)` /
  `"too many requests"` / `"rate limit"`
- 返回 True 表示是 429 / rate-limit 错误

```python
with_timeout(fn, *, timeout_s) -> T
```

- 用 SIGALRM 实现 (POSIX only)
- 超过 timeout 抛 `TimeoutError_` (自定义, 不与 builtin TimeoutError 冲突)

## 2. abort.py API

```python
class AbortError(Exception):
    """raised by AbortController when any abort condition fires"""

class ErrorRateMonitor:
    def __init__(self, *, threshold_pct=20.0, window=50): ...
    def record_ok() / record_error()
    @property error_rate_pct, errors, total
    def should_abort() -> bool

class AbortController:
    def __init__(self, *, error_rate_monitor=None, max_429_streak=5): ...
    def record_429() / record_429_cleared() / record_ok() / record_error()
    def record_write_failure(reason)
    def record_safety_self_check_failure(reason)
    def record_banned_token(token)
    def check_abort() -> None  # raise AbortError if any condition fires
    def summary() -> dict
```

5 类 abort conditions (per final freeze long_run_safety_gates):
1. `consecutive_429` (5 连发)
2. `error_rate` (>= 20%)
3. `write_failure`
4. `safety_self_check_failure`
5. `banned_token_detected`

## 3. safety check (静态)

- [x] retry.py 0 banned token
- [x] abort.py 0 banned token (in real code; tuple / docstring exempt)
- [x] 没有 wallet / signer / tx / mutation 方法
- [x] 没有 add_liquidity / remove_liquidity / swap / collect_fee / approve / mint
- [x] 没有 bridge (wormhole / mayan / portal)
- [x] 没有 production 路径
- [x] 没有 shadow 路径
- [x] 没有 daemon / cron / systemd

## 4. 单元测试覆盖 (后续 Stage L)

- `test_retry_with_backoff_succeeds_after_2_failures`
- `test_retry_with_backoff_gives_up_after_max_retries`
- `test_retry_with_backoff_respects_is_retryable`
- `test_classify_429_various_exc_shapes`
- `test_classify_429_returns_false_for_non_429`
- `test_with_timeout_raises_on_exceed`
- `test_with_timeout_returns_quickly_when_done`
- `test_error_rate_monitor_under_threshold`
- `test_error_rate_monitor_at_or_above_threshold`
- `test_error_rate_monitor_window_slides`
- `test_abort_controller_consecutive_429`
- `test_abort_controller_error_rate`
- `test_abort_controller_write_failure`
- `test_abort_controller_safety_self_check`
- `test_abort_controller_banned_token`
- `test_abort_controller_idempotent`

## 5. 结论

retry / backoff / timeout / 429 / abort / error_rate_monitor 全部实装.
5 类 abort condition 覆盖. 不引入网络 / wallet / tx. Stage D 通过.
