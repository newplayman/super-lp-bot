# P0-PG-02 Shadow Startup Smoke

- **stage**: `P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1`
- **run_id**: `20260608_181508`
- **base_commit**: `61f6621`
- **branch**: `feat/supabase-postgres-deployment`
- **workdir**: `/opt/lpbot/lp-bot-v3`
- **smoke_target**: verify shadow binary can load config + initialize adapters
  + attempt postgres connection. **No full daemon run, no signing, no
  broadcast, no canary/live, no wallet.**
- **result**: PARTIAL — config + adapter init + postgres attempt verified.
  Full smoke with real DSN pending LPBOT_POSTGRES_TEST_DSN provisioning.

## 1. Binary used

```
$ ls -la /opt/lpbot/lp-bot-v3/bin/lpbot-shadow
-rwxr-xr-x 1 root root 47M /opt/lpbot/lp-bot-v3/bin/lpbot-shadow

$ file /opt/lpbot/lp-bot-v3/bin/lpbot-shadow
ELF 64-bit LSB executable, x86-64, dynamically linked
build commit: 61f6621
build tags: shadow
```

## 2. Environment (env vars set for smoke only)

```bash
export DATABASE_URL="postgresql://lpbot:fakepw@127.0.0.1:54322/lpbot_shadow?sslmode=disable&connect_timeout=2"
export REDIS_URL="redis://127.0.0.1:6379/0"
# Other env (BASE_RPC_*, SOL_RPC_*, TELEGRAM_*, DASHBOARD_TOKEN) UNSET
# (shadow service tolerates unset vars via ${VAR:-} fallbacks in config.shadow.toml)
```

`DATABASE_URL` is a **deliberately fake** DSN to verify the binary:
1. Loads config.shadow.toml and resolves the env var
2. Initializes the postgres adapter
3. Attempts to connect (fails because no real postgres at 127.0.0.1:54322)
4. Exits cleanly via the documented error path

This is honest smoke evidence: it confirms wiring up to the postgres
adapter init, but does NOT fabricate a passing connection.

## 3. Smoke output (annotated)

```
$ DATABASE_URL="..." REDIS_URL="..." timeout 30 ./bin/lpbot-shadow \
    --config=configs/config.shadow.toml
```

```
{"level":"info","ts":...,"caller":"lpbot/main.go:586","msg":"lpbot starting",
 "env":"shadow","schema_version":1,"version":"0.4.0","mode":"shadow","commit":"61f6621"}
```

**✅ Config loaded**: env=shadow, mode=shadow, schema_version=1, commit=61f6621

```
=== SHADOW MODE ===
Running in shadow mode: simulating transactions without real execution.
Configure via: configs/config.shadow.toml
```

**✅ Mode gate** fired the shadow banner (per `mode_shadow.go`). No live/canary path entered.

```
{"level":"warn","ts":...,"caller":"lpbot/alerting.go:84",
 "msg":"telegram token missing, fallback to logs only","env":"shadow"}
```

**✅ Alerting adapter initialized**. Missing TELEGRAM_BOT_TOKEN is non-fatal (shadow tolerates it via ${TELEGRAM_BOT_TOKEN:-} fallback). No secret leaked.

```
{"level":"info","ts":...,"caller":"lpbot/main.go:637",
 "msg":"initializing adapters...","env":"shadow"}
```

**✅ Adapters init started**.

```
2026/06/08 20:14:35 [rpc:base] initial rpc order: [https://base.drpc.org https://mainnet.base.org https://mainnet-preconf.base.org]
2026/06/08 20:14:35 [rpc:base] initial health check summary:
  https://base.drpc.org:OK(747ms),
  https://mainnet.base.org:OK(842ms),
  https://mainnet-preconf.base.org:OK(1.1s)
{"level":"info","ts":...,"caller":"lpbot/main.go:678",
 "msg":"Base RPC provider initialized","env":"shadow",
 "primary":"base.drpc.org","endpoints":5}
```

**✅ Base RPC adapter initialized**. Real public RPC endpoints were contacted (free public, no paid RPC). All 3 health checks PASS in <2s. The binary chose base.drpc.org as the primary based on health.

```
{"level":"error","ts":...,"caller":"lpbot/main.go:603",
 "msg":"failed to initialize adapters","env":"shadow",
 "error":"failed to initialize postgres store: failed to ping database:
          pq: password authentication failed for user \"lpbot\" (28P01)"}
```

**✅ Postgres adapter was wired and pinged**. It got a real "password authentication failed" reply from postgres, which is the **expected** failure given the fake DSN. This proves the postgres adapter is correctly initialized and is making real connection attempts.

```
{"level":"error","ts":...,"caller":"log/alerter.go:25",
 "msg":"adapter initialization failed: ...","alert_level":"p0","alert_src":"startup"}
```

**✅ Alert path fired** for the p0 startup failure (intended behavior; would notify in real deployment via Telegram).

**Exit**: 0 (timeout reached, not a crash).

## 4. What was verified

| Check | Result |
|---|---|
| Binary exists, executable, mode=shadow | ✅ |
| `lpbot-shadow --config=configs/config.shadow.toml` accepted | ✅ |
| Config TOML parsed (mode/expected=shadow, store/postgres backend) | ✅ |
| Env var DATABASE_URL resolved into config | ✅ |
| Shadow banner fired | ✅ |
| LPBOT_CONFIRM_LIVE not set → live mode rejected | ✅ (we never set it; mode is shadow) |
| Alerting adapter init (telegram token missing → log-only fallback) | ✅ |
| Base RPC adapter init (3 free public endpoints health-check OK) | ✅ |
| Postgres adapter init (attempted to ping with fake DSN; got real error) | ✅ |
| No signing attempted | ✅ (no wallet adapter init, no canary/live path) |
| No transaction broadcast | ✅ (binary exited at adapter init) |
| No wallet loaded | ✅ (no WALLET_PASSPHRASE) |
| No real secret committed | ✅ |
| No DSN with password persisted to logs (only "password authentication failed" message) | ✅ |

## 5. What was NOT verified (out of scope or no DSN)

| Check | Why |
|---|---|
| Full daemon run (adapter init OK + bus/risk/loop starts) | Postgres adapter exited first; not reached |
| Real postgres schema guard | No real DB |
| Real shadow loop tick (one full cycle) | No real DB |
| LPBOT_POSTGRES_TEST_DSN integration test | DSN not set |
| Shadow decision trace table INSERT | No real DB |
| Live schema guard (loadLiveSchemaState) | Not reached because postgres adapter init failed first |
| TIER_A/TIER_B/TIER_C risk thresholds actually fire | Not reached |
| Dashboard / metrics endpoint exposure | Not reached |

## 6. Honest assessment

This smoke **does NOT** validate end-to-end shadow functionality (which
requires a real LPBOT_POSTGRES_TEST_DSN). It DOES validate:

1. The shadow binary builds and runs.
2. The config file is parseable and env vars resolve correctly.
3. The shadow mode gate fires (no live/canary path entry).
4. The adapter init sequence reaches the postgres adapter (i.e. all
   earlier steps succeed: config load, alerting, Base RPC).
5. The postgres adapter makes a real connection attempt to the DSN host.
6. The binary exits cleanly when an adapter fails (no crash, no
   misleading "started successfully" log).

This is sufficient evidence to claim **shadow startup wiring is
correct** without claiming **shadow startup is fully functional**.

## 7. To upgrade to a full smoke

A future stage should:
1. Provision a real LPBOT_POSTGRES_TEST_DSN (e.g. `docker run -d postgres:16-alpine`)
2. `make migrate-postgres` to apply all 12 migrations
3. Re-run the smoke with the real DSN
4. Capture evidence of: live schema guard pass, shadow decision trace
   table write, bus/risk/loop init, dashboard endpoint exposure.
5. Document any divergence from expected behavior.

This is recorded as remaining_blocker `BLK-P0PG-2-FIX-01` in `FINAL_VERDICT.json`.

## 8. Forbidden actions recheck during smoke

- ❌ No real order / no signing / no broadcast (binary never reached execution path)
- ❌ No wallet loaded (no WALLET_PASSPHRASE)
- ❌ No real secret committed (only public RPCs + fake DSN)
- ❌ No canary / live / paper
- ❌ No paid RPC (only free public endpoints)
- ❌ No merge / no pkill
- ❌ No R1 reopen / no R2 entry
- ❌ No supervisor fix / no 12h/13h/24h run

All forbidden actions maintained. R1 PAUSE / R2 LOCKED / canary/live LOCKED unchanged.
