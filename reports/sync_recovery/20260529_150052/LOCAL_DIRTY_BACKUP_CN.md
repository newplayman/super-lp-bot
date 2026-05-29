# Local Dirty Backup

- stage: 'SYNC_RECOVERY_BEFORE_TIERC_ONCHAIN_LOGS_V1'
- local_repo: '/Users/bendu/lp-bot/v3'
- branch: 'feat/supabase-postgres-deployment'
- head: 'b0439792f8bf69fb371f34c5e734934e1c81db54'
- dirty_files:
  - 'scripts/generate_shadow_reality_audits_v2.sh'
  - 'reports/'
- dirty_patch_backup_path: '/Users/bendu/lp-bot-backups/sync_recovery_20260529_150052/local_dirty_generate_shadow_reality_audits_v2.patch'
- reports_backup_path: '/Users/bendu/lp-bot-backups/sync_recovery_20260529_150052/local_reports/'
- involves_trading_path: no
- involves_wallet_tx_bridge_live_paper: no
- classification: research_report_script_only
- secret_scan_result: no_real_secret_found
- stash_allowed: yes
- followup_recommendation: stash_local_dirty_then_fast_forward_after_vps_artifact_push

## Dirty Patch Summary

- default repair version changed from 'v2_rpc_lineage_window' to 'v3_raw_universe_lineage_window'
- adds source repaired semantics / waterfall / redesign reporting
- adds repaired_v2 research materialization and reporting logic
- change scope is reporting SQL / research report generation
- no wallet / tx / bridge / live / paper execution path touched

## Secret Scan Interpretation

- 'POSTGRES_DSN' / 'DATABASE_URL' / similar names are present only as variable names or fallback expressions
- no concrete private key, mnemonic, password, API token, or database credential value was found in the reviewed dirty file or generated sync_recovery report files
