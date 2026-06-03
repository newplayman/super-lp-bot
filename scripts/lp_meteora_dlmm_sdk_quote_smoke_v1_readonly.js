#!/usr/bin/env node
/**
 * LP_METEORA_DLMM_SDK_QUOTE_SMOKE_V1_READONLY
 *
 * Read-only quote simulation for Meteora DLMM via @meteora-ag/dlmm SDK.
 *
 * STRICTLY read-only:
 *   - No keypair / signer / transaction / sendTransaction
 *   - No wallet adapter
 *   - swapQuote returns a *quote* object; we DO NOT build or send a transaction
 *
 * Note: swapQuote requires pre-fetched binArrays (BinArrayAccount[]). On public
 * RPC, the underlying getBinArrayForSwap is often 403/410. We capture the error
 * honestly and continue.
 *
 * Usage:
 *   NODE_PATH=/tmp/lpbot_meteora_dlmm_sdk_probe_${RUN_ID}/node_modules node \
 *     scripts/lp_meteora_dlmm_sdk_quote_smoke_v1_readonly.js \
 *     <pool1> [<pool2> ...] <output.json>
 */
"use strict";

const fs = require("fs");
const path = require("path");
const DLMM = require("@meteora-ag/dlmm");
const { Connection, PublicKey, Keypair } = require("@solana/web3.js");
// Note: Keypair is imported by the SDK itself, but we do NOT instantiate it.
// We use an ephemeral random PublicKey as the "user" for swapQuote (some SDK
// versions require a user for slippage calculation; we do NOT sign anything).

const PRIMARY_RPC = "https://solana.publicnode.com";
const FALLBACK_RPC = "https://api.mainnet-beta.solana.com";

// Notionals (raw). For 10 USDT of USDC (6 decimals): 10 * 1e6 = 10_000_000
// For 20 USDT of USDC (6 decimals): 20 * 1e6 = 20_000_000
const NOTIONALS = [
  { name: "10USDC", amount: 10_000_000, token: "USDC" },
  { name: "20USDC", amount: 20_000_000, token: "USDC" },
];

function now() { return Date.now(); }

async function withFallback(thunk) {
  try {
    return await thunk(new Connection(PRIMARY_RPC, "confirmed"));
  } catch (e1) {
    const msg1 = String(e1?.message ?? e1);
    if (msg1.includes("403") || msg1.includes("429") || msg1.includes("fetch failed") || msg1.includes("410")) {
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
  try { return [await fn(), null]; }
  catch (e) { return [null, String(e?.message ?? e)]; }
}

function bnOrZero(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v;
  if (typeof v === "object" && typeof v.toString === "function") return v.toString();
  return String(v);
}

async function quoteOnePool(poolAddress, notional) {
  const t0 = now();
  const result = {
    pool_address: poolAddress,
    notional_usd_approx: notional.name,
    notional_amount_raw: notional.amount,
    quote_token_in: notional.token,
    quote_success: false,
    amount_in_raw: null,
    amount_out_raw: null,
    price_impact: null,
    fee: null,
    bin_crossed: null,
    quote_method: "dlmmPool.swapQuote",
    swap_y_to_x: null,
    confidence: 0.0,
    latency_ms: 0,
    error: null,
    error_stage: null,
  };

  try {
    const [dlmmPool, createErr] = await safeCall(() =>
      withFallback((connection) =>
        DLMM.create(connection, new PublicKey(poolAddress), { cluster: "mainnet-beta" })
      )
    );
    if (!dlmmPool) {
      result.error = createErr;
      result.error_stage = "DLMM.create";
      result.latency_ms = now() - t0;
      return result;
    }

    // Determine if Y is USDC (so we know which direction to swap)
    const yMint = dlmmPool.tokenY?.publicKey?.toBase58?.();
    const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
    const swapYtoX = (yMint === USDC); // if Y is USDC, swap Y (USDC) for X
    result.swap_y_to_x = swapYtoX;
    result.amount_in_raw = notional.amount.toString();

    // Get bin arrays for swap direction
    const [binArrays, baErr] = await safeCall(() =>
      withFallback((c) => dlmmPool.getBinArrayForSwap(swapYtoX, 4))
    );
    if (!binArrays) {
      result.error = baErr;
      result.error_stage = "getBinArrayForSwap";
      result.latency_ms = now() - t0;
      return result;
    }

    // swapQuote (read-only; returns SwapQuote object with in/out amounts)
    // Allowed slippage: 50 bps (0.5%); isPartialFill: false
    const { BN } = require("@coral-xyz/anchor");
    const inAmount = new BN(notional.amount);
    const allowedSlippage = new BN(50);
    const [quote, qErr] = await safeCall(() =>
      dlmmPool.swapQuote(inAmount, swapYtoX, allowedSlippage, binArrays, false, 3)
    );
    if (!quote) {
      result.error = qErr;
      result.error_stage = "swapQuote";
      result.latency_ms = now() - t0;
      return result;
    }

    result.quote_success = true;
    result.amount_out_raw = bnOrZero(quote.outAmount);
    result.fee = bnOrZero(quote.totalFeeAmount);
    result.bin_crossed = quote.binArraysCovered ?? null;
    result.confidence = 0.9;
  } catch (e) {
    result.error = String(e?.message ?? e);
    result.error_stage = result.error_stage ?? "unknown";
  }
  result.latency_ms = now() - t0;
  return result;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("usage: lp_meteora_dlmm_sdk_quote_smoke_v1_readonly.js <pool1> [<pool2> ...] <output.json>");
    process.exit(2);
  }
  const outputPath = args[args.length - 1];
  const pools = args.slice(0, -1);

  const results = [];
  for (const p of pools) {
    for (const n of NOTIONALS) {
      const r = await quoteOnePool(p, n);
      results.push(r);
    }
  }

  const quoteSuccess = results.filter((r) => r.quote_success).length;
  const out = {
    smoke_attempted: true,
    smoke_success: quoteSuccess > 0,
    quote_success_count: quoteSuccess,
    quote_attempted_count: results.length,
    rpc_url_primary: PRIMARY_RPC,
    rpc_url_fallback: FALLBACK_RPC,
    sdk_package: "@meteora-ag/dlmm",
    sdk_package_version: "1.9.10",
    cluster: "mainnet-beta",
    results,
    timestamp_utc: new Date().toISOString(),
    solana_wallet_or_keypair_touched: false,
    transaction_sent: false,
    signer_used: false,
    wallet_adapter_used: false,
    swap_transaction_built: false,
  };

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(out, null, 2));
  console.log(`quote smoke wrote ${outputPath} (success=${quoteSuccess}/${results.length})`);
  process.exit(out.smoke_success ? 0 : 1);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(3);
});
