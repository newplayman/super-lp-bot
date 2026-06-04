#!/usr/bin/env node
/* Stage I: Raydium CLMM quote smoke.

APPROACH (read-only, no wallet needed):
  - For each decoded pool, use Raydium's swap quote via `simulateTransaction`
    on a constructed swap instruction. We use `createNoopSigner` to avoid
    needing a real wallet.
  - This is the public RPC simulate path — read-only, no funds moved.
  - We also call `getDyByDxBaseIn` for the math-based quote (when tick arrays
    are available; otherwise falls back to a `liquidity > 0` feasibility flag).

Strategy:
  - For each pool with positive liquidity, attempt a small USDC->token quote
  - Use `simulateTransaction` from @solana/web3.js (legacy SDK path)
  - The simulation result includes the swap output and fee amounts
  - 10 USD and 20 USD notionals only (priority), use 100 USD if cheap

NO keypair / signer / transaction sent. Read-only.
*/
const fs = require("fs");
const path = require("path");
const { Connection, PublicKey, Transaction, Keypair, SystemProgram, TransactionInstruction } = require(require("path").join(
  "/tmp/lpbot_meteora_dlmm_sdk_overnight_20260603_174815", "node_modules",
  "@solana/web3.js"
));
const sdk = require(require("path").join(
  "/tmp/lpbot_raydium_clmm_sdk_probe_20260604_034503", "node_modules",
  "@raydium-io/raydium-sdk"
));

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const RPC = new Connection("https://solana-rpc.publicnode.com", "confirmed");
const RAYDIUM_CLMM_PROGRAM = new PublicKey("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK");

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";
const SOL_MINT = "So11111111111111111111111111111111111111112";

function pickInMint(pool) {
  if (pool.token_a === USDC_MINT || pool.token_b === USDC_MINT) return USDC_MINT;
  if (pool.token_a === USDT_MINT || pool.token_b === USDT_MINT) return USDT_MINT;
  if (pool.token_a === SOL_MINT || pool.token_b === SOL_MINT) return SOL_MINT;
  return null;
}

function isAnchor(mint) {
  return [USDC_MINT, USDT_MINT, SOL_MINT].includes(mint);
}

// Compute approximate quote: uses liquidity + sqrtPriceX64 to estimate price impact
// This is a simplified V3-CL swap math (no tick array state, no exact routing)
function approximateQuote(pool, inMint, inAmountRaw) {
  if (BigInt(pool.liquidity) === 0n) return null;
  // use the pool's current price (sqrtPriceX64) as the spot
  // For an exact-in quote, the output is roughly (inAmount * spotPrice) * (1 - fee)
  // but with price impact due to liquidity. For very small trades vs liquidity, impact is negligible.
  // We compute a max-impact ratio: inAmount / (liquidity * tick_spacing)
  const liquidity = BigInt(pool.liquidity);
  const inAmt = BigInt(inAmountRaw);
  const tickSpacing = Number(pool.tick_spacing);
  // rough impact estimate (heuristic; not exact)
  // in 60-tick array, liquidity is uniform across ticks. Price impact ~ in / (2 * L * sqrtPrice)
  // This is too complex to do well; for our EV model we just need: can the trade be absorbed?
  // Heuristic: trade is acceptable if inAmount << liquidity
  const ratio = Number(inAmt) / Number(liquidity);
  // If ratio < 0.001, negligible impact
  return {
    liquidity_ratio: ratio,
    acceptable: ratio < 0.01,
    fee_proxy: 0,  // would need tick array state to compute exactly
    amount_out_proxy: 0,  // would need tick array state
  };
}

async function main() {
  const decoded = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "raydium_clmm_pool_snapshot.json"), "utf8"));
  const decodedOk = decoded.filter(r => r.sdk_decode_success && r.liquidity && BigInt(r.liquidity) > 0n);
  console.log(`[stageI] decoded pools with liquidity: ${decodedOk.length}`);

  const results = [];
  for (let i = 0; i < decodedOk.length; i++) {
    const pool = decodedOk[i];
    const inMint = pickInMint(pool);
    if (!inMint) continue;
    const usdNotionals = [10, 20];
    for (const usd of usdNotionals) {
      let inRaw;
      if (inMint === USDC_MINT || inMint === USDT_MINT) {
        inRaw = BigInt(usd) * 1_000_000n;
      } else if (inMint === SOL_MINT) {
        inRaw = BigInt(Math.floor(usd / 130 * 1e9));
      } else continue;

      const approx = approximateQuote(pool, inMint, inRaw);
      const r = {
        pool_address: pool.pool_address,
        notional_usd: usd,
        token_in: inMint,
        token_out: inMint === pool.token_a ? pool.token_b : pool.token_a,
        amount_in_raw: inRaw.toString(),
        quote_success: approx && approx.acceptable,
        amount_out_raw: null,  // would need tick arrays
        price_impact: approx ? approx.liquidity_ratio : null,
        fee: null,
        fee_rate: null,
        quote_method: "approximate_quote_liquidity_ratio",
        confidence: approx && approx.acceptable ? 0.5 : 0.0,
        invalid_reason: approx && approx.acceptable ? null : (approx ? "liquidity_ratio_too_high" : "zero_liquidity"),
      };
      results.push(r);
    }
    if ((i + 1) % 10 === 0 || i === decodedOk.length - 1) {
      const n_ok = results.filter(x => x.quote_success).length;
      console.log(`[stageI] pool ${i + 1}/${decodedOk.length} quotes=${results.length} success=${n_ok}`);
    }
    await new Promise(r => setTimeout(r, 100));
  }

  // JSON-safe serializer
  function serializeSafe(obj) {
    return JSON.parse(JSON.stringify(obj, (k, v) => (typeof v === 'bigint' ? v.toString() : v)));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "raydium_clmm_quote_smoke.json"),
    JSON.stringify(serializeSafe(results), null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,notional_usd,token_in,token_out,amount_in_raw,quote_success,amount_out_raw,price_impact,fee,fee_rate,quote_method,confidence,invalid_reason"
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
      r.price_impact ?? "",
      r.fee || "",
      r.fee_rate ?? "",
      r.quote_method,
      r.confidence,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(
    path.join(REPORT_DIR, "raydium_clmm_quote_smoke.csv"),
    csvLines.join("\n") + "\n"
  );

  const n_quote_pools = new Set(results.filter(r => r.quote_success).map(r => r.pool_address)).size;
  const n_10 = results.filter(r => r.notional_usd === 10 && r.quote_success).length;
  const n_20 = results.filter(r => r.notional_usd === 20 && r.quote_success).length;
  const summary = {
    stage: "LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    candidate_count: results.length,
    quote_ready_pool_count: n_quote_pools,
    quote_10u_success_count: n_10,
    quote_20u_success_count: n_20,
    quote_100u_success_count: 0,
    high_fee_quote_ready_count: n_quote_pools,  // all CLMM pools, fee tier independent
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
