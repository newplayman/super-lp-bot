#!/usr/bin/env node
/* Stage G: bin liquidity + quote targeted smoke.
 *
 * Per pool:
 *   1. DLMM.create (re-decode from snapshot)
 *   2. getBinArrayKeysCoverage(lowerBinId, upperBinId) — deterministic pubkeys
 *   3. getMultipleAccountsInfo (small batch, max 5 at a time)
 *   4. For each array, parse 80 byte header + 70 Bin (96 bytes each)
 *   5. Quote 10 / 20 USD via swapQuote for both directions (USDC->token, SOL->token)
 *
 * Coverage: 5 → 9 → 15 (hard cap)
 * Notionals: 10, 20 (priority)
 * Direction: USDC/SOL → volatile token (anchor to volatile)
 *
 * NO keypair / signer / transaction. Read-only.
 */
const fs = require("fs");
const path = require("path");
const { Connection, PublicKey } = require("@solana/web3.js");
const DLMM = require("@meteora-ag/dlmm");
const BN = require("bn.js");
const { struct, u64, u128, publicKey, bool, u8 } = require("@coral-xyz/borsh");

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const RPC_URL = "https://solana-rpc.publicnode.com";
const METEORA_DLMM_PROGRAM = new PublicKey("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo");

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const SOL_MINT = "So11111111111111111111111111111111111111112";
const USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";

// Bin layout: amountX (u64), amountY (u64), price (u128), priceType (u8)... approx 96 bytes
// We'll just extract the raw 8-byte x_amount and 8-byte y_amount from each bin position.

function parseBinArray(rawBuf) {
  // rawBuf is the account.data buffer (base64 decoded)
  // The first 80 bytes are header (index u64, version u8, padding, lbPair pubkey 32)
  // Actually, exact layout: discriminator(8) + lbPair(32) + index(8) + version(1) + padding(31) = 80 bytes
  // Then 70 bins × 96 bytes each
  // Bin layout (96 bytes): amountX(8) + amountY(8) + price(32 or 16) ... approximate
  const HEADER_LEN = 80;
  const BIN_LEN = 96;
  const N_BINS = 70;
  if (!rawBuf || rawBuf.length < HEADER_LEN + BIN_LEN) {
    return null;
  }
  const out = {
    header_index: null,
    bins: [],
    bins_with_liquidity: 0,
  };
  // try to read header index (u64 at offset 40 in header; but layout can vary)
  // safer: skip header, just read bins
  for (let i = 0; i < N_BINS; i++) {
    const off = HEADER_LEN + i * BIN_LEN;
    if (off + 16 > rawBuf.length) break;
    const xAmount = Number(rawBuf.readBigUInt64LE(off));
    const yAmount = Number(rawBuf.readBigUInt64LE(off + 8));
    const hasLiq = xAmount > 0 || yAmount > 0;
    if (hasLiq) out.bins_with_liquidity++;
    out.bins.push({ xAmount, yAmount, hasLiquidity: hasLiq });
  }
  return out;
}

function getQuote(conn, pool, inAmountRawBN, swapForY) {
  // Get 5 bin arrays around active
  const activeId = pool.lbPair.activeId;
  const lower = new BN(activeId - 2 * 70);
  const upper = new BN(activeId + 2 * 70 + 69);
  const keys = DLMM.getBinArrayKeysCoverage(lower, upper, new PublicKey(pool.pubkey), METEORA_DLMM_PROGRAM);
  // Filter to closest 5 to keep it bounded
  const keys5 = keys.slice(0, 5);
  return DLMM.swapQuote(inAmountRawBN, swapForY, new BN("1"), keys5, false, 0).catch((e) => {
    return { error: String(e).slice(0, 200) };
  });
}

async function smokeOne(decoded, notionalUSD, conn) {
  const out = {
    pool_address: decoded.pool_address,
    token_pair: "",
    bin_step: decoded.bin_step,
    base_fee_bps: decoded.base_fee_bps,
    max_fee_bps: decoded.max_fee_bps,
    coverage_arrays_used: 5,
    bins_decoded: 0,
    bins_with_liquidity: 0,
    quote_10u_success: false,
    quote_20u_success: false,
    price_impact_10u: null,
    price_impact_20u: null,
    fee_10u: null,
    fee_20u: null,
    quote_ready: false,
    invalid_reason: null,
  };
  const tokenXMint = decoded.token_x;
  const tokenYMint = decoded.token_y;
  // Pick direction: if Y is USDC/USDT/SOL, swapForY=true means buying X with Y
  const yIsAnchor = [USDC_MINT, USDT_MINT, SOL_MINT].includes(tokenYMint);
  const xIsAnchor = [USDC_MINT, USDT_MINT, SOL_MINT].includes(tokenXMint);
  out.token_pair = `${tokenXMint.slice(0, 6)}…/${tokenYMint.slice(0, 6)}…`;
  if (!yIsAnchor && !xIsAnchor) {
    out.invalid_reason = "no_anchor_token_in_pair";
    return out;
  }
  // swapForY = true means we sell Y (anchor) and buy X
  // if Y is anchor, we can use swapForY=true
  // if X is anchor, we need swapForY=false (sell X, buy Y)
  const swapForY = yIsAnchor;

  // Determine raw amount for inAmount based on which token we sell
  // If swapForY=true: we sell Y. If Y is USDC, inAmount = notional * 10^6. If Y is SOL, inAmount = notional / 130 * 10^9
  // For simplicity: assume USDC anchor, notional * 10^6 raw
  let inAmount10uRaw, inAmount20uRaw;
  if (swapForY) {
    if (tokenYMint === USDC_MINT || tokenYMint === USDT_MINT) {
      inAmount10uRaw = new BN("10000000");  // 10 * 10^6
      inAmount20uRaw = new BN("20000000");  // 20 * 10^6
    } else if (tokenYMint === SOL_MINT) {
      // 10 USD worth of SOL: assume 130 USD/SOL → 10/130 SOL → 10/130 * 10^9 lamports ≈ 76923077
      inAmount10uRaw = new BN("76923077");
      inAmount20uRaw = new BN("153846154");
    } else {
      // generic 6-decimal token fallback
      inAmount10uRaw = new BN("10000000");
      inAmount20uRaw = new BN("20000000");
    }
  } else {
    if (tokenXMint === USDC_MINT || tokenXMint === USDT_MINT) {
      inAmount10uRaw = new BN("10000000");
      inAmount20uRaw = new BN("20000000");
    } else if (tokenXMint === SOL_MINT) {
      inAmount10uRaw = new BN("76923077");
      inAmount20uRaw = new BN("153846154");
    } else {
      inAmount10uRaw = new BN("10000000");
      inAmount20uRaw = new BN("20000000");
    }
  }

  // First: read bin arrays for liquidity summary
  const activeId = decoded.active_bin;
  if (activeId == null) {
    out.invalid_reason = "no_active_bin";
    return out;
  }
  const lower = new BN(activeId - 2 * 70);
  const upper = new BN(activeId + 2 * 70 + 69);
  const keys = DLMM.getBinArrayKeysCoverage(lower, upper, new PublicKey(decoded.pool_address), METEORA_DLMM_PROGRAM);
  const keys5 = keys.slice(0, 5);

  try {
    const infos = await conn.getMultipleAccountsInfo(keys5, "confirmed");
    let totalBins = 0;
    let totalWithLiq = 0;
    for (const inf of infos) {
      if (!inf || !inf.data) continue;
      const buf = Buffer.from(inf.data);
      const parsed = parseBinArray(buf);
      if (parsed) {
        totalBins += parsed.bins.length;
        totalWithLiq += parsed.bins_with_liquidity;
      }
    }
    out.bins_decoded = totalBins;
    out.bins_with_liquidity = totalWithLiq;
  } catch (e) {
    out.invalid_reason = "bin_array_read_error: " + String(e).slice(0, 60);
    return out;
  }

  // Now quote: 10 USD and 20 USD
  // We need a pool object for swapQuote
  let pool;
  try {
    pool = await DLMM.create(conn, new PublicKey(decoded.pool_address));
    pool.pubkey = decoded.pool_address;  // tag for helper
  } catch (e) {
    out.invalid_reason = "dlmm_recreate_error";
    return out;
  }
  // Re-derive keys for swapQuote (use active bin arrays)
  const lower2 = new BN(activeId - 2 * 70);
  const upper2 = new BN(activeId + 2 * 70 + 69);
  const swapKeys = DLMM.getBinArrayKeysCoverage(lower2, upper2, new PublicKey(decoded.pool_address), METEORA_DLMM_PROGRAM).slice(0, 5);

  // swapQuote is an INSTANCE method on the pool, not a static DLMM function
  // It needs BinArrayAccount[] (decoded shape), not raw PublicKey[]
  // First read accounts and decode via SDK's decodeAccount
  let swapBinArrays = [];
  try {
    const infos = await conn.getMultipleAccountsInfo(swapKeys, "confirmed");
    const program = DLMM.createProgram(conn);
    for (let i = 0; i < infos.length; i++) {
      const inf = infos[i];
      if (!inf || !inf.data) continue;
      const buf = Buffer.from(inf.data);
      const ba = DLMM.decodeAccount(program, "binArray", buf);
      swapBinArrays.push({ publicKey: swapKeys[i], account: ba });
    }
  } catch (e) {
    out.invalid_reason = "bin_array_decode_error: " + String(e).slice(0, 60);
    return out;
  }
  if (swapBinArrays.length === 0) {
    out.invalid_reason = "no_bin_arrays_decoded";
    return out;
  }

  try {
    const q10 = await pool.swapQuote(inAmount10uRaw, swapForY, new BN("1"), swapBinArrays, false, 0);
    if (q10 && !q10.error) {
      out.quote_10u_success = true;
      if (q10.outAmount != null) out.price_impact_10u = q10.outAmount.toString();
      if (q10.fee != null) out.fee_10u = q10.fee.toString();
    }
  } catch (e) {
    out.invalid_reason = "quote_10u_error: " + String(e).slice(0, 60);
  }
  try {
    const q20 = await pool.swapQuote(inAmount20uRaw, swapForY, new BN("1"), swapBinArrays, false, 0);
    if (q20 && !q20.error) {
      out.quote_20u_success = true;
      if (q20.outAmount != null) out.price_impact_20u = q20.outAmount.toString();
      if (q20.fee != null) out.fee_20u = q20.fee.toString();
    }
  } catch (e) {
    if (!out.invalid_reason) out.invalid_reason = "quote_20u_error: " + String(e).slice(0, 60);
  }
  out.quote_ready = out.quote_10u_success || out.quote_20u_success;
  return out;
}

async function main() {
  const snapshot = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "meteora_targeted_pool_snapshot.json"), "utf8"));
  // Only consider pools with base_fee_bps >= 20 OR bin_step >= 20 (loose prefilter)
  const candidate = snapshot.filter((r) => r.sdk_decode_success && (r.base_fee_bps >= 20 || r.bin_step >= 20));
  console.log(`[stageG] candidate for quote: ${candidate.length} (out of ${snapshot.length} decoded)`);

  const conn = new Connection(RPC_URL, "confirmed");
  const results = [];
  for (let i = 0; i < candidate.length; i++) {
    const r = await smokeOne(candidate[i], 10, conn);
    results.push(r);
    if ((i + 1) % 5 === 0 || i === candidate.length - 1) {
      const q = results.filter((x) => x.quote_ready).length;
      console.log(`[stageG] smoke ${i + 1}/${candidate.length} quote_ready=${q}`);
    }
    await new Promise((res) => setTimeout(res, 80));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "meteora_targeted_quote_readiness.json"),
    JSON.stringify(results, null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,token_pair,bin_step,base_fee_bps,max_fee_bps,coverage_arrays_used,bins_decoded,bins_with_liquidity,quote_10u_success,quote_20u_success,price_impact_10u,price_impact_20u,fee_10u,fee_20u,quote_ready,invalid_reason"
  ];
  for (const r of results) {
    csvLines.push([
      r.pool_address,
      r.token_pair,
      r.bin_step ?? "",
      r.base_fee_bps ?? "",
      r.max_fee_bps ?? "",
      r.coverage_arrays_used,
      r.bins_decoded,
      r.bins_with_liquidity,
      r.quote_10u_success,
      r.quote_20u_success,
      r.price_impact_10u ?? "",
      r.price_impact_20u ?? "",
      r.fee_10u ?? "",
      r.fee_20u ?? "",
      r.quote_ready,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(path.join(REPORT_DIR, "meteora_targeted_quote_readiness.csv"), csvLines.join("\n") + "\n");

  const n_quote = results.filter((r) => r.quote_ready).length;
  const n_10 = results.filter((r) => r.quote_10u_success).length;
  const n_20 = results.filter((r) => r.quote_20u_success).length;
  const n_no_liq = results.filter((r) => r.bins_with_liquidity === 0 && r.bins_decoded > 0).length;
  const n_high_fee_quote = results.filter((r) => r.quote_ready && (r.base_fee_bps >= 50 || r.max_fee_bps >= 2000)).length;
  const summary = {
    stage: "LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1",
    run_id: process.env.RUN_ID || "",
    candidate_count: results.length,
    quote_ready_pool_count: n_quote,
    quote_10u_success_count: n_10,
    quote_20u_success_count: n_20,
    high_fee_quote_ready_count: n_high_fee_quote,
    no_liquidity_near_active_count: n_no_liq,
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "quote_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log(`[stageG] summary:`, summary);
}

main().catch((e) => {
  console.error("[stageG] fatal:", e);
  process.exit(1);
});
