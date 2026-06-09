// cmd/lpbot-migrate-postgres is the canonical Go-based migration CLI
// for the lp-bot Postgres adapter.
//
// Usage:
//
//	lpbot-migrate-postgres plan    # list migrations; mark applied / to-apply
//	lpbot-migrate-postgres status  # verify required tables/indexes
//	lpbot-migrate-postgres apply   # apply pending migrations
//
// DSN resolution order (first wins):
//   1. $POSTGRES_DSN
//   2. $DATABASE_URL
//
// Safety:
//   - Refuses DSNs containing "supabase.co", "rds.amazonaws.com",
//     "prod", or "production" unless $LPBOT_MIGRATE_ALLOW_LIVE=YES.
//   - Each migration runs in its own transaction; partial failures
//     roll back cleanly.
//   - Applied migrations are tracked in schema_migrations with a
//     SHA256 checksum; re-running apply is a no-op.
//   - Checksum mismatch (file changed since apply) refuses to proceed.
//   - Does NOT auto-load .env.canary, .env.live, or any canary/live
//     env. Operators must set POSTGRES_DSN or DATABASE_URL explicitly.
//
// This replaces scripts/migrate-postgres.sh as the canonical entry
// point. The shell script remains as a thin wrapper that invokes
// this binary, for backward compat with CI and operator muscle
// memory.
//
// build tag: none (this is a standalone utility; the same code is
// safe to run for shadow / canary / live / test DBs when the
// operator passes a real DSN).
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/lpbot/lpbot/internal/adapters/store/postgres/migrator"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	mode := migrator.Mode(strings.ToLower(os.Args[1]))
	switch mode {
	case migrator.ModePlan, migrator.ModeStatus, migrator.ModeApply:
		// ok
	default:
		usage()
		os.Exit(2)
	}

	dsn := os.Getenv("POSTGRES_DSN")
	if dsn == "" {
		dsn = os.Getenv("DATABASE_URL")
	}
	if dsn == "" {
		fmt.Fprintln(os.Stderr, "lpbot-migrate-postgres: POSTGRES_DSN / DATABASE_URL is empty")
		fmt.Fprintln(os.Stderr, "hint: copy .env.postgres.example to .env.postgres and fill DATABASE_URL")
		fmt.Fprintln(os.Stderr, "      (canary/live env files are NOT auto-loaded; set explicitly)")
		os.Exit(2)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	runner, err := migrator.NewRunner(ctx, migrator.Config{
		DSN:           dsn,
		MigrationsFS:  migrator.MigrationsFS,
		MigrationsDir: "sql",
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "lpbot-migrate-postgres: newRunner:", err)
		os.Exit(3)
	}
	defer runner.Close()

	switch mode {
	case migrator.ModePlan:
		out, err := runner.Plan(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, "lpbot-migrate-postgres: plan:", err)
			os.Exit(3)
		}
		writeJSON(out)

	case migrator.ModeStatus:
		out, err := runner.Status(ctx)
		if err != nil {
			fmt.Fprintln(os.Stderr, "lpbot-migrate-postgres: status:", err)
			os.Exit(3)
		}
		writeJSON(out)
		if !out.AllPresent {
			os.Exit(4) // missing required tables/indexes
		}

	case migrator.ModeApply:
		out, err := runner.Apply(ctx)
		if err != nil {
			if out != nil {
				fmt.Fprintf(os.Stderr, "lpbot-migrate-postgres: apply failed at %s: %v\n", out.FailedAt, err)
				fmt.Fprintf(os.Stderr, "  applied before failure: %v\n", out.Applied)
				fmt.Fprintf(os.Stderr, "  was partial: %v\n", out.WasPartial)
				writeJSON(out)
			} else {
				fmt.Fprintln(os.Stderr, "lpbot-migrate-postgres: apply:", err)
			}
			os.Exit(5)
		}
		writeJSON(out)
	}
}

func writeJSON(v interface{}) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}

func usage() {
	fmt.Fprintln(os.Stderr, "Usage: lpbot-migrate-postgres {plan|status|apply}")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "DSN resolution order:")
	fmt.Fprintln(os.Stderr, "  1. $POSTGRES_DSN")
	fmt.Fprintln(os.Stderr, "  2. $DATABASE_URL")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "Safety:")
	fmt.Fprintln(os.Stderr, "  - Refuses supabase.co / rds.amazonaws.com / prod / production DSNs")
	fmt.Fprintln(os.Stderr, "    unless LPBOT_MIGRATE_ALLOW_LIVE=YES")
	fmt.Fprintln(os.Stderr, "  - Per-migration transaction; partial failures roll back")
	fmt.Fprintln(os.Stderr, "  - SHA256 checksum recorded in schema_migrations; mismatch refuses")
	fmt.Fprintln(os.Stderr, "  - Does NOT auto-load .env.canary, .env.live, or any canary/live env")
}
