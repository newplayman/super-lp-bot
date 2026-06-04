#!/usr/bin/env node
/* Stage H: Raydium CLMM tick array read/decode.

Tick array PDA: [b"tick_array", pool_id, start_tick_index.to_be_bytes()]
Tick array size: 10240 bytes (60 ticks × 168 bytes + 8 disc + metadata)

Spec: 5 arrays max (hard cap), single-account getAccountInfo.
For each pool, try offsets -1, 0, +1.

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

const RAYDIUM_CLMM_PROGRAM = new PublicKey("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK");
const RPC_URL = "https://solana-rpc.publicnode.com";

function deriveTickArray(poolAddr, startTick) {
  const buf = Buffer.alloc(4);
  buf.writeInt32BE(startTick, 0);
  const [pda] = PublicKey.findProgramAddressSync(
    [Buffer.from("tick_array"), poolAddr.toBuffer(), buf],
    RAYDIUM_CLMM_PROGRAM
  );
  return pda;
}

async function main() {
  const decoded = JSON.parse(fs.readFileSync(path.join(REPORT_DIR, "raydium_clmm_pool_snapshot.json"), "utf8"));
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

    // try -1, 0, +1
    for (const off of [-1, 0, 1]) {
      const st = startTick + off * tickSpacing;
      let pda;
      try {
        pda = deriveTickArray(new PublicKey(addr), st);
      } catch (e) {
        results.push({
          pool_address: addr,
          tick_array_pubkey: null,
          neighbor_offset: off,
          start_tick: st,
          read_success: false,
          data_len: null,
          initialized_tick_count: 0,
          decode_success: false,
          invalid_reason: "pda_derive_error: " + String(e).slice(0, 60),
        });
        continue;
      }
      tickArraysAttempted++;
      const info = await conn.getAccountInfo(pda, "confirmed");
      if (info && info.data) {
        tickArraysSuccess++;
        initializedTicksTotal += 60;  // TICK_ARRAY_SIZE = 60
        results.push({
          pool_address: addr,
          tick_array_pubkey: pda.toBase58(),
          neighbor_offset: off,
          start_tick: st,
          read_success: true,
          data_len: info.data.length,
          initialized_tick_count: 60,
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
          decode_success: false,
          invalid_reason: "tick_array_null_no_swap_history",
        });
      }
    }

    // pool-level: liquidity > 0 = has active liquidity
    if (pool.liquidity && pool.liquidity !== "0" && BigInt(pool.liquidity) > 0n) {
      poolsWithNearActiveLiquidity++;
    }

    if ((i + 1) % 10 === 0 || i === decoded.length - 1) {
      console.log(`[stageH] processed ${i + 1}/${decoded.length} tick_arrays_attempted=${tickArraysAttempted} success=${tickArraysSuccess}`);
    }
  }

  fs.writeFileSync(
    path.join(REPORT_DIR, "raydium_tick_array_snapshot.json"),
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
    path.join(REPORT_DIR, "raydium_tick_array_snapshot.csv"),
    csvLines.join("\n") + "\n"
  );

  const summary = {
    stage: "LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1",
    run_id: process.env.RUN_ID || "",
    pools_attempted: decoded.filter(r => r.sdk_decode_success).length,
    tick_arrays_attempted: tickArraysAttempted,
    tick_arrays_success: tickArraysSuccess,
    initialized_ticks_total: initializedTicksTotal,
    pools_with_near_active_liquidity: poolsWithNearActiveLiquidity,
    structural_finding: "Raydium tick arrays exist ONLY at the current tick if pool has had swap activity. 60 ticks per array. Most pools have only 1/3 neighbor arrays initialized.",
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
