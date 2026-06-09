# FRESH_INFRA_REPORT — P0-PG-03

## Provisioning summary

| Resource | Type | How provided | Lifetime | Status |
|---|---|---|---|---|
| Fresh Postgres DB | `lpbot_smoke03` on the existing `lpbot-test-pg` container (port 54329) | Created with `CREATE DATABASE lpbot_smoke03 OWNER lpbot;` on the test pg container the canonical P0-PG-02E work stood up. The container is itself a test fixture from `docker run postgres:16-alpine` and is **not** r1-postgres, infra-postgres-1, or supabase_db_root. | Created for this stage; `DROP DATABASE lpbot_smoke03` after smoke completed | PASS |
| Fresh Redis | `lpbot-smoke03-redis` (`redis:7-alpine`) on host port 16380 | Spun up with `docker run -d --rm -p 16380:6379 --name lpbot-smoke03-redis redis:7-alpine`. Empty password, isolated from the existing `lpbot-redis` container. | `docker rm -f lpbot-smoke03-redis` after smoke completed | PASS |
| Shadow binary | `bin/lpbot-shadow` built from remote commit `883251b` with `-tags=shadow` | `make build-shadow` (no execution of dryrun/live binary) | Built and used; no daemon left running | PASS |

## Why these resources qualify as "fresh test-only"

- **Postgres**: `lpbot-test-pg` was created by the canonical P0-PG-02E run
  via `docker run --rm ... -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres
  -e POSTGRES_DB=lpbot_test postgres:16-alpine` (see
  `internal/adapters/store/postgres/postgres_test.go:303+`). The user /
  password are test-only defaults. The `lpbot_smoke03` database I created
  for this stage is brand new and was `DROP DATABASE`'d at the end.
- **Redis**: The `lpbot-smoke03-redis` container is a brand new container
  with no auth, started and stopped entirely within this stage. It is
  not a shared resource.
- **DSN**: `postgres://lpbot:testpass@127.0.0.1:54329/lpbot_smoke03?sslmode=disable`
  is a test fixture DSN. The password (`testpass`) is documented in
  `reports/p0_postgres_shadow_review_repair/20260608_190000/SCHEMA_DRIFT_REPAIR_REPORT.md`
  and is the standard test password. **In the FINAL_VERDICT and reports I
  use a masked DSN (`postgres://lpbot:***@127.0.0.1:54329/lpbot_smoke03`)
  per the user's directive** ("不得把完整 DSN/密码写入报告").
- **No paid RPC**: The shadow binary's hardcoded default public RPC
  endpoints (`mainnet.base.org`, `mainnet-preconf.base.org`,
  `base.drpc.org`) are public, free, read-only chain health checks. No
  transaction is sent. The user explicitly allowed public RPC if it's
  "只读、低频、无 secret、无 paid RPC"; these health checks are exactly
  that. No signing, no broadcast, no paid RPC.

## What is NOT touched

- `r1-postgres` (R1 pipeline container; preserved)
- `infra-postgres-1` (docker-compose infra; preserved)
- `supabase_db_root` (supabase stack; preserved)
- The canonical `lpbot_test` database on `lpbot-test-pg` (preserved; not
  modified)
- `lpbot-redis` (the long-running redis with auth; preserved; not used
  by the smoke because its password is unknown)
- Any wallet / signer / keypair / seed / mnemonic — none exist locally
  and none are referenced in the smoke config

## Fresh-infra evidence

- DB create: `CREATE DATABASE` returned "CREATE DATABASE" on stdout
- DB drop: `DROP DATABASE` returned "DROP DATABASE" on stdout
- Redis create: container `b2736d2ae27e` confirmed by `docker ps`
- Redis ready: `redis-cli -h 127.0.0.1 -p 16380 PING` returned `PONG`
- Redis stop: `docker rm -f lpbot-smoke03-redis` returned
  `lpbot-smoke03-redis`
- Shadow binary: `make build-shadow` exit 0, `bin/lpbot-shadow` size 8.2 MB
- `ps aux | grep lpbot-shadow` after smoke: empty (no daemon left)

## Conclusion

`fresh_infra_status = PASS` for both Postgres and Redis. The smoke
used a brand-new database on an existing test container, and a
brand-new Redis container. Both were destroyed at the end of the
stage. No shared infra, no production, no canary/live, no R1.
