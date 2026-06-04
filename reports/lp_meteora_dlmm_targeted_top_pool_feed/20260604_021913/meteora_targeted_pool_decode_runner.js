#!/usr/bin/env node
/* Stage F: SDK decode targeted Meteora DLMM pools (fixed for v1.9.10).
 *
 * Real shape discovered:
 *   pool.tokenX.publicKey     - PublicKey (use .toBase58())
 *   pool.tokenX.mint          - undefined (NOT the mint)
 *   pool.lbPair.tokenXMint    - PublicKey
 *   pool.lbPair.tokenYMint    - PublicKey
 *   pool.lbPair.binStep       - number
 *   pool.lbPair.activeId      - number
 *   pool.lbPair.parameters.baseFactor - number
 *   pool.getFeeInfo()         - { baseFeeRatePercentage: string, maxFeeRatePercentage: string, protocolFeePercentage: string }
 *
 * These percentage strings are in PERCENT (so "0.04" = 0.04% = 4 bps).
 * We convert to bps.
 */
const fs = require("fs");
const path = require("path");
const { Connection, PublicKey } = require("@solana/web3.js");
const DLMM = require("@meteora-ag/dlmm");

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const RPC_URL = "https://solana-rpc.publicnode.com";

function makeConnection() {
  return new Connection(RPC_URL, "confirmed");
}

async function decodeOne(poolAddress) {
  const out = {
    pool_address: poolAddress,
    token_x: null,
    token_y: null,
    token_x_symbol_if_known: null,
    token_y_symbol_if_known: null,
    token_x_decimals: null,
    token_y_decimals: null,
    bin_step: null,
    active_bin: null,
    active_price: null,
    reserve_x_raw: null,
    reserve_y_raw: null,
    base_fee_bps: null,
    max_fee_bps: null,
    sdk_decode_success: false,
    confidence: 0.0,
    invalid_reason: null,
    latency_ms: null,
  };
  const t0 = Date.now();
  const conn = makeConnection();
  let pool;
  try {
    pool = await DLMM.create(conn, new PublicKey(poolAddress));
  } catch (e) {
    out.invalid_reason = `dlmm_create_error: ${String(e).slice(0, 80)}`;
    out.latency_ms = Date.now() - t0;
    return out;
  }

  // tokenX/tokenY: use lbPair.tokenXMint/tokenYMint (most reliable)
  try {
    if (pool.lbPair?.tokenXMint) out.token_x = pool.lbPair.tokenXMint.toBase58();
    if (pool.lbPair?.tokenYMint) out.token_y = pool.lbPair.tokenYMint.toBase58();
    // also try tokenX.publicKey (object form may have decimals)
    if (pool.tokenX?.publicKey && !out.token_x) out.token_x = pool.tokenX.publicKey.toBase58();
    if (pool.tokenY?.publicKey && !out.token_y) out.token_y = pool.tokenY.publicKey.toBase58();
    if (pool.tokenX?.decimals != null) out.token_x_decimals = pool.tokenX.decimals;
    if (pool.tokenY?.decimals != null) out.token_y_decimals = pool.tokenY.decimals;
  } catch (e) {
    out.invalid_reason = "token_extract_error";
  }

  // binStep + activeId (from lbPair)
  try {
    if (pool.lbPair?.binStep != null) out.bin_step = Number(pool.lbPair.binStep);
    if (pool.lbPair?.activeId != null) out.active_bin = Number(pool.lbPair.activeId);
  } catch (e) {
    // ok
  }

  // active bin price
  try {
    const active = await pool.getActiveBin();
    if (active) {
      if (active.binId != null && out.active_bin == null) out.active_bin = Number(active.binId);
      if (active.price != null) out.active_price = String(active.price);
    }
  } catch (e) {
    out.invalid_reason = (out.invalid_reason || "") + ` active_bin_error: ${String(e).slice(0, 60)}`;
  }

  // fee info: convert percentage string to bps
  try {
    const fee = await pool.getFeeInfo();
    if (fee) {
      const basePct = Number(fee.baseFeeRatePercentage);
      const maxPct = Number(fee.maxFeeRatePercentage);
      if (!Number.isNaN(basePct)) out.base_fee_bps = Math.round(basePct * 100);  // pct -> bps
      if (!Number.isNaN(maxPct)) out.max_fee_bps = Math.round(maxPct * 100);
    }
  } catch (e) {
    out.invalid_reason = (out.invalid_reason || "") + ` fee_error: ${String(e).slice(0, 60)}`;
  }

  // success criteria
  if (out.token_x && out.token_y && out.active_bin != null && out.base_fee_bps != null) {
    out.sdk_decode_success = true;
    out.confidence = 0.85;
  } else {
    if (!out.invalid_reason) {
      const missing = ["token_x","token_y","active_bin","base_fee_bps"].filter(k => {
        const v = out[k];
        return v == null || v === "";
      });
      out.invalid_reason = "missing_required_fields: " + missing.join(",");
    }
  }
  out.latency_ms = Date.now() - t0;
  return out;
}

async function main() {
  const verifyJson = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "meteora_targeted_pool_chain_verify.json"), "utf8"));
  const verified = verifyJson.filter((r) => r.verified && r.selected_for_sdk_decode);
  console.log(`[stageF] verified pools: ${verified.length}`);

  const results = [];
  for (let i = 0; i < verified.length; i++) {
    const v = verified[i];
    const r = await decodeOne(v.pool_address);
    results.push(r);
    if ((i + 1) % 5 === 0 || i === verified.length - 1) {
      const n_ok = results.filter((x) => x.sdk_decode_success).length;
      console.log(`[stageF] decoded ${i + 1}/${verified.length} success=${n_ok}`);
    }
    // tiny pause to avoid 429
    await new Promise((res) => setTimeout(res, 80));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "meteora_targeted_pool_snapshot.json"),
    JSON.stringify(results, null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,token_x,token_y,token_x_decimals,token_y_decimals,bin_step,active_bin,active_price,base_fee_bps,max_fee_bps,sdk_decode_success,confidence,invalid_reason"
  ];
  for (const r of results) {
    csvLines.push([
      r.pool_address,
      r.token_x || "",
      r.token_y || "",
      r.token_x_decimals ?? "",
      r.token_y_decimals ?? "",
      r.bin_step ?? "",
      r.active_bin ?? "",
      r.active_price ?? "",
      r.base_fee_bps ?? "",
      r.max_fee_bps ?? "",
      r.sdk_decode_success,
      r.confidence,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(path.join(REPORT_DIR, "meteora_targeted_pool_snapshot.csv"), csvLines.join("\n") + "\n");

  const n_success = results.filter((r) => r.sdk_decode_success).length;
  const n_high_fee = results.filter((r) => r.sdk_decode_success && (Number(r.base_fee_bps) >= 500 || Number(r.max_fee_bps) >= 2000)).length;
  const n_high_max_fee = results.filter((r) => r.sdk_decode_success && Number(r.max_fee_bps) >= 2000).length;
  const summary = {
    stage: "LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1",
    run_id: process.env.RUN_ID || "",
    attempted_count: results.length,
    sdk_decode_success_count: n_success,
    sdk_decode_failure_count: results.length - n_success,
    high_fee_pool_count: n_high_fee,
    high_max_fee_pool_count: n_high_max_fee,
    quote_candidate_count: 0,
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "decode_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log(`[stageF] summary:`, summary);
}

main().catch((e) => {
  console.error("[stageF] fatal:", e);
  process.exit(1);
});
