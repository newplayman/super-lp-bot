// Package migrator: embed the migration files for the postgres
// adapter. This is a separate file from migrator.go so the embed
// directive is co-located with the actual files being embedded.
package migrator

import "embed"

//go:embed all:sql
var MigrationsFS embed.FS
