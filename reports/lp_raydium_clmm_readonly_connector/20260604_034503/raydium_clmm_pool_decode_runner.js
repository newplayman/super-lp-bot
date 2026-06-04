#!/usr/bin/env node
/* Stage G: Raydium CLMM PoolState decode via @raydium-io/raydium-sdk 1.3.1-beta.58.

For each verified Raydium CLMM pool (65 total):
  - getAccountInfo
  - PoolInfoLayout.decode
  - extract: mintA, mintB, mintDecimalsA, mintDecimalsB, tickSpacing,
             liquidity, sqrtPriceX64, tickCurrent, ammConfig

NO keypair / signer / transaction. Read-only.
*/
const fs = require("fs");
const path = require("path");
const { Connection, PublicKey } = require(require("path").join(
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

async function decodeOne(poolAddress) {
  const out = {
    pool_address: poolAddress,
    token_a: null,
    token_b: null,
    token_a_symbol_if_known: null,
    token_b_symbol_if_known: null,
    token_a_decimals: null,
    token_b_decimals: null,
    tick_spacing: null,
    current_tick: null,
    sqrt_price: null,
    liquidity: null,
    fee_rate: null,
    protocol_fee_rate: null,
    reward_infos_count: 0,
    amm_config: null,
    sdk_decode_success: false,
    confidence: 0.0,
    invalid_reason: null,
    latency_ms: null,
  };
  const t0 = Date.now();
  const conn = RPC;
  let info;
  try {
    info = await conn.getAccountInfo(new PublicKey(poolAddress), "confirmed");
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

  // PoolInfoLayout.decode handles 8-byte discriminator internally
  let decoded;
  try {
    decoded = sdk.PoolInfoLayout.decode(info.data);
  } catch (e) {
    out.invalid_reason = "decode_error: " + String(e).slice(0, 60);
    out.latency_ms = Date.now() - t0;
    return out;
  }

  out.token_a = decoded.mintA?.toBase58?.() || null;
  out.token_b = decoded.mintB?.toBase58?.() || null;
  out.token_a_decimals = Number(decoded.mintDecimalsA);
  out.token_b_decimals = Number(decoded.mintDecimalsB);
  out.tick_spacing = Number(decoded.tickSpacing);
  out.current_tick = Number(decoded.tickCurrent);
  out.sqrt_price = decoded.sqrtPriceX64?.toString?.() || null;
  out.liquidity = decoded.liquidity?.toString?.() || null;
  out.amm_config = decoded.ammConfig?.toBase58?.() || null;
  out.reward_infos_count = Array.isArray(decoded.rewardInfos) ? decoded.rewardInfos.length : 0;

  // fee_rate: in Raydium, fees are stored in amm_config (PoolFeeConfig) not in pool
  // skip for now; would need to fetch amm_config
  out.sdk_decode_success = true;
  out.confidence = 0.92;
  out.latency_ms = Date.now() - t0;
  return out;
}

async function main() {
  const chainVerify = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "raydium_clmm_pool_chain_verification.json"), "utf8"));
  const verifiedAddrs = chainVerify.filter(r => r.verified && r.selected_for_sdk_decode).map(r => r.pool_address);
  console.log("[stageG] verified pools:", verifiedAddrs.length);

  const results = [];
  for (let i = 0; i < verifiedAddrs.length; i++) {
    const r = await decodeOne(verifiedAddrs[i]);
    results.push(r);
    if ((i + 1) % 10 === 0 || i === verifiedAddrs.length - 1) {
      const n_ok = results.filter(x => x.sdk_decode_success).length;
      console.log(`[stageG] decoded ${i + 1}/${verifiedAddrs.length} success=${n_ok}`);
    }
    await new Promise(r => setTimeout(r, 80));
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "raydium_clmm_pool_snapshot.json"),
    JSON.stringify(results, null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,token_a,token_b,token_a_decimals,token_b_decimals,tick_spacing,current_tick,sqrt_price,liquidity,amm_config,reward_infos_count,sdk_decode_success,confidence,invalid_reason"
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
      r.amm_config || "",
      r.reward_infos_count ?? 0,
      r.sdk_decode_success,
      r.confidence,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(path.join(REPORT_DIR, "raydium_clmm_pool_snapshot.csv"), csvLines.join("\n") + "\n");

  const n_success = results.filter(r => r.sdk_decode_success).length;
  const summary = {
    stage: "LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    attempted_count: results.length,
    sdk_decode_success_count: n_success,
    sdk_decode_failure_count: results.length - n_success,
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
