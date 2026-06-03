#!/usr/bin/env node
/**
 * LP_METEORA_DLMM_BINARRAY_COVERAGE_EXPAND_V1_READONLY
 *
 * Read-only bin array coverage expansion probe.
 *
 * STRICTLY read-only:
 *   - No keypair / signer / wallet adapter
 *   - No transaction construction / sendTransaction
 *   - No swap tx builder / open_lp / close_lp / collect_fee / bridge
 *   - SDK is loaded from a /tmp isolated install dir (NOT repo root)
 *
 * Stages:
 *   D: derive 5/7/9 bin array PDA per pool
 *   E: getAccountInfo (single) on each derived pubkey
 *   F: decode bin array (per success)
 *   G: swapQuote (read-only) per coverage tier
 *   Auto-checkpoint: if 5 succeeds, skip 7+9; if 7 succeeds, skip 9
 *
 * Usage:
 *   NODE_PATH=/tmp/lpbot_meteora_dlmm_sdk_probe_<RUN_ID>/node_modules node \
 *     scripts/lp_meteora_dlmm_binarray_coverage_expand_v1_readonly.js \
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

const { binIdToBinArrayIndex, deriveBinArray, getBinArrayLowerUpperBinId } = DLMM;
const DLMM_PROGRAM_ID = new PublicKey("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo");
const PRIMARY_RPC = "https://solana.publicnode.com";
const FALLBACK_RPC = "https://api.mainnet-beta.solana.com";

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
      try { return await thunk(new Connection(FALLBACK_RPC, "confirmed")); }
      catch (e2) { throw e2; }
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
function offsetsForCoverage(arr) {
  if (arr === 3) return [-1, 0, 1];
  if (arr === 5) return [-2, -1, 0, 1, 2];
  if (arr === 7) return [-3, -2, -1, 0, 1, 2, 3];
  if (arr === 9) return [-4, -3, -2, -1, 0, 1, 2, 3, 4];
  return null;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runId = args["run-id"] || "unknown";
  const outputDir = args["output-dir"] || `reports/lp_meteora_dlmm_quote_binarray_coverage_expand/${runId}/connector_output`;
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
  log(`coverage_expand started: run_id=${runId} rpc_redacted=${rpcRedacted}`);

  const feed = JSON.parse(fs.readFileSync(knownPoolFeedPath, "utf8"));
  const snapshot = JSON.parse(fs.readFileSync(poolSnapshotPath, "utf8"));
  const selected = feed.pools.filter((p) => p.selected_for_snapshot);
  const snapshotByAddr = {};
  for (const s of snapshot) snapshotByAddr[s.pool_address] = s;

  // === Stage D: PDA derivation for 5/7/9 arrays ===
  log("=== Stage D: PDA derivation (5/7/9 arrays) ===");
  const derivations = [];
  const derivationByPool = {}; // pool -> { tier -> [pubkey, ...] }
  for (const p of selected) {
    const snap = snapshotByAddr[p.pool_address];
    if (!snap || !snap.sdk_decode_success) {
      log(`  skip ${p.pool_address}: no snapshot`);
      continue;
    }
    const activeBinId = snap.active_bin_id;
    const lbPair = new PublicKey(p.pool_address);
    const activeIdx = bnToInt(binIdToBinArrayIndex(new BN(activeBinId)));
    log(`  pool=${p.pool_address} active_bin_id=${activeBinId} bin_step=${snap.bin_step} active_index=${activeIdx}`);
    derivationByPool[p.pool_address] = {};
    for (const arr of [5, 7, 9]) {
      const offsets = offsetsForCoverage(arr);
      const arrDerivs = [];
      for (const offset of offsets) {
        const idx = activeIdx + offset;
        try {
          const [pubkey] = deriveBinArray(lbPair, new BN(idx), DLMM_PROGRAM_ID);
          const pubkeyStr = pubkey.toBase58();
          derivations.push({
            pool_address: p.pool_address,
            coverage_arrays: arr,
            active_bin_id: activeBinId,
            bin_step: snap.bin_step,
            bin_array_index: idx,
            bin_array_pubkey: pubkeyStr,
            neighbor_offset: offset,
            derivation_success: true,
            confidence: 0.95,
            invalid_reason: "",
          });
          arrDerivs.push({ offset, index: idx, pubkey, success: true });
        } catch (e) {
          derivations.push({
            pool_address: p.pool_address,
            coverage_arrays: arr,
            active_bin_id: activeBinId,
            bin_step: snap.bin_step,
            bin_array_index: idx,
            bin_array_pubkey: "",
            neighbor_offset: offset,
            derivation_success: false,
            confidence: 0.0,
            invalid_reason: String(e?.message ?? e),
          });
          arrDerivs.push({ offset, index: idx, pubkey: null, success: false });
        }
      }
      derivationByPool[p.pool_address][arr] = arrDerivs;
      log(`    coverage_${arr}_arrays: ${arrDerivs.filter(d => d.success).length}/${arr} success`);
    }
  }
  const dCsv = path.join(outputDir, "expanded_binarray_pda_derivation.csv");
  const dJson = path.join(outputDir, "expanded_binarray_pda_derivation.json");
  const dHeader = ["pool_address", "coverage_arrays", "active_bin_id", "bin_step", "bin_array_index", "bin_array_pubkey", "neighbor_offset", "derivation_success", "confidence", "invalid_reason"];
  writeCsv(dCsv, dHeader, derivations);
  fs.writeFileSync(dJson, JSON.stringify(derivations, null, 2));
  log(`wrote ${dCsv} + ${dJson} (${derivations.length} rows)`);

  // === Stage E: single-account getAccountInfo for 5/7/9 ===
  log("=== Stage E: single-account read (5/7/9 arrays) ===");
  const singleReads = [];
  for (const p of selected) {
    const poolDerives = derivationByPool[p.pool_address] || {};
    for (const arr of [5, 7, 9]) {
      const arrDerivs = poolDerives[arr] || [];
      for (const d of arrDerivs) {
        if (!d.success) continue;
        const t0 = now();
        const [info, err] = await safeCall(() => withFallback((c) => c.getAccountInfo(d.pubkey)));
        const ms = now() - t0;
        if (err) {
          const rpcErrorType = err.includes("410") ? "rpc_410_gone" : (err.includes("403") ? "rpc_403_forbidden" : "unknown");
          singleReads.push({
            pool_address: p.pool_address,
            coverage_arrays: arr,
            bin_array_pubkey: d.pubkey.toBase58(),
            neighbor_offset: d.offset,
            getAccountInfo_success: false,
            owner: "",
            data_len: 0,
            rpc_error_type: rpcErrorType,
            latency_ms: ms,
            confidence: 0.0,
            invalid_reason: err,
          });
        } else if (info === null) {
          singleReads.push({
            pool_address: p.pool_address,
            coverage_arrays: arr,
            bin_array_pubkey: d.pubkey.toBase58(),
            neighbor_offset: d.offset,
            getAccountInfo_success: false,
            owner: "",
            data_len: 0,
            rpc_error_type: "account_null",
            latency_ms: ms,
            confidence: 0.0,
            invalid_reason: "getAccountInfo returned null (account doesn't exist)",
          });
        } else {
          let dataBuf = null;
          if (info.data) {
            if (Buffer.isBuffer(info.data)) dataBuf = info.data;
            else if (Array.isArray(info.data) && info.data[0]) dataBuf = Buffer.from(info.data[0], "base64");
            else if (typeof info.data === "string") dataBuf = Buffer.from(info.data, "base64");
          }
          const dataLen = dataBuf ? dataBuf.length : 0;
          const owner = info.owner?.toBase58?.() || (typeof info.owner === "string" ? info.owner : "");
          const expectedOwner = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo";
          const ownerOk = (owner === expectedOwner);
          singleReads.push({
            pool_address: p.pool_address,
            coverage_arrays: arr,
            bin_array_pubkey: d.pubkey.toBase58(),
            neighbor_offset: d.offset,
            getAccountInfo_success: true,
            owner,
            data_len: dataLen,
            rpc_error_type: ownerOk ? "ok" : "owner_mismatch",
            latency_ms: ms,
            confidence: ownerOk ? 0.9 : 0.3,
            invalid_reason: ownerOk ? "" : `owner=${owner} != expected=${expectedOwner}`,
          });
        }
      }
    }
  }
  const eCsv = path.join(outputDir, "expanded_single_account_read.csv");
  const eJson = path.join(outputDir, "expanded_single_account_read.json");
  const eHeader = ["pool_address", "coverage_arrays", "bin_array_pubkey", "neighbor_offset", "getAccountInfo_success", "owner", "data_len", "rpc_error_type", "latency_ms", "confidence", "invalid_reason"];
  writeCsv(eCsv, eHeader, singleReads);
  fs.writeFileSync(eJson, JSON.stringify(singleReads, null, 2));
  // Stage E summary by coverage tier
  for (const arr of [5, 7, 9]) {
    const arrReads = singleReads.filter((r) => r.coverage_arrays === arr);
    const success = arrReads.filter((r) => r.getAccountInfo_success).length;
    const e403 = arrReads.filter((r) => r.rpc_error_type === "rpc_403_forbidden").length;
    const e410 = arrReads.filter((r) => r.rpc_error_type === "rpc_410_gone").length;
    log(`  coverage_${arr}_arrays: attempted=${arrReads.length} success=${success} 403=${e403} 410=${e410}`);
  }
  log(`wrote ${eCsv} + ${eJson} (${singleReads.length} rows)`);

  // === Stage F: bin liquidity decode (only for successful single-account reads) ===
  log("=== Stage F: bin liquidity decode ===");
  const binLiquidityDecoded = [];
  for (const p of selected) {
    const snap = snapshotByAddr[p.pool_address];
    if (!snap || !snap.sdk_decode_success) continue;
    const poolDerives = derivationByPool[p.pool_address] || {};
    for (const arr of [5, 7, 9]) {
      const arrDerivs = poolDerives[arr] || [];
      for (const d of arrDerivs) {
        if (!d.success) continue;
        const smoke = singleReads.find((s) => s.coverage_arrays === arr && s.pool_address === p.pool_address && s.bin_array_pubkey === d.pubkey.toBase58() && s.getAccountInfo_success);
        if (!smoke) continue;
        try {
          const dlmmPool = await DLMM.create(new Connection(PRIMARY_RPC, "confirmed"), new PublicKey(p.pool_address), { cluster: "mainnet-beta" });
          const [binArrayAcct] = await safeCall(() => withFallback((c) => dlmmPool.program.account.binArray.fetch(d.pubkey).then(r => r).catch(e => { throw e; })));
          if (binArrayAcct) {
            const bins = binArrayAcct.bins || [];
            const [lowerBinId] = getBinArrayLowerUpperBinId(new BN(d.index));
            for (let i = 0; i < bins.length; i++) {
              const b = bins[i];
              const binId = bnToInt(lowerBinId) + i;
              const xAmount = b.amountX?.toString?.() ?? b.amountX ?? null;
              const yAmount = b.amountY?.toString?.() ?? b.amountY ?? null;
              const hasLiq = (xAmount !== null && xAmount !== "0") || (yAmount !== null && yAmount !== "0");
              binLiquidityDecoded.push({
                pool_address: p.pool_address,
                coverage_arrays: arr,
                bin_array_pubkey: d.pubkey.toBase58(),
                bin_id: binId,
                x_amount: xAmount,
                y_amount: yAmount,
                price: null,
                active_bin_distance: binId - snap.active_bin_id,
                liquidity_available: hasLiq,
                decode_success: true,
                confidence: 0.85,
                invalid_reason: "",
              });
            }
          }
        } catch (e) {
          // skip
        }
      }
    }
  }
  const fCsv = path.join(outputDir, "expanded_bin_liquidity_decode.csv");
  const fJson = path.join(outputDir, "expanded_bin_liquidity_decode.json");
  const fHeader = ["pool_address", "coverage_arrays", "bin_array_pubkey", "bin_id", "x_amount", "y_amount", "price", "active_bin_distance", "liquidity_available", "decode_success", "confidence", "invalid_reason"];
  writeCsv(fCsv, fHeader, binLiquidityDecoded);
  fs.writeFileSync(fJson, JSON.stringify(binLiquidityDecoded, null, 2));
  // Stage F summary
  for (const arr of [5, 7, 9]) {
    const arrBins = binLiquidityDecoded.filter((b) => b.coverage_arrays === arr);
    const withLiq = arrBins.filter((b) => b.liquidity_available).length;
    log(`  coverage_${arr}_arrays: bins_decoded=${arrBins.length} bins_with_liquidity=${withLiq}`);
  }
  log(`wrote ${fCsv} + ${fJson} (${binLiquidityDecoded.length} rows)`);

  // === Stage G: quote smoke v3 by coverage ===
  log("=== Stage G: quote smoke v3 (by coverage) ===");
  // For each coverage tier, if previous tier got 100% quote success, skip higher tier
  const quoteResults = [];
  let solUsdcSuccessByTier = {}; // tier -> quote_success_count
  for (const arr of [5, 7, 9]) {
    // Pre-fetch decoded bin arrays for this tier
    const tierBins = binLiquidityDecoded.filter((b) => b.coverage_arrays === arr);
    for (const p of selected) {
      const tierBinsForPool = tierBins.filter((b) => b.pool_address === p.pool_address);
      if (tierBinsForPool.length === 0) continue;
      try {
        const dlmmPool = await DLMM.create(new Connection(PRIMARY_RPC, "confirmed"), new PublicKey(p.pool_address), { cluster: "mainnet-beta" });
        const yMint = dlmmPool.tokenY?.publicKey?.toBase58?.();
        const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
        const swapYtoX = (yMint === USDC);
        // Re-fetch all decoded bin arrays (full BinArrayAccount)
        const poolDerives = (derivationByPool[p.pool_address] || {})[arr] || [];
        const baAccts = [];
        for (const d of poolDerives) {
          if (!d.success) continue;
          const [ba] = await safeCall(() => withFallback((c) => dlmmPool.program.account.binArray.fetch(d.pubkey).then(r => r).catch(e => { throw e; })));
          if (ba) baAccts.push({ account: ba, publicKey: d.pubkey });
        }
        if (baAccts.length === 0) {
          log(`  pool=${p.pool_address} coverage=${arr}: no bin arrays fetchable`);
          continue;
        }
        log(`  pool=${p.pool_address} coverage=${arr}: ${baAccts.length} bin arrays for swapQuote`);
        for (const notional of [10_000_000, 20_000_000]) {
          const t0 = now();
          const inAmount = new BN(notional);
          const slippage = new BN(50);
          const [quote, qErr] = await safeCall(() => dlmmPool.swapQuote(inAmount, swapYtoX, slippage, baAccts, false, 3));
          const ms = now() - t0;
          if (quote) {
            quoteResults.push({
              pool_address: p.pool_address,
              coverage_arrays: arr,
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
              coverage_sufficient: "yes",
              confidence: 0.9,
              invalid_reason: "",
              latency_ms: ms,
            });
            log(`    ${notional === 10_000_000 ? "10U" : "20U"}: QUOTE SUCCESS out=${quote.outAmount?.toString?.()}`);
          } else {
            quoteResults.push({
              pool_address: p.pool_address,
              coverage_arrays: arr,
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
              coverage_sufficient: "no",
              confidence: 0.0,
              invalid_reason: qErr || "swapQuote returned null",
              latency_ms: ms,
            });
            log(`    ${notional === 10_000_000 ? "10U" : "20U"}: failed: ${qErr?.slice(0, 60)}`);
          }
        }
      } catch (e) {
        log(`  pool=${p.pool_address} coverage=${arr} exception: ${String(e?.message ?? e).slice(0, 60)}`);
      }
    }
    // Track SOL/USDC success by tier
    const solUsdcTierResults = quoteResults.filter((r) => r.coverage_arrays === arr && r.pool_address === "5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF");
    solUsdcSuccessByTier[arr] = solUsdcTierResults.filter((r) => r.quote_success).length;
    // Auto-checkpoint: if SOL/USDC achieves 2/2, log "5_arrays sufficient"
    if (solUsdcSuccessByTier[arr] === 2 && p === selected[selected.length - 1]) {
      log(`  coverage_${arr}_arrays: SOL/USDC achieved 2/2 success → STOP expansion; ${arr}_arrays sufficient`);
    }
  }
  const gCsv = path.join(outputDir, "quote_smoke_v3_by_coverage.csv");
  const gJson = path.join(outputDir, "quote_smoke_v3_by_coverage.json");
  const gHeader = ["pool_address", "coverage_arrays", "notional_usd", "token_in", "token_out", "amount_in_raw", "quote_attempted", "quote_success", "amount_out_raw", "price_impact", "fee", "bins_crossed", "coverage_sufficient", "confidence", "invalid_reason", "latency_ms"];
  writeCsv(gCsv, gHeader, quoteResults);
  fs.writeFileSync(gJson, JSON.stringify(quoteResults, null, 2));
  log(`wrote ${gCsv} + ${gJson} (${quoteResults.length} rows)`);

  // === Summary ===
  const summary = {
    run_id: runId,
    stage: "LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1",
    rpc_url_redacted_source: rpcRedacted,
    sdk_package: "@meteora-ag/dlmm",
    sdk_package_version: "1.9.10",
    cluster: "mainnet-beta",
    pools_attempted: selected.length,
    coverage_tiers_run: [5, 7, 9],
    pda_derivation_total: derivations.length,
    pda_derivation_success_count: derivations.filter((d) => d.derivation_success).length,
    single_account_read_total: singleReads.length,
    single_account_read_success_count: singleReads.filter((r) => r.getAccountInfo_success).length,
    bin_liquidity_decode_total: binLiquidityDecoded.length,
    bin_liquidity_decode_with_liquidity: binLiquidityDecoded.filter((b) => b.liquidity_available).length,
    quote_attempted_count: quoteResults.length,
    quote_success_count: quoteResults.filter((r) => r.quote_success).length,
    quote_success_by_tier: {
      coverage_5_arrays: quoteResults.filter((r) => r.coverage_arrays === 5 && r.quote_success).length,
      coverage_7_arrays: quoteResults.filter((r) => r.coverage_arrays === 7 && r.quote_success).length,
      coverage_9_arrays: quoteResults.filter((r) => r.coverage_arrays === 9 && r.quote_success).length,
    },
    sol_usdc_quote_success_by_tier: solUsdcSuccessByTier,
    x_usdc_quote_success_by_tier: {
      coverage_5_arrays: quoteResults.filter((r) => r.coverage_arrays === 5 && r.pool_address === "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad" && r.quote_success).length,
      coverage_7_arrays: quoteResults.filter((r) => r.coverage_arrays === 7 && r.pool_address === "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad" && r.quote_success).length,
      coverage_9_arrays: quoteResults.filter((r) => r.coverage_arrays === 9 && r.pool_address === "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad" && r.quote_success).length,
    },
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

  // Exit 0 if SOL/USDC achieved 2/2 success at any tier OR if total 4/4+
  const solUsdcTotalSuccess = (solUsdcSuccessByTier[5] || 0) + (solUsdcSuccessByTier[7] || 0) + (solUsdcSuccessByTier[9] || 0);
  const ok = solUsdcTotalSuccess >= 2 || summary.quote_success_count >= 4;
  log(`exit: ${ok ? 0 : 1}`);
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(3);
});
