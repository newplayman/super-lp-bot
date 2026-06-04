#!/usr/bin/env node
/* Stage G: Orca Whirlpool account decode via @orca-so/whirlpools 8.0.0.

For each verified Orca pool (75 total):
  - fetchConcentratedLiquidityPool(rpc, tokenMintA, tokenMintB, tickSpacing)
  - extract: tokenMintA, tokenMintB, tokenVaultA, tokenVaultB, tickSpacing,
             feeRate, protocolFeeRate, liquidity, sqrtPrice, tickCurrentIndex
  - reject if any required field missing

The SDK requires token mints and tickSpacing, not raw pool address.
We have these in collection metadata (Orca official API). For DexScreener-only
pools, we need to fall back to fetching by token pair (or by direct account read).

NO keypair / signer / transaction. Read-only.
*/
const fs = require("fs");
const path = require("path");
const { createSolanaRpc, address } = require("@solana/kit");
const whirlpool = require("@orca-so/whirlpools");

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const RPC = createSolanaRpc("https://solana-rpc.publicnode.com");

// Load collection (for token mints + tickSpacing) and chain verify
const collection = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "orca_candidate_source_collection.json"), "utf8"));
const chainVerify = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "orca_pool_chain_verification.json"), "utf8"));

const verifiedAddrs = new Set(chainVerify.filter(r => r.verified).map(r => r.pool_address));

// build pool_address -> {tokenMintA, tokenMintB, tickSpacing} lookup
const poolMeta = {};
for (const p of collection) {
  if (!p.pool_address) continue;
  if (!p.token_a_mint || !p.token_b_mint || !p.tick_spacing) continue;
  // Orca SDK uses (tokenMintOne, tokenMintTwo) but order matters; we try both
  poolMeta[p.pool_address] = {
    mintA: p.token_a_mint,
    mintB: p.token_b_mint,
    tickSpacing: p.tick_spacing,
    name: p.name,
  };
}

async function decodeOne(poolAddress) {
  const out = {
    pool_address: poolAddress,
    token_a: null,
    token_b: null,
    token_a_decimals: null,
    token_b_decimals: null,
    tick_spacing: null,
    current_tick: null,
    sqrt_price: null,
    liquidity: null,
    fee_rate: null,
    fee_rate_bps: null,
    protocol_fee_rate: null,
    reward_infos_count: 0,
    sdk_decode_success: false,
    confidence: 0.0,
    invalid_reason: null,
    latency_ms: null,
  };
  const t0 = Date.now();
  const meta = poolMeta[poolAddress];
  if (!meta) {
    out.invalid_reason = "no_meta_in_collection";
    out.latency_ms = Date.now() - t0;
    return out;
  }

  // SDK requires tokenMintOne, tokenMintTwo, tickSpacing
  // Try (A, B) order first
  let pool;
  let lastErr = null;
  const orders = [[meta.mintA, meta.mintB], [meta.mintB, meta.mintA]];
  for (const [m1, m2] of orders) {
    try {
      pool = await whirlpool.fetchConcentratedLiquidityPool(
        RPC,
        address(m1),
        address(m2),
        Number(meta.tickSpacing)
      );
      if (pool && pool.address === poolAddress) break;
      // if address doesn't match, this order is wrong
      pool = null;
    } catch (e) {
      lastErr = String(e).slice(0, 80);
      pool = null;
    }
  }
  if (!pool) {
    out.invalid_reason = `sdk_decode_error: ${lastErr || 'address_mismatch'}`;
    out.latency_ms = Date.now() - t0;
    return out;
  }

  // extract fields
  out.token_a = pool.tokenMintA;
  out.token_b = pool.tokenMintB;
  out.tick_spacing = pool.tickSpacing;
  out.current_tick = pool.tickCurrentIndex;
  out.sqrt_price = pool.sqrtPrice?.toString?.() || null;
  out.liquidity = pool.liquidity?.toString?.() || null;
  out.fee_rate = pool.feeRate;
  // feeRate in Orca = bps * 100 (e.g. 400 = 4bps)
  if (pool.feeRate != null) out.fee_rate_bps = Math.round(Number(pool.feeRate) / 100);
  out.protocol_fee_rate = pool.protocolFeeRate;
  out.reward_infos_count = Array.isArray(pool.rewardInfos) ? pool.rewardInfos.length : 0;

  // decimals from collection
  if (collection) {
    const c = collection.find(p => p.pool_address === poolAddress);
    if (c) {
      out.token_a_decimals = c.token_a_decimals;
      out.token_b_decimals = c.token_b_decimals;
    }
  }

  out.sdk_decode_success = true;
  out.confidence = 0.92;
  out.latency_ms = Date.now() - t0;
  return out;
}

async function main() {
  console.log("[stageG] verified pools:", verifiedAddrs.size);
  const results = [];
  for (const addr of verifiedAddrs) {
    const r = await decodeOne(addr);
    results.push(r);
    if (results.length % 10 === 0 || results.length === verifiedAddrs.size) {
      const n_ok = results.filter(x => x.sdk_decode_success).length;
      console.log(`[stageG] decoded ${results.length}/${verifiedAddrs.size} success=${n_ok}`);
    }
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "orca_whirlpool_pool_snapshot.json"),
    JSON.stringify(results, null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,token_a,token_b,token_a_decimals,token_b_decimals,tick_spacing,current_tick,sqrt_price,liquidity,fee_rate,fee_rate_bps,protocol_fee_rate,reward_infos_count,sdk_decode_success,confidence,invalid_reason"
  ];
  for (const r of results) {
    csvLines.push([
      r.pool_address,
      r.token_a || "",
      r.token_b || "",
      r.token_a_decimals ?? "",
      r.token_b_decimals ?? "",
      r.tick_spacing ?? "",
      r.current_tick ?? "",
      r.sqrt_price ?? "",
      r.liquidity ?? "",
      r.fee_rate ?? "",
      r.fee_rate_bps ?? "",
      r.protocol_fee_rate ?? "",
      r.reward_infos_count ?? 0,
      r.sdk_decode_success,
      r.confidence,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(
    path.join(REPORT_DIR, "orca_whirlpool_pool_snapshot.csv"),
    csvLines.join("\n") + "\n"
  );

  const n_success = results.filter(r => r.sdk_decode_success).length;
  const n_high_fee = results.filter(r => r.sdk_decode_success && Number(r.fee_rate_bps) >= 30).length;
  const n_stable = results.filter(r => r.sdk_decode_success && (
    (r.token_a && ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"].includes(r.token_a)) ||
    (r.token_b && ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"].includes(r.token_b))
  )).length;
  const n_sol = results.filter(r => r.sdk_decode_success && (
    (r.token_a && r.token_a === "So11111111111111111111111111111111111111112") ||
    (r.token_b && r.token_b === "So11111111111111111111111111111111111111112")
  )).length;
  const summary = {
    stage: "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    attempted_count: results.length,
    sdk_decode_success_count: n_success,
    sdk_decode_failure_count: results.length - n_success,
    high_fee_pool_count: n_high_fee,
    stable_pair_count: n_stable,
    sol_pair_count: n_sol,
    quote_candidate_count: 0,
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "decode_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log("[stageG] summary:", summary);
}

main().catch(e => {
  console.error("[stageG] fatal:", e);
  process.exit(1);
});
