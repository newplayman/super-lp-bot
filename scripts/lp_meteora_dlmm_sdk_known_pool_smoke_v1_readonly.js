#!/usr/bin/env node
/**
 * LP_METEORA_DLMM_SDK_KNOWN_POOL_SMOKE_V1_READONLY (v2 - resilient)
 *
 * Read-only smoke for Meteora DLMM via @meteora-ag/dlmm SDK.
 *
 * STRICTLY read-only:
 *   - No keypair
 *   - No signer
 *   - No transaction
 *   - No sendTransaction
 *   - No swap / open LP / close LP / collect fee / bridge
 *   - No wallet adapter
 *
 * Per-pool try/catch so a single failure doesn't fail the whole smoke.
 * Falls back to a second RPC if the primary returns 403 (publicnode rate limit).
 *
 * Usage:
 *   NODE_PATH=/tmp/lpbot_meteora_dlmm_sdk_probe_${RUN_ID}/node_modules node \
 *     scripts/lp_meteora_dlmm_sdk_known_pool_smoke_v1_readonly.js \
 *     <pool1> <pool2> ... <output.json>
 */
"use strict";

const fs = require("fs");
const path = require("path");
const DLMM = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");

const PRIMARY_RPC = "https://solana.publicnode.com";
const FALLBACK_RPC = "https://api.mainnet-beta.solana.com";

function now() {
  return Date.now();
}

async function withFallback(thunk) {
  try {
    return await thunk(new Connection(PRIMARY_RPC, "confirmed"));
  } catch (e1) {
    const msg1 = String(e1?.message ?? e1);
    if (msg1.includes("403") || msg1.includes("429") || msg1.includes("fetch failed")) {
      try {
        return await thunk(new Connection(FALLBACK_RPC, "confirmed"));
      } catch (e2) {
        throw e2;
      }
    }
    throw e1;
  }
}

async function safeCall(fn) {
  try {
    return [await fn(), null];
  } catch (e) {
    return [null, String(e?.message ?? e)];
  }
}

async function smokeOnePool(poolAddress) {
  const t0 = now();
  const result = {
    pool_address: poolAddress,
    pool_owner: null,
    sdk_decode_success: false,
    token_x: null,
    token_y: null,
    token_x_decimals: null,
    token_y_decimals: null,
    bin_step: null,
    active_bin_id: null,
    active_bin_price: null,
    active_bin_x_amount: null,
    active_bin_y_amount: null,
    fee_info_available: false,
    fee_info_base_fee_bps: null,
    fee_info_max_fee_bps: null,
    fee_info_protocol_fee_bps: null,
    bin_array_available: false,
    bin_array_count: 0,
    first_bin_array_index: null,
    liquidity_fields_available: false,
    reserve_x_amount: null,
    reserve_y_amount: null,
    lock_info_available: false,
    lock_info_locked_by: null,
    lock_info_lock_end_ts: null,
    get_active_bin_error: null,
    get_fee_info_error: null,
    get_bin_array_error: null,
    get_lock_info_error: null,
    latency_ms_total: 0,
  };

  let dlmmPool = null;
  try {
    // DLMM.create itself does getMultipleAccountsInfo on the pool + bitmap extension + clock
    [dlmmPool, result.create_error] = await safeCall(() =>
      withFallback((connection) =>
        DLMM.create(connection, new PublicKey(poolAddress), { cluster: "mainnet-beta" })
      )
    );
    if (!dlmmPool) {
      result.latency_ms_total = now() - t0;
      return result;
    }

    // Direct fields from the decoded LbPair
    result.pool_owner = dlmmPool.program?.programId?.toBase58?.() ?? null;
    result.bin_step = dlmmPool.lbPair?.binStep ?? null;

    result.token_x = dlmmPool.tokenX?.publicKey?.toBase58?.() ?? null;
    result.token_y = dlmmPool.tokenY?.publicKey?.toBase58?.() ?? null;
    result.token_x_decimals = dlmmPool.tokenX?.mint?.decimals ?? null;
    result.token_y_decimals = dlmmPool.tokenY?.mint?.decimals ?? null;

    if (dlmmPool.tokenX?.amount) result.reserve_x_amount = dlmmPool.tokenX.amount.toString();
    if (dlmmPool.tokenY?.amount) result.reserve_y_amount = dlmmPool.tokenY.amount.toString();
    result.liquidity_fields_available =
      result.reserve_x_amount !== null || result.reserve_y_amount !== null;

    // getActiveBin (with fallback)
    {
      const [ab, err] = await safeCall(() => withFallback((c) => dlmmPool.getActiveBin(c).then(r => r).catch(e => { throw e; })));
      if (ab) {
        result.active_bin_id = ab.binId ?? null;
        result.active_bin_price = ab.price ? ab.price.toString() : null;
        if (ab.xAmount !== undefined) result.active_bin_x_amount = ab.xAmount.toString();
        if (ab.yAmount !== undefined) result.active_bin_y_amount = ab.yAmount.toString();
      } else {
        result.get_active_bin_error = err;
      }
    }

    // getFeeInfo (synchronous; doesn't need RPC)
    {
      const [fi, err] = await safeCall(async () => dlmmPool.getFeeInfo());
      if (fi) {
        result.fee_info_available = true;
        result.fee_info_base_fee_bps = fi.baseFeeRatePercentage ?? null;
        result.fee_info_max_fee_bps = fi.maxFeeRatePercentage ?? null;
        result.fee_info_protocol_fee_bps =
          fi.protocolFeeBps ?? fi.protocolFeeRatePercentage ?? null;
      } else {
        result.get_fee_info_error = err;
      }
    }

    // getBinArrayForSwap (try smaller count=1; don't bail out)
    {
      const [bas, err] = await safeCall(() =>
        withFallback((c) => dlmmPool.getBinArrayForSwap(true, 1))
      );
      if (bas) {
        result.bin_array_count = bas.length;
        result.bin_array_available = result.bin_array_count > 0;
        if (result.bin_array_count > 0) {
          const ba = bas[0];
          result.first_bin_array_index = ba.account?.account?.index?.toNumber?.() ?? null;
        }
      } else {
        result.get_bin_array_error = err;
      }
    }

    // getLbPairLockInfo
    {
      const [li, err] = await safeCall(() => dlmmPool.getLbPairLockInfo());
      if (li) {
        result.lock_info_available = true;
        result.lock_info_locked_by = li.lockedBy ?? null;
        result.lock_info_lock_end_ts = li.lockEndTs?.toNumber?.() ?? null;
      } else {
        result.lock_info_error = err;
      }
    }

    // Success if pool was created (we can read direct fields)
    result.sdk_decode_success = true;
  } catch (e) {
    result.fatal_error = String(e?.message ?? e);
  }
  result.latency_ms_total = now() - t0;
  return result;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("usage: lp_meteora_dlmm_sdk_known_pool_smoke_v1_readonly.js <pool1> [<pool2> ...] <output.json>");
    process.exit(2);
  }
  const outputPath = args[args.length - 1];
  const pools = args.slice(0, -1);

  const results = [];
  for (const p of pools) {
    const r = await smokeOnePool(p);
    results.push(r);
  }

  // overall success = DLMM.create succeeded for all pools
  const allCreated = results.every((r) => r.sdk_decode_success);

  const out = {
    smoke_attempted: true,
    smoke_success: allCreated,
    rpc_url_primary: PRIMARY_RPC,
    rpc_url_fallback: FALLBACK_RPC,
    sdk_package: "@meteora-ag/dlmm",
    sdk_package_version: "1.9.10",
    cluster: "mainnet-beta",
    pool_count: pools.length,
    results,
    timestamp_utc: new Date().toISOString(),
    solana_wallet_or_keypair_touched: false,
    transaction_sent: false,
    signer_used: false,
    wallet_adapter_used: false,
    swap_called: false,
    open_lp_called: false,
    close_lp_called: false,
    collect_fee_called: false,
    bridge_called: false,
  };

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(out, null, 2));
  console.log(`smoke wrote ${outputPath}`);
  process.exit(out.smoke_success ? 0 : 1);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(3);
});
