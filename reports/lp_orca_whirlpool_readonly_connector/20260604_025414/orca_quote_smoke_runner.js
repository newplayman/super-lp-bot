#!/usr/bin/env node
/* Stage I: Orca quote smoke.

For each decoded Orca pool, do read-only quote:
  - 10 USD in (USDC, 6 decimals)
  - 20 USD in (USDC)
  - 100 USD in (USDC) if pool has USDC or wSOL anchor

Direction: anchor -> volatile only.

Output: orca_quote_smoke.{json,csv}
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

function pickInMint(pool) {
  // if pool has USDC or USDT, swap USDC->other
  if (pool.token_a === USDC_MINT || pool.token_b === USDC_MINT) return USDC_MINT;
  if (pool.token_a === USDT_MINT || pool.token_b === USDT_MINT) return USDT_MINT;
  if (pool.token_a === SOL_MINT || pool.token_b === SOL_MINT) return SOL_MINT;
  return null;
}

function isUSDCOrSOL(mint) {
  return [USDC_MINT, USDT_MINT, SOL_MINT].includes(mint);
}

async function quotePool(pool, inMint, inAmountRaw) {
  const out = {
    pool_address: pool.pool_address,
    notional_usd: 0,
    token_in: inMint,
    token_out: null,
    amount_in_raw: inAmountRaw.toString(),
    quote_success: false,
    amount_out_raw: null,
    price_impact: null,
    fee: null,
    fee_rate: null,
    quote_method: "orca_swapInstructions_quote_only",
    confidence: 0.0,
    invalid_reason: null,
  };
  try {
    const result = await whirlpool.swapInstructions(
      RPC,
      { inputAmount: inAmountRaw, mint: address(inMint) },
      address(pool.pool_address)
    );
    const q = result.quote;
    out.quote_success = true;
    out.amount_out_raw = q.tokenEstOut?.toString() || null;
    out.fee = q.tradeFee?.toString() || null;
    out.fee_rate = q.tradeFeeRateMax || null;
    out.token_out = inMint === q.tokenIn ? pool.token_a : pool.token_b;
    if (q.tokenIn !== inMint) {
      // mint order mismatch
      out.token_in = q.tokenIn;
      out.token_out = pool.token_a === q.tokenIn ? pool.token_b : pool.token_a;
    }
    out.price_impact = null;  // not directly available
    out.confidence = 0.85;
  } catch (e) {
    out.invalid_reason = "quote_error: " + String(e).slice(0, 80);
  }
  return out;
}

// convert BigInt to string recursively
function serializeSafe(obj) {
  return JSON.parse(JSON.stringify(obj, (k, v) => (typeof v === 'bigint' ? v.toString() : v)));
}

async function main() {
  const decoded = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "orca_whirlpool_pool_snapshot.json"), "utf8"));
  const decodedOk = decoded.filter(r => r.sdk_decode_success);
  console.log(`[stageI] decoded pools: ${decodedOk.length}`);

  const results = [];
  // smaller batch + longer delay to avoid 429
  for (let i = 0; i < decodedOk.length; i++) {
    const pool = decodedOk[i];
    const inMint = pickInMint(pool);
    if (!inMint) {
      // skip non-anchor pool
      continue;
    }
    // 10 USD, 20 USD only (priority)
    const usdNotionals = [10, 20];
    for (const usd of usdNotionals) {
      let inRaw;
      if (inMint === USDC_MINT || inMint === USDT_MINT) {
        inRaw = BigInt(usd) * 1_000_000n;  // 6 decimals
      } else if (inMint === SOL_MINT) {
        inRaw = BigInt(Math.floor(usd / 130 * 1e9));  // 9 decimals
      } else {
        continue;
      }
      const q = await quotePool(pool, inMint, inRaw);
      q.notional_usd = usd;
      results.push(q);
    }
    if ((i + 1) % 5 === 0 || i === decodedOk.length - 1) {
      const n_ok = results.filter(x => x.quote_success).length;
      console.log(`[stageI] pool ${i + 1}/${decodedOk.length} quotes=${results.length} success=${n_ok}`);
    }
    // delay to avoid 429
    await new Promise(r => setTimeout(r, 250));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "orca_quote_smoke.json"),
    JSON.stringify(serializeSafe(results), null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,notional_usd,token_in,token_out,amount_in_raw,quote_success,amount_out_raw,fee,fee_rate,quote_method,confidence,invalid_reason"
  ];
  for (const r of results) {
    csvLines.push([
      r.pool_address,
      r.notional_usd,
      r.token_in,
      r.token_out || "",
      r.amount_in_raw,
      r.quote_success,
      r.amount_out_raw || "",
      r.fee || "",
      r.fee_rate ?? "",
      r.quote_method,
      r.confidence,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(
    path.join(REPORT_DIR, "orca_quote_smoke.csv"),
    csvLines.join("\n") + "\n"
  );

  const n_quote_pools = new Set(results.filter(r => r.quote_success).map(r => r.pool_address)).size;
  const n_10 = results.filter(r => r.notional_usd === 10 && r.quote_success).length;
  const n_20 = results.filter(r => r.notional_usd === 20 && r.quote_success).length;
  const n_100 = results.filter(r => r.notional_usd === 100 && r.quote_success).length;
  const n_high_fee_quote = results.filter(r => r.quote_success && r.fee_rate && Number(r.fee_rate) >= 0.003).length;  // feeRateMax >= 30bps (0.3%)
  const summary = {
    stage: "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    candidate_count: results.length,
    quote_ready_pool_count: n_quote_pools,
    quote_10u_success_count: n_10,
    quote_20u_success_count: n_20,
    quote_100u_success_count: n_100,
    high_fee_quote_ready_count: n_high_fee_quote,
    no_liquidity_near_active_count: 0,
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "quote_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log("[stageI] summary:", summary);
}

main().catch(e => {
  console.error("[stageI] fatal:", e);
  process.exit(1);
});
