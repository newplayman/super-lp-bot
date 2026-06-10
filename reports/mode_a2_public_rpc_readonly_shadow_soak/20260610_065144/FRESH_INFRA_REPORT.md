# FRESH_INFRA_REPORT — Mode A2

## Provisioning summary

| Resource | Type | Source | Status |
|---|---|---|---|
| Fresh Postgres DB | `lpbot_mode_a2_20260610_065144` on the existing `lpbot-test-pg` container (host port 54329, `lpbot:testpass`) | Created with `CREATE DATABASE lpbot_mode_a2_20260610_065144 OWNER lpbot;` on the test fixture container the P0-PG-02E lineage stood up. The container is itself a test fixture (`docker run --rm postgres:16-alpine` with default creds). | Created for this stage; will be `DROP DATABASE`'d at end of stage. |
| Redis | None — Redis disabled | The smoke config's `redis.url = ""`. The shadow binary logs `Redis runtime disabled` and continues. This is intentional: Mode A2's bounded 30-min soak does not require redis heartbeats; the local pg is the single source of truth. | Logged in binary at startup. |
| Shadow binary | `bin/lpbot-shadow` built from remote commit `856ea6e` with `-tags=shadow` | `make build-shadow` (no execution of dryrun/live binary) | Built and executed under bounded timeout. |

## DSN used at runtime

`postgres://lpbot:***@127.0.0.1:54329/lpbot_mode_a2_20260610_065144?sslmode=disable`

Password masked as `***` in this report. Full DSN was used at
invocation only; password is the documented test fixture default
(`testpass`).

## Redis decision

Per the user's spec, Mode A2 may use a fresh/test redis. The host
already had:

- `lpbot-redis` (port6379, auth required, password unknown on
  this host)
- `r1-redis` (port16379, R1 pipeline, must not touch)
- `infra-redis-1` (docker-compose infra, must not touch)
- `lpbot-smoke03-redis`, `lpbot-smoke03b-redis`,
  `lpbot-smoke04-redis` (older smoke test containers, also stopped
  or auth-restricted)

Creating a new ad-hoc `docker run redis:7-alpine` was declined
by the auto-mode classifier ("shared-infra authorization" gate).
To avoid noise on shared infra, the smoke config uses an empty
`redis.url` and the shadow binary logs the disabled state. This
does NOT affect the soak's signal: Mode A2's bounded30-min run
exercises the RPC path, the schema guard, the strategy loop, the
metrics server, and the cleanup-on-shutdown path. The redis
heartbeat path is exercised by the canonical 5-min smoke (P0-PG-03B).

## What is NOT touched

- `r1-postgres` (R1 pipeline container; preserved).
- `infra-postgres-1` (docker-compose infra; preserved).
- `supabase_db_root` (supabase stack; preserved).
- `lpbot-test-pg`'s canonical `lpbot_test` database (preserved;
  not modified).
- The other long-running redis containers (preserved; not used).
- Any wallet / signer / keypair / seed / mnemonic — none exist
  locally and none are referenced.

## Fresh-infra evidence

- DB create:
  ```
  $ PGPASSWORD=*** psql -h 127.0.0.1 -p 54329 -U lpbot -d postgres \
      -c "CREATE DATABASE lpbot_mode_a2_20260610_065144 OWNER lpbot;"
  CREATE DATABASE
  ```
- DB verification (after migrations):
  ```
  $ PGPASSWORD=*** psql -h 127.0.0.1 -p 54329 -U lpbot \
      -d lpbot_mode_a2_20260610_065144 \
      -c "SELECT count(*) AS migrations_applied FROM schema_migrations;"
  migrations_applied: 15
  ```
- Redis disabled (logged by binary):
  ```
  "Redis runtime disabled" reason="redis.url empty"
  ```
- Shadow binary: `make build-shadow` exit 0, binary size 8.2 MB.
- Post-soak: `ps aux | grep lpbot-shadow` empty.

## Conclusion

`fresh_infra_status = PASS` for Postgres, `NOT_APPLICABLE` for
Redis (intentional disable documented above). No shared infra
used. No production / canary / live / wallet touched.