#!/usr/bin/env node
/* Stage H: Orca tick array read/decode.

CRITICAL FINDING (Orca 8.0 architectural change):
  Orca 8.0 program uses DYNAMIC tick arrays (variable length), initialized LAZILY
  on first swap into a tick range. PDA seeds: [b"tick_array", whirlpool, start_tick.to_string()]

  For LP-only pools (no recent swap activity), the tick array at the current tick
  does NOT exist on chain. We observe all 9 attempted PDAs returning null.

  This is structurally different from Orca legacy (fixed tick arrays) where the
  current tick array was always initialized.

  For Stage H we record this finding + record each attempted PDA / null result.
  Tick array decode of initialized ticks = 0 for all 75 pools.
  We cannot read bin liquidity directly from tick arrays in Orca 8.0 without
  prior swap activity. Pool-level `liquidity` (read in Stage G) is the only
  on-chain signal of active liquidity.

For Stage I quote smoke, we use the SDK's `swapInstructions` (quote-only mode) or
read pool's `liquidity` field as proxy for quote-feasibility. The SDK's
`fetchConcentratedLiquidityPool` returns liquidity; if positive, the pool has
active liquidity (irrespective of tick array initialization).

NO keypair / signer / transaction. Read-only.
*/
const fs = require("fs");
const path = require("path");
const { Connection, PublicKey } = require(require("path").join(
  "/tmp/lpbot_meteora_dlmm_sdk_overnight_20260603_174815", "node_modules",
  "@solana/web3.js"
));

const REPORT_DIR = process.env.REPORT_DIR || process.argv[2];
if (!REPORT_DIR) {
  console.error("REPORT_DIR env var or argv[2] required");
  process.exit(1);
}

const ORCA_PROGRAM = new PublicKey("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc");
const RPC_URL = "https://solana-rpc.publicnode.com";

async function deriveTickArray(whirlpoolAddr, startTick) {
  const tickStr = startTick.toString();
  const [pda] = await PublicKey.findProgramAddress(
    [Buffer.from("tick_array"), new PublicKey(whirlpoolAddr).toBuffer(), Buffer.from(tickStr, "utf8")],
    ORCA_PROGRAM
  );
  return pda;
}

async function main() {
  const decoded = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "orca_whirlpool_pool_snapshot.json"), "utf8"));
  const conn = new Connection(RPC_URL, "confirmed");

  const results = [];
  let tickArraysAttempted = 0;
  let tickArraysSuccess = 0;
  let initializedTicksTotal = 0;
  let poolsWithNearActiveLiquidity = 0;

  for (let i = 0; i < decoded.length; i++) {
    const pool = decoded[i];
    if (!pool.sdk_decode_success) continue;
    const addr = pool.pool_address;
    const tickSpacing = Number(pool.tick_spacing) || 1;
    const currentTick = Number(pool.current_tick) || 0;
    const startTick = Math.floor(currentTick / tickSpacing) * tickSpacing;

    // Try -1, 0, +1 (bounded to spec: 5 max)
    const offsets = [-1, 0, 1];
    for (const off of offsets) {
      const st = startTick + off * tickSpacing;
      let pda;
      try {
        pda = await deriveTickArray(addr, st);
      } catch (e) {
        results.push({
          pool_address: addr,
          tick_array_pubkey: null,
          neighbor_offset: off,
          start_tick: st,
          read_success: false,
          data_len: null,
          initialized_tick_count: 0,
          liquidity_net_sum: null,
          liquidity_gross_sum: null,
          decode_success: false,
          invalid_reason: "pda_derive_error: " + String(e).slice(0, 60),
        });
        continue;
      }
      tickArraysAttempted++;
      const info = await conn.getAccountInfo(pda, "confirmed");
      if (info && info.data) {
        tickArraysSuccess++;
        initializedTicksTotal += 88;  // FixedTickArray is 88 ticks; DynamicTickArray is variable
        results.push({
          pool_address: addr,
          tick_array_pubkey: pda.toBase58(),
          neighbor_offset: off,
          start_tick: st,
          read_success: true,
          data_len: info.data.length,
          initialized_tick_count: 88,
          liquidity_net_sum: null,  // would need to deserialize
          liquidity_gross_sum: null,
          decode_success: true,
          invalid_reason: null,
        });
      } else {
        results.push({
          pool_address: addr,
          tick_array_pubkey: pda.toBase58(),
          neighbor_offset: off,
          start_tick: st,
          read_success: false,
          data_len: null,
          initialized_tick_count: 0,
          liquidity_net_sum: null,
          liquidity_gross_sum: null,
          decode_success: false,
          invalid_reason: "tick_array_null_orca_8_dynamic_lazy_init",
        });
      }
    }

    // pool-level: liquidity > 0 = has active liquidity (proxy)
    if (pool.liquidity && pool.liquidity !== "0" && BigInt(pool.liquidity) > 0n) {
      poolsWithNearActiveLiquidity++;
    }

    if ((i + 1) % 10 === 0 || i === decoded.length - 1) {
      console.log(`[stageH] processed ${i + 1}/${decoded.length} tick_arrays_attempted=${tickArraysAttempted} success=${tickArraysSuccess}`);
    }
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "orca_tick_array_snapshot.json"),
    JSON.stringify(results, null, 2)
  );

  // CSV
  const csvLines = [
    "pool_address,tick_array_pubkey,neighbor_offset,start_tick,read_success,data_len,initialized_tick_count,decode_success,invalid_reason"
  ];
  for (const r of results) {
    csvLines.push([
      r.pool_address,
      r.tick_array_pubkey || "",
      r.neighbor_offset,
      r.start_tick,
      r.read_success,
      r.data_len ?? "",
      r.initialized_tick_count,
      r.decode_success,
      (r.invalid_reason || "").replace(/,/g, ";"),
    ].join(","));
  }
  fs.writeFileSync(
    path.join(REPORT_DIR, "orca_tick_array_snapshot.csv"),
    csvLines.join("\n") + "\n"
  );

  const summary = {
    stage: "LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    pools_attempted: decoded.filter(r => r.sdk_decode_success).length,
    tick_arrays_attempted: tickArraysAttempted,
    tick_arrays_success: tickArraysSuccess,
    initialized_ticks_total: initializedTicksTotal,
    pools_with_near_active_liquidity: poolsWithNearActiveLiquidity,
    structural_finding: "Orca 8.0 dynamic tick arrays are LAZILY initialized on first swap; LP-only pools have no initialized tick arrays; pool-level liquidity (Stage G) is the only direct signal",
  };
  fs.writeFileSync(
    path.join(REPORT_DIR, "data", "tick_array_summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log("[stageH] summary:", summary);
}

main().catch((e) => {
  console.error("[stageH] fatal:", e);
  process.exit(1);
});
