#!/usr/bin/env node
/* Stage G + H: Stable pool decode + quote smoke.

For each verified pool (25 Orca Whirlpool), use the SDK fetchConcentratedLiquidityPool + getPdaTickArrayAddress
to get reserves, feeRate, tickCurrent. Then quote 10/20 USD via SDK swapInstructions.

This is essentially re-running the Orca V1 stage on LST-stable pools. We'll see if the same
best_cell / realistic pattern emerges.

NO keypair / signer / transaction. Read-only.
*/
const fs = require("fs");
const path = require("path");
const { createSolanaRpc, address } = require(require("path").join(
  "/tmp/lpbot_orca_whirlpool_sdk_probe_20260604_025414", "node_modules",
  "@solana/kit"
));
const whirlpool = require(require("path").join(
  "/tmp/lpbot_orca_whirlpool_sdk_probe_20260604_025414", "node_modules",
  "@orca-so/whirlpools"
));

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const RPC = createSolanaRpc("https://solana-rpc.publicnode.com");

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";
const SOL_MINT = "So11111111111111111111111111111111111111112";
const MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So";

function pickInMint(pool) {
  if (pool.token_a === USDC_MINT || pool.token_b === USDC_MINT) return USDC_MINT;
  if (pool.token_a === USDT_MINT || pool.token_b === USDT_MINT) return USDT_MINT;
  if (pool.token_a === SOL_MINT || pool.token_b === SOL_MINT) return SOL_MINT;
  if (pool.token_a === MSOL_MINT || pool.token_b === MSOL_MINT) return MSOL_MINT;
  return null;
}

function bigintSafe(v) {
  if (v == null) return null;
  if (typeof v === "bigint") return v.toString();
  if (v && typeof v.toString === "function" && v.constructor?.name === "BN") return v.toString();
  return String(v);
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
    liquidity: null,
    fee_rate_bps: null,
    sdk_decode_success: false,
    confidence: 0.0,
    invalid_reason: null,
    latency_ms: null,
  };
  const t0 = Date.now();
  try {
    // Try to get token mints + tickSpacing from collection
    const coll = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "stable_pool_candidate_source_collection.json"), "utf8"));
    const c = coll.find(p => p.pool_address === poolAddress);
    if (!c) {
      out.invalid_reason = "no_meta_in_collection";
      out.latency_ms = Date.now() - t0;
      return out;
    }
    // Try fetching pool
    const pool = await whirlpool.fetchConcentratedLiquidityPool(
      RPC,
      address(c.base_mint),
      address(c.quote_mint),
      Number(c.tick_spacing)
    );
    if (!pool || pool.address !== poolAddress) {
      out.invalid_reason = "address_mismatch_or_fetch_failed";
      out.latency_ms = Date.now() - t0;
      return out;
    }
    out.token_a = pool.tokenMintA;
    out.token_b = pool.tokenMintB;
    out.token_a_decimals = pool.mintDecimalsA != null ? Number(pool.mintDecimalsA) : null;
    out.token_b_decimals = pool.mintDecimalsB != null ? Number(pool.mintDecimalsB) : null;
    out.tick_spacing = pool.tickSpacing != null ? Number(pool.tickSpacing) : null;
    out.current_tick = pool.tickCurrent != null ? Number(pool.tickCurrent) : null;
    out.liquidity = bigintSafe(pool.liquidity);
    out.fee_rate_bps = pool.feeRate != null ? Math.round(Number(pool.feeRate) / 100) : null;
    out.sdk_decode_success = true;
    out.confidence = 0.92;
  } catch (e) {
    out.invalid_reason = "decode_error: " + String(e).slice(0, 80);
  }
  out.latency_ms = Date.now() - t0;
  return out;
}

async function quoteOne(pool, inMint, inAmountRaw) {
  try {
    const result = await whirlpool.swapInstructions(
      RPC,
      { inputAmount: inAmountRaw, mint: address(inMint) },
      address(pool.pool_address)
    );
    const q = result.quote;
    return {
      success: true,
      amountOut: q.tokenEstOut?.toString() || null,
      fee: q.tradeFee?.toString() || null,
    };
  } catch (e) {
    return { success: false, error: String(e).slice(0, 80) };
  }
}

async function main() {
  const chainVerify = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "stable_pool_chain_verification.json"), "utf8"));
  const verifiedAddrs = chainVerify.filter(r => r.verified && r.selected_for_sdk_decode).map(r => r.pool_address);
  console.log(`[stageGH] verified pools: ${verifiedAddrs.length}`);

  // Stage G: decode
  const decoded = [];
  for (let i = 0; i < verifiedAddrs.length; i++) {
    const r = await decodeOne(verifiedAddrs[i]);
    decoded.push(r);
    if ((i + 1) % 5 === 0 || i === verifiedAddrs.length - 1) {
      const n_ok = decoded.filter(x => x.sdk_decode_success).length;
      console.log(`[stageG] decoded ${i + 1}/${verifiedAddrs.length} success=${n_ok}`);
    }
    await new Promise(r => setTimeout(r, 200));
  }

  function serializeSafe(obj) {
    return JSON.parse(JSON.stringify(obj, (k, v) => (typeof v === "bigint" ? v.toString() : v)));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "stable_pool_decode_snapshot.json"),
    JSON.stringify(serializeSafe(decoded), null, 2)
  );

  const n_success = decoded.filter(r => r.sdk_decode_success).length;
  console.log(`[stageG] summary: ${n_success} decoded`);
  if (n_success === 0) {
    console.log("[stageG] no decoded pools; skipping stage H");
    process.exit(0);
  }

  // Stage H: quote smoke
  console.log("[stageH] starting quote smoke");
  const quoteResults = [];
  for (const pool of decoded) {
    if (!pool.sdk_decode_success) continue;
    const inMint = pickInMint(pool);
    if (!inMint) continue;
    for (const usd of [10, 20, 100]) {
      let inRaw;
      if (inMint === USDC_MINT || inMint === USDT_MINT) {
        inRaw = BigInt(usd) * 1_000_000n;
      } else if (inMint === SOL_MINT) {
        inRaw = BigInt(Math.floor(usd / 130 * 1e9));
      } else if (inMint === MSOL_MINT) {
        inRaw = BigInt(Math.floor(usd / 130 * 1e9));
      } else continue;
      const q = await quoteOne(pool, inMint, inRaw);
      quoteResults.push({
        pool_address: pool.pool_address,
        notional_usd: usd,
        token_in: inMint,
        token_out: inMint === pool.token_a ? pool.token_b : pool.token_a,
        amount_in_raw: inRaw.toString(),
        quote_success: q.success,
        amount_out_raw: q.amountOut,
        fee: q.fee,
        fee_bps: pool.fee_rate_bps,
        quote_method: "orca_swapInstructions_quote_only",
        confidence: q.success ? 0.85 : 0.0,
        invalid_reason: q.success ? null : (q.error || "unknown"),
      });
    }
    await new Promise(r => setTimeout(r, 100));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "stable_pool_quote_smoke.json"),
    JSON.stringify(serializeSafe(quoteResults), null, 2)
  );

  const n_quote_pools = new Set(quoteResults.filter(r => r.quote_success).map(r => r.pool_address)).size;
  const n_10 = quoteResults.filter(r => r.notional_usd === 10 && r.quote_success).length;
  const n_20 = quoteResults.filter(r => r.notional_usd === 20 && r.quote_success).length;
  const n_100 = quoteResults.filter(r => r.notional_usd === 100 && r.quote_success).length;
  const n_high_fee = quoteResults.filter(r => r.quote_success && r.fee_bps && Number(r.fee_bps) >= 30).length;
  const summary = {
    stage: "LP_SOLANA_STABLE_POOL_RESEARCH_V1",
    run_id: process.env.RUN_ID || "",
    decoded_count: n_success,
    candidate_count: quoteResults.length,
    quote_ready_pool_count: n_quote_pools,
    quote_10u_success_count: n_10,
    quote_20u_success_count: n_20,
    quote_100u_success_count: n_100,
    high_fee_quote_ready_count: n_high_fee,
    stable_quote_ready_count: n_quote_pools,
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "decode_quote_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log("[stageGH] summary:", summary);
}

main().catch(e => {
  console.error("[stageGH] fatal:", e);
  process.exit(1);
});
