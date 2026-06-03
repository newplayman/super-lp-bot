#!/usr/bin/env node
/**
 * LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1_READONLY
 *
 * Read-only connector for Meteora DLMM via @meteora-ag/dlmm SDK.
 *
 * STRICTLY read-only:
 *   - No keypair / signer / wallet adapter
 *   - No transaction construction / sendTransaction
 *   - No swap tx builder / open_lp / close_lp / collect_fee / bridge
 *   - SDK is loaded from a /tmp isolated install dir (NOT repo root)
 *   - No package install in repo root; no node_modules in repo root
 *
 * Modes:
 *   --mode snapshot     run pool_snapshot + fee_snapshot + bin_liquidity_attempt
 *                       (this is the default; quote is NOT attempted in snapshot mode)
 *   --mode quote-smoke  additionally attempt 10U/20U quote (read-only swapQuote)
 *   --mode all          all of the above
 *
 * Usage:
 *   NODE_PATH=/tmp/lpbot_meteora_dlmm_sdk_probe_<RUN_ID>/node_modules node \
 *     scripts/lp_meteora_dlmm_known_pool_connector_v1_readonly.js \
 *     --run-id <RUN_ID> \
 *     --output-dir <DIR> \
 *     --rpc-url-redacted-source <label> \
 *     --known-pool-feed <PATH_TO_meteora_dlmm_known_pool_feed.json> \
 *     --mode snapshot
 */
"use strict";

const fs = require("fs");
const path = require("path");
const DLMM = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");

const PRIMARY_RPC = "https://solana.publicnode.com";
const FALLBACK_RPC = "https://api.mainnet-beta.solana.com";

function now() { return Date.now(); }

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const k = a.slice(2);
      const v = argv[i + 1];
      args[k] = v;
      i++;
    }
  }
  return args;
}

function asInt(x, d) {
  const n = parseInt(x, 10);
  return Number.isFinite(n) ? n : d;
}

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
  for (const r of rows) {
    lines.push(header.map((h) => csvEscape(r[h])).join(","));
  }
  fs.writeFileSync(filePath, lines.join("\n") + "\n");
}

async function decodePool(poolAddress) {
  const t0 = now();
  const result = {
    pool_address: poolAddress,
    pool_owner: null,
    sdk_decode_success: false,
    token_x_mint: null,
    token_y_mint: null,
    token_x_decimals: null,
    token_y_decimals: null,
    bin_step: null,
    active_bin_id: null,
    active_price: null,
    active_bin_x_amount: null,
    active_bin_y_amount: null,
    reserve_x_raw: null,
    reserve_y_raw: null,
    volatility_accumulator: null,
    data_len: null,
    fee_info_available: false,
    base_fee_bps: null,
    max_fee_bps: null,
    protocol_fee_bps: null,
    get_active_bin_error: null,
    get_fee_info_error: null,
    create_error: null,
    latency_ms_total: 0,
  };

  let dlmmPool = null;
  try {
    [dlmmPool, result.create_error] = await safeCall(() =>
      withFallback((connection) =>
        DLMM.create(connection, new PublicKey(poolAddress), { cluster: "mainnet-beta" })
      )
    );
    if (!dlmmPool) {
      result.latency_ms_total = now() - t0;
      return result;
    }
    result.pool_owner = dlmmPool.program?.programId?.toBase58?.() ?? null;
    result.bin_step = dlmmPool.lbPair?.binStep ?? null;
    result.token_x_mint = dlmmPool.tokenX?.publicKey?.toBase58?.() ?? null;
    result.token_y_mint = dlmmPool.tokenY?.publicKey?.toBase58?.() ?? null;
    result.token_x_decimals = dlmmPool.tokenX?.mint?.decimals ?? null;
    result.token_y_decimals = dlmmPool.tokenY?.mint?.decimals ?? null;
    if (dlmmPool.tokenX?.amount) result.reserve_x_raw = dlmmPool.tokenX.amount.toString();
    if (dlmmPool.tokenY?.amount) result.reserve_y_raw = dlmmPool.tokenY.amount.toString();
    if (dlmmPool.lbPair?.vParameters?.volatilityAccumulator) {
      result.volatility_accumulator = dlmmPool.lbPair.vParameters.volatilityAccumulator.toString();
    }
    if (dlmmPool.lbPair?.account) {
      // account data length if exposed
      const data = dlmmPool.lbPair.account.data;
      if (typeof data === "object" && data.length !== undefined) {
        result.data_len = data.length;
      } else if (typeof data === "string") {
        // not expected, but defensive
        result.data_len = data.length;
      }
    }

    // active bin (with fallback)
    {
      const [ab, err] = await safeCall(() => withFallback((c) => dlmmPool.getActiveBin(c).then(r => r).catch(e => { throw e; })));
      if (ab) {
        result.active_bin_id = ab.binId ?? null;
        result.active_price = ab.price ? ab.price.toString() : null;
        if (ab.xAmount !== undefined) result.active_bin_x_amount = ab.xAmount.toString();
        if (ab.yAmount !== undefined) result.active_bin_y_amount = ab.yAmount.toString();
      } else {
        result.get_active_bin_error = err;
      }
    }

    // fee info (synchronous)
    {
      const [fi, err] = await safeCall(async () => dlmmPool.getFeeInfo());
      if (fi) {
        result.fee_info_available = true;
        result.base_fee_bps = fi.baseFeeRatePercentage ?? null;
        result.max_fee_bps = fi.maxFeeRatePercentage ?? null;
        result.protocol_fee_bps = fi.protocolFeeBps ?? fi.protocolFeeRatePercentage ?? null;
      } else {
        result.get_fee_info_error = err;
      }
    }

    result.sdk_decode_success = true;
  } catch (e) {
    result.fatal_error = String(e?.message ?? e);
  }
  result.latency_ms_total = now() - t0;
  return result;
}

async function attemptBinLiquidity(poolAddress) {
  const t0 = now();
  const result = {
    pool_address: poolAddress,
    active_bin_id: null,
    bin_array_attempted: false,
    bin_array_success: false,
    bin_count: 0,
    total_x_amount: null,
    total_y_amount: null,
    blocker: null,
    rpc_error_type: null,
    confidence: 0.0,
    latency_ms: 0,
  };

  let dlmmPool = null;
  try {
    let err = null;
    [dlmmPool, err] = await safeCall(() =>
      withFallback((c) => DLMM.create(c, new PublicKey(poolAddress), { cluster: "mainnet-beta" }))
    );
    if (!dlmmPool) {
      result.blocker = err || "DLMM.create failed";
      result.rpc_error_type = "create_failed";
      result.latency_ms = now() - t0;
      return result;
    }
    result.active_bin_id = dlmmPool.lbPair?.activeId ?? null;
    result.bin_array_attempted = true;
    const [binArrays, baErr] = await safeCall(() =>
      withFallback((c) => dlmmPool.getBinArrayForSwap(true, 1))
    );
    if (binArrays) {
      result.bin_array_success = true;
      result.bin_count = binArrays.length;
      let totalX = 0n, totalY = 0n;
      for (const ba of binArrays) {
        // bin array has bins[]; we sum xAmount / yAmount from bins if present
        const bins = ba?.account?.bins ?? ba?.bins ?? [];
        for (const b of bins) {
          if (b?.amountX !== undefined) totalX += BigInt(b.amountX.toString());
          if (b?.amountY !== undefined) totalY += BigInt(b.amountY.toString());
          // some SDK versions use xAmount/yAmount keys
          if (b?.xAmount !== undefined) totalX += BigInt(b.xAmount.toString());
          if (b?.yAmount !== undefined) totalY += BigInt(b.yAmount.toString());
        }
      }
      result.total_x_amount = totalX > 0n ? totalX.toString() : null;
      result.total_y_amount = totalY > 0n ? totalY.toString() : null;
      result.confidence = 0.6;
    } else {
      result.blocker = baErr;
      result.rpc_error_type = baErr && baErr.includes("410") ? "rpc_410_gone" : (baErr && baErr.includes("403") ? "rpc_403_forbidden" : "unknown");
      result.confidence = 0.0;
    }
  } catch (e) {
    result.blocker = String(e?.message ?? e);
    result.rpc_error_type = "exception";
    result.confidence = 0.0;
  }
  result.latency_ms = now() - t0;
  return result;
}

async function attemptQuote(poolAddress, notionalAmount, swapYtoX) {
  const t0 = now();
  const result = {
    pool_address: poolAddress,
    notional_usd: "10U" === null ? "" : (notionalAmount === 10_000_000 ? "10U" : (notionalAmount === 20_000_000 ? "20U" : "other")),
    amount_in_raw: notionalAmount.toString(),
    token_in: swapYtoX ? "Y" : "X",
    token_out: swapYtoX ? "X" : "Y",
    quote_attempted: true,
    quote_success: false,
    amount_out_raw: null,
    fee: null,
    bins_crossed: null,
    blocker: null,
    confidence: 0.0,
    latency_ms: 0,
  };

  let dlmmPool = null;
  try {
    let err = null;
    [dlmmPool, err] = await safeCall(() =>
      withFallback((c) => DLMM.create(c, new PublicKey(poolAddress), { cluster: "mainnet-beta" }))
    );
    if (!dlmmPool) {
      result.blocker = err || "DLMM.create failed";
      result.latency_ms = now() - t0;
      return result;
    }

    const [binArrays, baErr] = await safeCall(() =>
      withFallback((c) => dlmmPool.getBinArrayForSwap(swapYtoX, 4))
    );
    if (!binArrays) {
      result.blocker = baErr;
      result.latency_ms = now() - t0;
      return result;
    }

    const { BN } = require("@coral-xyz/anchor");
    const inAmount = new BN(notionalAmount);
    const allowedSlippage = new BN(50);
    const [quote, qErr] = await safeCall(() =>
      dlmmPool.swapQuote(inAmount, swapYtoX, allowedSlippage, binArrays, false, 3)
    );
    if (!quote) {
      result.blocker = qErr;
      result.latency_ms = now() - t0;
      return result;
    }
    result.quote_success = true;
    result.amount_out_raw = bnOrZero(quote.outAmount);
    result.fee = bnOrZero(quote.totalFeeAmount);
    result.bins_crossed = quote.binArraysCovered ?? null;
    result.confidence = 0.9;
  } catch (e) {
    result.blocker = String(e?.message ?? e);
  }
  result.latency_ms = now() - t0;
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runId = args["run-id"] || "unknown";
  const outputDir = args["output-dir"] || `reports/lp_meteora_dlmm_known_pool_connector/${runId}/connector_output`;
  const rpcRedacted = args["rpc-url-redacted-source"] || "<redacted_public_rpc>";
  const knownPoolFeedPath = args["known-pool-feed"];
  const mode = args["mode"] || "snapshot";

  if (!knownPoolFeedPath || !fs.existsSync(knownPoolFeedPath)) {
    console.error("ERROR: --known-pool-feed <PATH> required and must exist");
    process.exit(2);
  }

  // Load known pool feed
  const feed = JSON.parse(fs.readFileSync(knownPoolFeedPath, "utf8"));
  const selectedPools = feed.pools
    .filter((p) => p.selected_for_sdk_smoke)
    .map((p) => p.pool_address);

  // Prepare output dir
  fs.mkdirSync(outputDir, { recursive: true });
  const logLines = [];
  function log(s) {
    const line = `[${new Date().toISOString()}] ${s}`;
    console.log(line);
    logLines.push(line);
  }
  log(`connector_v1 started: run_id=${runId} mode=${mode} rpc_redacted_source=${rpcRedacted}`);
  log(`known_pool_feed_path=${knownPoolFeedPath} pools=${selectedPools.length}`);

  const connectorSummary = {
    run_id: runId,
    stage: "LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1",
    rpc_url_redacted_source: rpcRedacted,
    sdk_package: "@meteora-ag/dlmm",
    sdk_package_version: "1.9.10",
    cluster: "mainnet-beta",
    mode: mode,
    pools_attempted: selectedPools.length,
    pools: [],
    timestamp_utc: new Date().toISOString(),
    solana_wallet_or_keypair_touched: false,
    transaction_sent: false,
    signer_used: false,
    wallet_adapter_used: false,
    swap_transaction_built: false,
    open_lp_called: false,
    close_lp_called: false,
    collect_fee_called: false,
    bridge_called: false,
  };

  // Stage D: known_pool_universe (just re-emit selected pools)
  {
    const universeCsv = path.join(outputDir, "known_pool_universe.csv");
    const header = ["pool_address", "source", "source_file", "source_confidence", "selected_for_snapshot", "expected_owner_program", "previous_smoke_status", "invalid_reason"];
    const rows = feed.pools.map((p) => ({
      pool_address: p.pool_address,
      source: p.source,
      source_file: p.source_file,
      source_confidence: p.source_confidence,
      selected_for_snapshot: p.selected_for_sdk_smoke ? "yes" : "no",
      expected_owner_program: p.expected_owner_program,
      previous_smoke_status: p.selected_for_sdk_smoke ? "verified_v3" : "skipped_not_on_mainnet",
      invalid_reason: p.invalid_reason || "",
    }));
    writeCsv(universeCsv, header, rows);
    log(`wrote ${universeCsv} (${rows.length} rows)`);
  }

  // Stage E + F: per-pool decode + fee
  const poolSnapshotResults = [];
  const feeSnapshotResults = [];
  for (const p of selectedPools) {
    log(`decode pool: ${p}`);
    const dec = await decodePool(p);
    poolSnapshotResults.push(dec);
    connectorSummary.pools.push({
      pool_address: p,
      decode_status: dec.sdk_decode_success ? "ok" : "failed",
      decode_error: dec.create_error || dec.fatal_error,
    });
    log(`  -> sdk_decode_success=${dec.sdk_decode_success} token_x=${dec.token_x_mint} token_y=${dec.token_y_mint} active_bin=${dec.active_bin_id}`);
    if (dec.fee_info_available) {
      feeSnapshotResults.push({
        pool_address: p,
        base_fee_bps: dec.base_fee_bps,
        max_fee_bps: dec.max_fee_bps,
        protocol_fee_bps: dec.protocol_fee_bps,
        fee_info_available: true,
        source_method: "dlmmPool.getFeeInfo()",
        confidence: 0.95,
        invalid_reason: "",
      });
    } else {
      feeSnapshotResults.push({
        pool_address: p,
        base_fee_bps: null,
        max_fee_bps: null,
        protocol_fee_bps: null,
        fee_info_available: false,
        source_method: "dlmmPool.getFeeInfo()",
        confidence: 0.0,
        invalid_reason: dec.get_fee_info_error || "fee_info_unavailable",
      });
    }
  }

  // Stage E outputs
  {
    const psCsv = path.join(outputDir, "pool_snapshot.csv");
    const psJson = path.join(outputDir, "pool_snapshot.json");
    const header = [
      "pool_address", "token_x_mint", "token_y_mint", "token_x_decimals", "token_y_decimals",
      "bin_step", "active_bin_id", "active_price", "reserve_x_raw", "reserve_y_raw",
      "base_fee_bps", "max_fee_bps", "protocol_fee_bps", "volatility_accumulator",
      "data_len", "owner_program", "sdk_decode_success", "confidence", "invalid_reason"
    ];
    const rows = poolSnapshotResults.map((r) => ({
      pool_address: r.pool_address,
      token_x_mint: r.token_x_mint,
      token_y_mint: r.token_y_mint,
      token_x_decimals: r.token_x_decimals,
      token_y_decimals: r.token_y_decimals,
      bin_step: r.bin_step,
      active_bin_id: r.active_bin_id,
      active_price: r.active_price,
      reserve_x_raw: r.reserve_x_raw,
      reserve_y_raw: r.reserve_y_raw,
      base_fee_bps: r.base_fee_bps,
      max_fee_bps: r.max_fee_bps,
      protocol_fee_bps: r.protocol_fee_bps,
      volatility_accumulator: r.volatility_accumulator,
      data_len: r.data_len,
      owner_program: r.pool_owner,
      sdk_decode_success: r.sdk_decode_success,
      confidence: r.sdk_decode_success ? 0.9 : 0.0,
      invalid_reason: r.create_error || r.fatal_error || "",
    }));
    writeCsv(psCsv, header, rows);
    fs.writeFileSync(psJson, JSON.stringify(poolSnapshotResults, null, 2));
    log(`wrote ${psCsv} + ${psJson} (${rows.length} rows)`);
  }

  // Stage F outputs
  {
    const fsCsv = path.join(outputDir, "fee_snapshot.csv");
    const fsJson = path.join(outputDir, "fee_snapshot.json");
    const header = ["pool_address", "base_fee_bps", "max_fee_bps", "dynamic_fee_components", "fee_info_available", "source_method", "confidence", "invalid_reason"];
    const rows = feeSnapshotResults.map((r) => ({
      pool_address: r.pool_address,
      base_fee_bps: r.base_fee_bps,
      max_fee_bps: r.max_fee_bps,
      dynamic_fee_components: "",  // SDK returns baseFeeRatePercentage / maxFeeRatePercentage
      fee_info_available: r.fee_info_available,
      source_method: r.source_method,
      confidence: r.confidence,
      invalid_reason: r.invalid_reason,
    }));
    writeCsv(fsCsv, header, rows);
    fs.writeFileSync(fsJson, JSON.stringify(feeSnapshotResults, null, 2));
    log(`wrote ${fsCsv} + ${fsJson} (${rows.length} rows)`);
  }

  // Stage G: bin_liquidity attempt
  const binLiquidityResults = [];
  for (const p of selectedPools) {
    log(`bin_liquidity attempt: ${p}`);
    const r = await attemptBinLiquidity(p);
    binLiquidityResults.push(r);
    log(`  -> bin_array_success=${r.bin_array_success} blocker=${r.blocker ? r.blocker.slice(0, 60) : "none"}`);
  }
  {
    const blCsv = path.join(outputDir, "bin_liquidity_snapshot.csv");
    const blJson = path.join(outputDir, "bin_liquidity_snapshot.json");
    const header = ["pool_address", "active_bin_id", "bin_array_attempted", "bin_array_success", "bin_count", "total_x_amount", "total_y_amount", "blocker", "rpc_error_type", "confidence"];
    const rows = binLiquidityResults.map((r) => ({
      pool_address: r.pool_address,
      active_bin_id: r.active_bin_id,
      bin_array_attempted: r.bin_array_attempted,
      bin_array_success: r.bin_array_success,
      bin_count: r.bin_count,
      total_x_amount: r.total_x_amount,
      total_y_amount: r.total_y_amount,
      blocker: r.blocker,
      rpc_error_type: r.rpc_error_type,
      confidence: r.confidence,
    }));
    writeCsv(blCsv, header, rows);
    fs.writeFileSync(blJson, JSON.stringify(binLiquidityResults, null, 2));
    log(`wrote ${blCsv} + ${blJson} (${rows.length} rows)`);
  }

  // Stage H: quote attempt (only if mode includes quote-smoke)
  const quoteResults = [];
  if (mode === "quote-smoke" || mode === "all") {
    for (const p of selectedPools) {
      // Determine Y token: for both V3 pools, Y is USDC, so swapYtoX=true (USDC -> X)
      const dec = poolSnapshotResults.find((r) => r.pool_address === p);
      const yMint = dec?.token_y_mint;
      const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
      const swapYtoX = (yMint === USDC);
      for (const notional of [10_000_000, 20_000_000]) {
        log(`quote attempt: ${p} notional=${notional} swapYtoX=${swapYtoX}`);
        const r = await attemptQuote(p, notional, swapYtoX);
        quoteResults.push(r);
        log(`  -> quote_success=${r.quote_success} blocker=${r.blocker ? r.blocker.slice(0, 60) : "none"}`);
      }
    }
    {
      const qCsv = path.join(outputDir, "quote_snapshot.csv");
      const qJson = path.join(outputDir, "quote_snapshot.json");
      const header = ["pool_address", "notional_usd", "token_in", "token_out", "amount_in_raw", "quote_attempted", "quote_success", "amount_out_raw", "price_impact", "fee", "bins_crossed", "blocker", "confidence", "invalid_reason"];
      const rows = quoteResults.map((r) => ({
        pool_address: r.pool_address,
        notional_usd: r.notional_usd,
        token_in: r.token_in,
        token_out: r.token_out,
        amount_in_raw: r.amount_in_raw,
        quote_attempted: r.quote_attempted,
        quote_success: r.quote_success,
        amount_out_raw: r.amount_out_raw,
        price_impact: "",  // SDK doesn't return directly
        fee: r.fee,
        bins_crossed: r.bins_crossed,
        blocker: r.blocker,
        confidence: r.confidence,
        invalid_reason: r.blocker || "",
      }));
      writeCsv(qCsv, header, rows);
      fs.writeFileSync(qJson, JSON.stringify(quoteResults, null, 2));
      log(`wrote ${qCsv} + ${qJson} (${rows.length} rows)`);
    }
  } else {
    log("quote mode skipped (mode != quote-smoke/all)");
  }

  // Write summary
  connectorSummary.pool_snapshot_success_count = poolSnapshotResults.filter((r) => r.sdk_decode_success).length;
  connectorSummary.fee_snapshot_success_count = feeSnapshotResults.filter((r) => r.fee_info_available).length;
  connectorSummary.bin_liquidity_snapshot_success_count = binLiquidityResults.filter((r) => r.bin_array_success).length;
  connectorSummary.quote_snapshot_success_count = quoteResults.filter((r) => r.quote_success).length;
  connectorSummary.quote_snapshot_attempted_count = quoteResults.length;
  fs.writeFileSync(path.join(outputDir, "connector_summary.json"), JSON.stringify(connectorSummary, null, 2));
  log(`wrote ${path.join(outputDir, "connector_summary.json")}`);

  // Write run.log
  fs.writeFileSync(path.join(outputDir, "run.log"), logLines.join("\n") + "\n");

  // Exit code 0 if at least pool_snapshot and fee_snapshot worked
  const ok = connectorSummary.pool_snapshot_success_count > 0 && connectorSummary.fee_snapshot_success_count > 0;
  log(`exit: ${ok ? 0 : 1}`);
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(3);
});
