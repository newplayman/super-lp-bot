#!/usr/bin/env node
/* Stage H: Raydium AMM v4 pool decode via v2 SDK liquidityStateV4Layout.

For each verified pool (81 total):
  - getAccountInfo
  - liquidityStateV4Layout.decode
  - read baseVault/quoteVault balances for actual reserves
  - extract: baseMint, quoteMint, baseVault, quoteVault, lpMint, baseDecimal, quoteDecimal,
             tradeFeeNumerator, tradeFeeDenominator, lpReserve, poolOpenTime

NO keypair / signer / transaction. Read-only.
*/
const fs = require("fs");
const path = require("path");
const { Connection, PublicKey } = require(require("path").join(
  "/tmp/lpbot_meteora_dlmm_sdk_overnight_20260603_174815", "node_modules",
  "@solana/web3.js"
));
const sdk = require(require("path").join(
  "/tmp/lpbot_raydium_v2_probe_20260604", "node_modules",
  "@raydium-io/raydium-sdk-v2"
));

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const RPC = new Connection("https://solana-rpc.publicnode.com", "confirmed");

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";
const SOL_MINT = "So11111111111111111111111111111111111111112";

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
    token_a_symbol_if_known: null,
    token_b_symbol_if_known: null,
    token_a_decimals: null,
    token_b_decimals: null,
    reserve_a_raw: null,
    reserve_b_raw: null,
    reserve_a_usd_proxy: null,
    reserve_b_usd_proxy: null,
    lp_mint: null,
    lp_supply: null,
    fee_bps: null,
    protocol_fee_bps: null,
    open_time: null,
    sdk_decode_success: false,
    confidence: 0.0,
    invalid_reason: null,
    latency_ms: null,
  };
  const t0 = Date.now();
  let info;
  try {
    info = await RPC.getAccountInfo(new PublicKey(poolAddress), "confirmed");
  } catch (e) {
    out.invalid_reason = "get_account_error: " + String(e).slice(0, 60);
    out.latency_ms = Date.now() - t0;
    return out;
  }
  if (!info) {
    out.invalid_reason = "account_null";
    out.latency_ms = Date.now() - t0;
    return out;
  }

  let decoded;
  try {
    decoded = sdk.liquidityStateV4Layout.decode(info.data);
  } catch (e) {
    out.invalid_reason = "decode_error: " + String(e).slice(0, 60);
    out.latency_ms = Date.now() - t0;
    return out;
  }

  out.token_a = decoded.baseMint?.toBase58?.() || null;
  out.token_b = decoded.quoteMint?.toBase58?.() || null;
  out.token_a_decimals = Number(decoded.baseDecimal);
  out.token_b_decimals = Number(decoded.quoteDecimal);
  out.lp_mint = decoded.lpMint?.toBase58?.() || null;
  out.lp_supply = bigintSafe(decoded.lpReserve);
  out.open_time = bigintSafe(decoded.poolOpenTime);

  // fee: tradeFeeNumerator / tradeFeeDenominator
  if (decoded.tradeFeeNumerator && decoded.tradeFeeDenominator) {
    const num = Number(decoded.tradeFeeDenominator) > 0 ? Number(decoded.tradeFeeDenominator) : 1;
    out.fee_bps = Math.round(Number(decoded.tradeFeeNumerator) / num * 10000);
  }
  if (decoded.swapFeeNumerator && decoded.swapFeeDenominator) {
    const num = Number(decoded.swapFeeDenominator) > 0 ? Number(decoded.swapFeeDenominator) : 1;
    out.protocol_fee_bps = Math.round(Number(decoded.swapFeeNumerator) / num * 10000);
  }

  // read baseVault + quoteVault balances
  const baseVault = decoded.baseVault?.toBase58?.();
  const quoteVault = decoded.quoteVault?.toBase58?.();
  if (baseVault && quoteVault) {
    try {
      const vaultInfos = await RPC.getMultipleAccountsInfo([
        new PublicKey(baseVault),
        new PublicKey(quoteVault),
      ], "confirmed");
      // SPL token account: data[0..32]=mint, [32..64]=owner, [64..72]=amount (u64 LE)
      for (let i = 0; i < vaultInfos.length; i++) {
        const inf = vaultInfos[i];
        if (!inf || !inf.data) continue;
        const buf = Buffer.from(inf.data);
        if (buf.length < 72) continue;
        const amount = Number(buf.readBigUInt64LE(64));
        if (i === 0) out.reserve_a_raw = amount.toString();
        else out.reserve_b_raw = amount.toString();
      }
    } catch (e) {
      out.invalid_reason = "vault_read_error: " + String(e).slice(0, 60);
    }
  }

  out.sdk_decode_success = true;
  out.confidence = 0.92;
  out.latency_ms = Date.now() - t0;
  return out;
}

async function main() {
  const chainVerify = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "raydium_cpmm_pool_chain_verification.json"), "utf8"));
  const verifiedAddrs = chainVerify.filter(r => r.verified && r.selected_for_sdk_decode).map(r => r.pool_address);
  console.log("[stageH] verified pools:", verifiedAddrs.length);

  const results = [];
  for (let i = 0; i < verifiedAddrs.length; i++) {
    const r = await decodeOne(verifiedAddrs[i]);
    results.push(r);
    if ((i + 1) % 10 === 0 || i === verifiedAddrs.length - 1) {
      const n_ok = results.filter(x => x.sdk_decode_success).length;
      console.log(`[stageH] decoded ${i + 1}/${verifiedAddrs.length} success=${n_ok}`);
    }
    await new Promise(r => setTimeout(r, 80));
  }

  // BigInt-safe serializer
  function serializeSafe(obj) {
    return JSON.parse(JSON.stringify(obj, (k, v) => (typeof v === "bigint" ? v.toString() : v)));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "raydium_cpmm_pool_snapshot.json"),
    JSON.stringify(serializeSafe(results), null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,token_a,token_b,token_a_decimals,token_b_decimals,reserve_a_raw,reserve_b_raw,lp_mint,lp_supply,fee_bps,protocol_fee_bps,open_time,sdk_decode_success,confidence,invalid_reason"
  ];
  for (const r of results) {
    csvLines.push([
      r.pool_address,
      r.token_a || "",
      r.token_b || "",
      r.token_a_decimals ?? "",
      r.token_b_decimals ?? "",
      r.reserve_a_raw ?? "",
      r.reserve_b_raw ?? "",
      r.lp_mint || "",
      r.lp_supply ?? "",
      r.fee_bps ?? "",
      r.protocol_fee_bps ?? "",
      r.open_time ?? "",
      r.sdk_decode_success,
      r.confidence,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(
    path.join(REPORT_DIR, "raydium_cpmm_pool_snapshot.csv"),
    csvLines.join("\n") + "\n"
  );

  const n_success = results.filter(r => r.sdk_decode_success).length;
  const n_stable = results.filter(r => r.sdk_decode_success && (
    (r.token_a && [USDC_MINT, USDT_MINT].includes(r.token_a)) ||
    (r.token_b && [USDC_MINT, USDT_MINT].includes(r.token_b))
  )).length;
  const n_sol = results.filter(r => r.sdk_decode_success && (
    (r.token_a && r.token_a === SOL_MINT) ||
    (r.token_b && r.token_b === SOL_MINT)
  )).length;
  const n_high_fee = results.filter(r => r.sdk_decode_success && Number(r.fee_bps) >= 30).length;
  const n_high_liq = results.filter(r => r.sdk_decode_success && r.reserve_a_raw && Number(r.reserve_a_raw) > 0 && r.reserve_b_raw && Number(r.reserve_b_raw) > 0).length;
  const summary = {
    stage: "LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    attempted_count: results.length,
    sdk_decode_success_count: n_success,
    sdk_decode_failure_count: results.length - n_success,
    high_fee_pool_count: n_high_fee,
    stable_pair_count: n_stable,
    sol_pair_count: n_sol,
    high_liquidity_pool_count: n_high_liq,
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "decode_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log("[stageH] summary:", summary);
}

main().catch(e => {
  console.error("[stageH] fatal:", e);
  process.exit(1);
});
