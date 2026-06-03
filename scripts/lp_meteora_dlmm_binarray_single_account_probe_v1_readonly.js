#!/usr/bin/env node
/**
 * LP_METEORA_DLMM_BINARRAY_SINGLE_ACCOUNT_PROBE_V1_READONLY
 *
 * Read-only bin array PDA derivation + single-account getAccountInfo smoke.
 *
 * STRICTLY read-only:
 *   - No keypair / signer / wallet adapter
 *   - No transaction construction / sendTransaction
 *   - No swap tx builder / open_lp / close_lp / collect_fee / bridge
 *   - SDK is loaded from a /tmp isolated install dir (NOT repo root)
 *
 * Stages performed:
 *   D: derive active + neighbor -1/+1 bin array PDA for each known pool
 *   E: single-account getAccountInfo on each derived pubkey
 *   F: small-batch getMultipleAccounts (1 + 3 accounts) if E partial
 *   G: bin array decode via SDK (if E or F succeeded)
 *
 * Usage:
 *   NODE_PATH=/tmp/lpbot_meteora_dlmm_sdk_probe_<RUN_ID>/node_modules node \
 *     scripts/lp_meteora_dlmm_binarray_single_account_probe_v1_readonly.js \
 *     --run-id <RUN_ID> \
 *     --output-dir <DIR> \
 *     --rpc-url-redacted-source <label> \
 *     --known-pool-feed <PATH_TO_meteora_dlmm_known_pool_universe.json> \
 *     --pool-snapshot <PATH_TO_meteora_pool_snapshot.json>
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { BN } = require("@coral-xyz/anchor");
const DLMM = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");

// Helper functions imported via SDK's barrel export
const { binIdToBinArrayIndex, deriveBinArray, getBinArrayLowerUpperBinId } = DLMM;

const PRIMARY_RPC = "https://solana.publicnode.com";
const FALLBACK_RPC = "https://api.mainnet-beta.solana.com";
const DLMM_PROGRAM_ID = new PublicKey("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo");

function now() { return Date.now(); }

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const k = a.slice(2);
      args[k] = argv[i + 1];
      i++;
    }
  }
  return args;
}

function csvEscape(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (s.includes(",") || s.includes("\"") || s.includes("\n")) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function writeCsv(filePath, header, rows) {
  const lines = [header.join(",")];
  for (const r of rows) lines.push(header.map((h) => csvEscape(r[h])).join(","));
  fs.writeFileSync(filePath, lines.join("\n") + "\n");
}

async function withFallback(thunk) {
  try {
    return await thunk(new Connection(PRIMARY_RPC, "confirmed"));
  } catch (e1) {
    const msg1 = String(e1?.message ?? e1);
    if (msg1.includes("403") || msg1.includes("429") || msg1.includes("fetch failed") || msg1.includes("410")) {
      try {
        return await thunk(new Connection(FALLBACK_RPC, "confirmed"));
      } catch (e2) { throw e2; }
    }
    throw e1;
  }
}

async function safeCall(fn) {
  try { return [await fn(), null]; }
  catch (e) { return [null, String(e?.message ?? e)]; }
}

function bnToInt(bn) {
  if (bn === null || bn === undefined) return null;
  if (typeof bn === "number") return bn;
  if (typeof bn.toNumber === "function") return bn.toNumber();
  return Number(bn.toString());
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runId = args["run-id"] || "unknown";
  const outputDir = args["output-dir"] || `reports/lp_meteora_dlmm_quote_binarray_fix/${runId}/connector_output`;
  const rpcRedacted = args["rpc-url-redacted-source"] || "<redacted_public_rpc>";
  const knownPoolFeedPath = args["known-pool-feed"];
  const poolSnapshotPath = args["pool-snapshot"];

  if (!knownPoolFeedPath || !fs.existsSync(knownPoolFeedPath)) {
    console.error("ERROR: --known-pool-feed <PATH> required");
    process.exit(2);
  }
  if (!poolSnapshotPath || !fs.existsSync(poolSnapshotPath)) {
    console.error("ERROR: --pool-snapshot <PATH> required");
    process.exit(2);
  }

  fs.mkdirSync(outputDir, { recursive: true });
  const logLines = [];
  function log(s) { const line = `[${new Date().toISOString()}] ${s}`; console.log(line); logLines.push(line); }
  log(`binarray_single_account_probe started: run_id=${runId} rpc_redacted=${rpcRedacted}`);

  // Load known pool feed + pool snapshot
  const feed = JSON.parse(fs.readFileSync(knownPoolFeedPath, "utf8"));
  const snapshot = JSON.parse(fs.readFileSync(poolSnapshotPath, "utf8"));
  const selected = feed.pools.filter((p) => p.selected_for_snapshot);
  const snapshotByAddr = {};
  for (const s of snapshot) snapshotByAddr[s.pool_address] = s;

  // === Stage D: derive bin array PDAs ===
  log("=== Stage D: bin array PDA derivation ===");
  const derivations = []; // rows for CSV
  const derivationByPool = {}; // pool_addr -> [{ offset, index, pubkey, success }]
  for (const p of selected) {
    const snap = snapshotByAddr[p.pool_address];
    if (!snap || !snap.sdk_decode_success) {
      log(`  skip ${p.pool_address}: no snapshot`);
      continue;
    }
    const activeBinId = snap.active_bin_id;
    const lbPair = new PublicKey(p.pool_address);
    const activeIdx = bnToInt(binIdToBinArrayIndex(new BN(activeBinId)));
    log(`  pool=${p.pool_address} active_bin_id=${activeBinId} bin_array_index=${activeIdx}`);

    const poolDerives = [];
    for (const offset of [-1, 0, 1]) {
      const idx = activeIdx + offset;
      try {
        const [pubkey] = deriveBinArray(lbPair, new BN(idx), DLMM_PROGRAM_ID);
        const pubkeyStr = pubkey.toBase58();
        derivations.push({
          pool_address: p.pool_address,
          active_bin_id: activeBinId,
          bin_step: snap.bin_step,
          bin_array_index: idx,
          bin_array_pubkey: pubkeyStr,
          neighbor_offset: offset,
          derivation_success: true,
          confidence: 0.95,
          invalid_reason: "",
        });
        poolDerives.push({ offset, index: idx, pubkey, success: true });
        log(`    offset=${offset} index=${idx} pubkey=${pubkeyStr}`);
      } catch (e) {
        derivations.push({
          pool_address: p.pool_address,
          active_bin_id: activeBinId,
          bin_step: snap.bin_step,
          bin_array_index: idx,
          bin_array_pubkey: "",
          neighbor_offset: offset,
          derivation_success: false,
          confidence: 0.0,
          invalid_reason: String(e?.message ?? e),
        });
        poolDerives.push({ offset, index: idx, pubkey: null, success: false });
        log(`    offset=${offset} FAILED: ${String(e?.message ?? e).slice(0, 60)}`);
      }
    }
    derivationByPool[p.pool_address] = poolDerives;
  }
  // Write derivation CSV/JSON
  const dCsv = path.join(outputDir, "binarray_pda_derivation.csv");
  const dJson = path.join(outputDir, "binarray_pda_derivation.json");
  const dHeader = ["pool_address", "active_bin_id", "bin_step", "bin_array_index", "bin_array_pubkey", "neighbor_offset", "derivation_success", "confidence", "invalid_reason"];
  writeCsv(dCsv, dHeader, derivations);
  fs.writeFileSync(dJson, JSON.stringify(derivations, null, 2));
  log(`wrote ${dCsv} + ${dJson} (${derivations.length} rows)`);

  // === Stage E: single-account getAccountInfo ===
  log("=== Stage E: single-account getAccountInfo ===");
  const singleSmokes = [];
  for (const p of selected) {
    const poolDerives = derivationByPool[p.pool_address] || [];
    for (const d of poolDerives) {
      if (!d.success) continue;
      const t0 = now();
      const [info, err] = await safeCall(() => withFallback((c) => c.getAccountInfo(d.pubkey)));
      const ms = now() - t0;
      if (err) {
        const rpcErrorType = err.includes("410") ? "rpc_410_gone" : (err.includes("403") ? "rpc_403_forbidden" : "unknown");
        singleSmokes.push({
          pool_address: p.pool_address,
          bin_array_pubkey: d.pubkey.toBase58(),
          neighbor_offset: d.offset,
          getAccountInfo_attempted: true,
          getAccountInfo_success: false,
          owner: "",
          data_len: 0,
          rpc_error_type: rpcErrorType,
          confidence: 0.0,
          invalid_reason: err,
          latency_ms: ms,
        });
        log(`  pool=${p.pool_address} offset=${d.offset} failed (${rpcErrorType})`);
      } else if (info === null) {
        singleSmokes.push({
          pool_address: p.pool_address,
          bin_array_pubkey: d.pubkey.toBase58(),
          neighbor_offset: d.offset,
          getAccountInfo_attempted: true,
          getAccountInfo_success: false,
          owner: "",
          data_len: 0,
          rpc_error_type: "account_null",
          confidence: 0.0,
          invalid_reason: "getAccountInfo returned null (account doesn't exist)",
          latency_ms: ms,
        });
        log(`  pool=${p.pool_address} offset=${d.offset} account null`);
      } else {
        // data can be: Buffer (when encoding is "base64" no array)
        // or array [base64_string, "base64"] (when getAccountInfo returns JSON)
        let dataBuf = null;
        if (info.data) {
          if (Buffer.isBuffer(info.data)) {
            dataBuf = info.data;
          } else if (Array.isArray(info.data) && info.data[0]) {
            dataBuf = Buffer.from(info.data[0], "base64");
          } else if (typeof info.data === "string") {
            dataBuf = Buffer.from(info.data, "base64");
          }
        }
        const dataLen = dataBuf ? dataBuf.length : 0;
        const owner = info.owner?.toBase58?.() || (typeof info.owner === "string" ? info.owner : "");
        const expectedOwner = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo";
        const ownerOk = (owner === expectedOwner);
        singleSmokes.push({
          pool_address: p.pool_address,
          bin_array_pubkey: d.pubkey.toBase58(),
          neighbor_offset: d.offset,
          getAccountInfo_attempted: true,
          getAccountInfo_success: true,
          owner,
          data_len: dataLen,
          rpc_error_type: ownerOk ? "ok" : "owner_mismatch",
          confidence: ownerOk ? 0.9 : 0.3,
          invalid_reason: ownerOk ? "" : `owner=${owner} != expected=${expectedOwner}`,
          latency_ms: ms,
        });
        log(`  pool=${p.pool_address} offset=${d.offset} SUCCESS (owner=${owner.slice(0, 8)}... data_len=${dataLen})`);
      }
    }
  }
  // Single-account smoke CSV/JSON
  const eCsv = path.join(outputDir, "binarray_single_account_smoke.csv");
  const eJson = path.join(outputDir, "binarray_single_account_smoke.json");
  const eHeader = ["pool_address", "bin_array_pubkey", "neighbor_offset", "getAccountInfo_attempted", "getAccountInfo_success", "owner", "data_len", "rpc_error_type", "confidence", "invalid_reason", "latency_ms"];
  writeCsv(eCsv, eHeader, singleSmokes);
  fs.writeFileSync(eJson, JSON.stringify(singleSmokes, null, 2));
  log(`wrote ${eCsv} + ${eJson} (${singleSmokes.length} rows)`);

  // Summary for Stage E
  const eAttempted = singleSmokes.length;
  const eSuccess = singleSmokes.filter((r) => r.getAccountInfo_success).length;
  const e403 = singleSmokes.filter((r) => r.rpc_error_type === "rpc_403_forbidden").length;
  const e410 = singleSmokes.filter((r) => r.rpc_error_type === "rpc_410_gone").length;
  const eTimeout = singleSmokes.filter((r) => r.rpc_error_type === "timeout").length;
  const eNull = singleSmokes.filter((r) => r.rpc_error_type === "account_null").length;
  log(`Stage E summary: attempted=${eAttempted} success=${eSuccess} 403=${e403} 410=${e410} timeout=${eTimeout} account_null=${eNull}`);

  // === Stage F: small-batch getMultipleAccounts (only if Stage E had 0 success) ===
  let fAttempted = false;
  const smallBatchResults = [];
  if (eSuccess === 0) {
    log("=== Stage F: small-batch getMultipleAccounts (Stage E 0 success, try multi-account) ===");
    fAttempted = true;
    for (const p of selected) {
      const poolDerives = (derivationByPool[p.pool_address] || []).filter((d) => d.success);
      if (poolDerives.length < 1) continue;
      // Test 1: single pubkey via getMultipleAccountsInfo
      const singleKey = [poolDerives[0].pubkey];
      const t0 = now();
      const [infos, err] = await safeCall(() => withFallback((c) => c.getMultipleAccountsInfo(singleKey)));
      const ms = now() - t0;
      if (err || !infos) {
        smallBatchResults.push({
          pool_address: p.pool_address,
          account_count: 1,
          getMultipleAccounts_success: false,
          success_count: 0,
          data_lens: "",
          rpc_error_type: err && err.includes("410") ? "rpc_410_gone" : (err && err.includes("403") ? "rpc_403_forbidden" : "unknown"),
          confidence: 0.0,
          invalid_reason: err || "returned null",
          latency_ms: ms,
        });
        log(`  pool=${p.pool_address} 1-account getMultipleAccounts: ${err ? "blocked" : "null"}`);
      } else {
        const nonNull = infos.filter((i) => i !== null);
        const dataLens = nonNull.map((i) => (i.data?.[0] ? Buffer.from(i.data[0], "base64").length : 0));
        const owners = nonNull.map((i) => i.owner?.toBase58?.() || "");
        const allOk = nonNull.length === 1 && owners[0] === "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo";
        smallBatchResults.push({
          pool_address: p.pool_address,
          account_count: 1,
          getMultipleAccounts_success: true,
          success_count: nonNull.length,
          data_lens: dataLens.join(";"),
          rpc_error_type: allOk ? "ok" : "owner_mismatch_or_partial",
          confidence: allOk ? 0.85 : 0.4,
          invalid_reason: allOk ? "" : `owners=${owners.join(",")} nonNull=${nonNull.length}`,
          latency_ms: ms,
        });
        log(`  pool=${p.pool_address} 1-account getMultipleAccounts: success (data_lens=${dataLens.join(",")})`);
      }
      // Test 2: 3 pubkeys if 1-account worked
      if (poolDerives.length >= 3) {
        const threeKeys = poolDerives.map((d) => d.pubkey);
        const t0b = now();
        const [infos2, err2] = await safeCall(() => withFallback((c) => c.getMultipleAccountsInfo(threeKeys)));
        const ms2 = now() - t0b;
        if (err2 || !infos2) {
          smallBatchResults.push({
            pool_address: p.pool_address,
            account_count: 3,
            getMultipleAccounts_success: false,
            success_count: 0,
            data_lens: "",
            rpc_error_type: err2 && err2.includes("410") ? "rpc_410_gone" : (err2 && err2.includes("403") ? "rpc_403_forbidden" : "unknown"),
            confidence: 0.0,
            invalid_reason: err2 || "returned null",
            latency_ms: ms2,
          });
          log(`  pool=${p.pool_address} 3-account getMultipleAccounts: blocked`);
        } else {
          const nonNull2 = infos2.filter((i) => i !== null);
          const dataLens2 = nonNull2.map((i) => (i.data?.[0] ? Buffer.from(i.data[0], "base64").length : 0));
          smallBatchResults.push({
            pool_address: p.pool_address,
            account_count: 3,
            getMultipleAccounts_success: true,
            success_count: nonNull2.length,
            data_lens: dataLens2.join(";"),
            rpc_error_type: nonNull2.length === 3 ? "ok" : "partial",
            confidence: nonNull2.length === 3 ? 0.85 : 0.4,
            invalid_reason: nonNull2.length === 3 ? "" : `nonNull=${nonNull2.length}`,
            latency_ms: ms2,
          });
          log(`  pool=${p.pool_address} 3-account getMultipleAccounts: success_count=${nonNull2.length}`);
        }
      }
    }
  } else {
    log("=== Stage F: skipped (Stage E had success; single-account path works) ===");
  }
  // Write small-batch CSV/JSON
  if (fAttempted) {
    const fCsv = path.join(outputDir, "binarray_small_batch_smoke.csv");
    const fJson = path.join(outputDir, "binarray_small_batch_smoke.json");
    const fHeader = ["pool_address", "account_count", "getMultipleAccounts_success", "success_count", "data_lens", "rpc_error_type", "confidence", "invalid_reason", "latency_ms"];
    writeCsv(fCsv, fHeader, smallBatchResults);
    fs.writeFileSync(fJson, JSON.stringify(smallBatchResults, null, 2));
    log(`wrote ${fCsv} + ${fJson} (${smallBatchResults.length} rows)`);
  }

  // === Stage G: bin liquidity decode (only if E or F succeeded) ===
  let gAttempted = false;
  const binLiquidityDecoded = [];
  const fSuccess = smallBatchResults.filter((r) => r.getMultipleAccounts_success).length;
  if (eSuccess > 0 || fSuccess > 0) {
    log("=== Stage G: bin liquidity decode ===");
    gAttempted = true;
    for (const p of selected) {
      const poolDerives = derivationByPool[p.pool_address] || [];
      // For each successful bin array, decode
      const candidates = poolDerives.map((d) => {
        if (!d.success) return null;
        // Find the corresponding smoke result
        const smoke = singleSmokes.find((s) => s.pool_address === p.pool_address && s.bin_array_pubkey === d.pubkey.toBase58() && s.getAccountInfo_success);
        if (!smoke) return null;
        return { d, smoke };
      }).filter(Boolean);
      for (const cand of candidates) {
        const { d, smoke } = cand;
        try {
          // Use SDK program to decode the bin array
          // Connect to program via dlmmPool
          const dlmmPool = await DLMM.create(new Connection(PRIMARY_RPC, "confirmed"), new PublicKey(p.pool_address), { cluster: "mainnet-beta" });
          // program.account.binArray.fetch is a single-account decode via Anchor
          const [binArrayAcct, fetchErr] = await safeCall(() => withFallback((c) => dlmmPool.program.account.binArray.fetch(cand.d.pubkey).then(r => r).catch(e => { throw e; })));
          if (binArrayAcct) {
            const bins = binArrayAcct.bins || [];
            // for each bin in the array, decode amountX / amountY
            for (let i = 0; i < bins.length; i++) {
              const b = bins[i];
              const [lowerBinId] = getBinArrayLowerUpperBinId(new BN(d.index));
              const binId = bnToInt(lowerBinId) + i;
              const xAmount = b.amountX?.toString?.() ?? b.amountX ?? null;
              const yAmount = b.amountY?.toString?.() ?? b.amountY ?? null;
              const price = binArrayAcct.priceCalculator
                ? null
                : null;  // SDK does not expose price directly; compute manually if needed
              binLiquidityDecoded.push({
                pool_address: p.pool_address,
                bin_array_pubkey: cand.d.pubkey.toBase58(),
                bin_id: binId,
                x_amount: xAmount,
                y_amount: yAmount,
                price: price,
                liquidity_available: (xAmount !== null || yAmount !== null),
                decode_success: true,
                confidence: 0.85,
                invalid_reason: "",
              });
            }
            log(`  pool=${p.pool_address} offset=${d.offset} decoded ${bins.length} bins`);
          } else {
            log(`  pool=${p.pool_address} offset=${d.offset} decode FAILED: ${fetchErr}`);
          }
        } catch (e) {
          log(`  pool=${p.pool_address} offset=${d.offset} exception: ${String(e?.message ?? e).slice(0, 60)}`);
        }
      }
    }
  } else {
    log("=== Stage G: skipped (Stage E + F both failed) ===");
  }
  if (gAttempted) {
    const gCsv = path.join(outputDir, "bin_liquidity_decode.csv");
    const gJson = path.join(outputDir, "bin_liquidity_decode.json");
    const gHeader = ["pool_address", "bin_array_pubkey", "bin_id", "x_amount", "y_amount", "price", "liquidity_available", "decode_success", "confidence", "invalid_reason"];
    writeCsv(gCsv, gHeader, binLiquidityDecoded);
    fs.writeFileSync(gJson, JSON.stringify(binLiquidityDecoded, null, 2));
    log(`wrote ${gCsv} + ${gJson} (${binLiquidityDecoded.length} rows)`);
  }

  // === Stage H: quote smoke v2 (only if G had decoded rows) ===
  let hAttempted = false;
  let hSuccess = 0;
  const quoteResults = [];
  if (gAttempted && binLiquidityDecoded.length > 0) {
    log("=== Stage H: quote smoke v2 ===");
    hAttempted = true;
    for (const p of selected) {
      const poolDerives = (derivationByPool[p.pool_address] || []).filter((d) => d.success);
      const poolDecoded = binLiquidityDecoded.filter((r) => r.pool_address === p.pool_address);
      if (poolDecoded.length === 0) continue;
      try {
        const dlmmPool = await DLMM.create(new Connection(PRIMARY_RPC, "confirmed"), new PublicKey(p.pool_address), { cluster: "mainnet-beta" });
        // Determine Y token
        const yMint = dlmmPool.tokenY?.publicKey?.toBase58?.();
        const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
        const swapYtoX = (yMint === USDC);
        // Pre-fetch ALL 3 bin arrays (active + 2 neighbors) via single-account path
        // and pass ALL of them to swapQuote
        const baAccts = [];
        for (const d of poolDerives) {
          const [ba, ferr] = await safeCall(() => withFallback((c) => dlmmPool.program.account.binArray.fetch(d.pubkey).then(r => r).catch(e => { throw e; })));
          if (ba) baAccts.push({ account: ba, publicKey: d.pubkey });
        }
        if (baAccts.length === 0) {
          log(`  pool=${p.pool_address} no bin arrays fetchable`);
          continue;
        }
        log(`  pool=${p.pool_address} prepared ${baAccts.length} bin arrays for swapQuote`);
        for (const notional of [10_000_000, 20_000_000]) {
          const t0 = now();
          const inAmount = new BN(notional);
          const slippage = new BN(50);
          // Try with maxExtraBinArrays=3 (let SDK try to fetch more if needed; will fail on multi-account)
          const [quote, qErr] = await safeCall(() => dlmmPool.swapQuote(inAmount, swapYtoX, slippage, baAccts, false, 3));
          const ms = now() - t0;
          if (quote) {
            hSuccess++;
            quoteResults.push({
              pool_address: p.pool_address,
              notional_usd: notional === 10_000_000 ? "10U" : "20U",
              token_in: swapYtoX ? "Y" : "X",
              token_out: swapYtoX ? "X" : "Y",
              amount_in_raw: notional.toString(),
              quote_attempted: true,
              quote_success: true,
              amount_out_raw: quote.outAmount?.toString?.() ?? null,
              price_impact: "",
              fee: quote.totalFeeAmount?.toString?.() ?? null,
              bins_crossed: quote.binArraysCovered ?? 0,
              confidence: 0.85,
              invalid_reason: "",
              latency_ms: ms,
            });
            log(`  pool=${p.pool_address} notional=${notional}: QUOTE SUCCESS out=${quote.outAmount?.toString?.()}`);
          } else {
            quoteResults.push({
              pool_address: p.pool_address,
              notional_usd: notional === 10_000_000 ? "10U" : "20U",
              token_in: swapYtoX ? "Y" : "X",
              token_out: swapYtoX ? "X" : "Y",
              amount_in_raw: notional.toString(),
              quote_attempted: true,
              quote_success: false,
              amount_out_raw: null,
              price_impact: "",
              fee: null,
              bins_crossed: null,
              confidence: 0.0,
              invalid_reason: qErr || "swapQuote returned null",
              latency_ms: ms,
            });
            log(`  pool=${p.pool_address} notional=${notional}: quote failed: ${qErr?.slice(0, 60)}`);
          }
        }
      } catch (e) {
        log(`  pool=${p.pool_address} quote exception: ${String(e?.message ?? e).slice(0, 60)}`);
      }
    }
  } else {
    log("=== Stage H: skipped (Stage G had no decoded rows) ===");
  }
  if (hAttempted) {
    const hCsv = path.join(outputDir, "quote_smoke_v2.csv");
    const hJson = path.join(outputDir, "quote_smoke_v2.json");
    const hHeader = ["pool_address", "notional_usd", "token_in", "token_out", "amount_in_raw", "quote_attempted", "quote_success", "amount_out_raw", "price_impact", "fee", "bins_crossed", "confidence", "invalid_reason", "latency_ms"];
    writeCsv(hCsv, hHeader, quoteResults);
    fs.writeFileSync(hJson, JSON.stringify(quoteResults, null, 2));
    log(`wrote ${hCsv} + ${hJson} (${quoteResults.length} rows; success=${hSuccess})`);
  }

  // === Summary ===
  const summary = {
    run_id: runId,
    stage: "LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1",
    rpc_url_redacted_source: rpcRedacted,
    sdk_package: "@meteora-ag/dlmm",
    sdk_package_version: "1.9.10",
    cluster: "mainnet-beta",
    pools_attempted: selected.length,
    pda_derivation_success_count: derivations.filter((d) => d.derivation_success).length,
    pda_derivation_total: derivations.length,
    single_account_smoke_attempted_count: eAttempted,
    single_account_smoke_success_count: eSuccess,
    single_account_smoke_403_count: e403,
    single_account_smoke_410_count: e410,
    small_batch_smoke_attempted: fAttempted,
    small_batch_smoke_results_count: smallBatchResults.length,
    small_batch_smoke_success_count: smallBatchResults.filter((r) => r.getMultipleAccounts_success).length,
    bin_liquidity_decode_attempted: gAttempted,
    bin_liquidity_decode_rows: binLiquidityDecoded.length,
    bin_liquidity_decode_success_count: binLiquidityDecoded.filter((r) => r.decode_success).length,
    quote_smoke_attempted: hAttempted,
    quote_smoke_results_count: quoteResults.length,
    quote_smoke_success_count: hSuccess,
    timestamp_utc: new Date().toISOString(),
    solana_wallet_or_keypair_touched: false,
    transaction_sent: false,
    signer_used: false,
    wallet_adapter_used: false,
    swap_transaction_built: false,
    paid_rpc_used: false,
  };
  fs.writeFileSync(path.join(outputDir, "connector_summary.json"), JSON.stringify(summary, null, 2));
  log(`wrote ${path.join(outputDir, "connector_summary.json")}`);

  // Write run.log
  fs.writeFileSync(path.join(outputDir, "run.log"), logLines.join("\n") + "\n");

  // Exit 0 if either single_account or small_batch succeeded
  const ok = (eSuccess > 0) || (smallBatchResults.filter((r) => r.getMultipleAccounts_success).length > 0);
  log(`exit: ${ok ? 0 : 1}`);
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(3);
});
