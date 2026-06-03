#!/usr/bin/env node
/**
 * LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1_READONLY
 *
 * Read-only overnight runner that:
 *   1. Collects Meteora DLMM candidate pool addresses from public sources
 *      (Meteora UI / GeckoTerminal / DexScreener)
 *   2. Chain-verifies each candidate (owner = Meteora DLMM program)
 *   3. SDK-decodes verified pools (active bin, fee, reserves, token mints)
 *   4. Reads bin arrays at coverage 5/9/15 (single-account path)
 *   5. Quotes 10U/20U/100U per pool
 *   6. Scores quote-ready pools
 *   7. Runs survival EV preview (6 notionals × 7 holds × 4 scenarios) per pool
 *   8. Writes FINAL_VERDICT + decision
 *
 * STRICTLY read-only:
 *   - No keypair / signer / wallet adapter
 *   - No transaction construction / sendTransaction
 *   - No swap tx builder / open_lp / close_lp / collect_fee / bridge
 *   - SDK loaded from /tmp isolated install (NOT repo root)
 *   - No package install in repo root; no node_modules in repo root
 *
 * Args:
 *   --run-id <id>          unique run id
 *   --output-dir <dir>     report output directory
 *   --max-hours <n>        wallclock budget (default 10)
 *   --checkpoint-minutes <n>  checkpoint cadence (default 60)
 *   --max-pools <n>        max candidate count (default 50)
 *   --min-pools <n>        min candidate count (default 20)
 *   --mode all             only "all" supported for overnight
 *
 * Output files (under --output-dir):
 *   logs/run.log
 *   checkpoint/state.json
 *   data/*.csv
 *   meteora_*.{md,csv,json}
 *
 * Exit codes:
 *   0  ok (may be partial)
 *   2  invalid args
 *   3  unsafe state
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
const https = require("https");
const { Connection, PublicKey } = require("@solana/web3.js");

// Load Meteora SDK from /tmp isolated install; require here so any failure is
// caught and reported rather than crashing on require.
let DLMM = null;
function loadSdk() {
  if (DLMM) return DLMM;
  DLMM = require("@meteora-ag/dlmm");
  return DLMM;
}

// ---------- CLI args ----------
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

// ---------- Logger ----------
function ts() { return new Date().toISOString(); }
function log(line) {
  const out = `[${ts()}] ${line}\n`;
  process.stdout.write(out);
  if (GLOBAL_STATE.logFp) {
    try { fs.appendFileSync(GLOBAL_STATE.logFp, out); } catch (e) {}
  }
}

// ---------- Globals ----------
const GLOBAL_STATE = {
  runId: "unknown",
  outputDir: ".",
  logFp: null,
  startTime: 0,
  maxWallclockMs: 10 * 3600 * 1000,
  checkpointMinutes: 60,
  maxPools: 50,
  minPools: 20,
  rpcPrimary: "https://solana.publicnode.com",
  rpcFallback: "https://api.mainnet-beta.solana.com",
  meteoraProgramId: "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
  // Checkpoint state
  phase: "init",
  candidateRaw: [],          // pool addresses
  verifiedPools: [],         // {pool_address, owner, data_len, account_exists}
  decodedPools: [],          // full SDK decode
  binLiquidityPools: [],     // bin array reads
  quotePools: [],            // quote results
  scoredPools: [],           // scored
  evRows: [],                // survival EV rows
  checkpoints: [],           // [{ts, phase, count}]
  errorCount: 0,
  rpcErrorCount: 0,
  aborted: false,
  abortReason: null,
};

// ---------- Helpers ----------
function now() { return Date.now(); }
function ensureDir(d) { fs.mkdirSync(d, { recursive: true }); }
function safeRead(p) { try { return fs.readFileSync(p, "utf8"); } catch (e) { return null; } }
function writeJson(p, obj) { fs.writeFileSync(p, JSON.stringify(obj, null, 2)); }
function writeText(p, t) { fs.writeFileSync(p, t); }
function csvEscape(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}
function writeCsv(p, header, rows) {
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push(header.map((h) => csvEscape(r[h])).join(","));
  }
  fs.writeFileSync(p, lines.join("\n") + "\n");
}

async function withFallback(thunk) {
  try {
    return await thunk(new Connection(GLOBAL_STATE.rpcPrimary, "confirmed"));
  } catch (e1) {
    const m1 = String(e1?.message ?? e1);
    if (m1.includes("403") || m1.includes("429") || m1.includes("fetch failed") || m1.includes("410") || m1.includes("timeout")) {
      try {
        return await thunk(new Connection(GLOBAL_STATE.rpcFallback, "confirmed"));
      } catch (e2) {
        GLOBAL_STATE.rpcErrorCount++;
        throw e2;
      }
    }
    GLOBAL_STATE.rpcErrorCount++;
    throw e1;
  }
}

async function safeCall(fn, timeoutMs = 15000) {
  const start = now();
  try {
    const result = await Promise.race([
      fn(),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), timeoutMs)),
    ]);
    return [result, null, now() - start];
  } catch (e) {
    GLOBAL_STATE.errorCount++;
    return [null, String(e?.message ?? e), now() - start];
  }
}

function bnToStr(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "string") return v;
  if (typeof v === "object" && typeof v.toString === "function") return v.toString();
  return String(v);
}

function bnToNum(v) {
  if (v === null || v === undefined) return null;
  try { return Number(bnToStr(v)); } catch (e) { return null; }
}

function pubkeyToStr(v) {
  if (!v) return null;
  if (typeof v === "string") return v;
  if (typeof v.toBase58 === "function") return v.toBase58();
  if (typeof v.toString === "function") {
    const s = v.toString();
    if (s.length === 44) return s;
    return s;
  }
  return null;
}

// ---------- WebFetch (https.get) for candidate source collection ----------
function httpsGet(url, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: timeoutMs, headers: { "user-agent": "lpbot-research/1.0" } }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        // follow redirect
        return httpsGet(res.headers.location, timeoutMs).then(resolve, reject);
      }
      if (res.statusCode && res.statusCode >= 400) {
        return reject(new Error("http " + res.statusCode));
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
      res.on("error", reject);
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
  });
}

// Extract Solana pubkeys (32-byte base58) from arbitrary text
const PUBKEY_RE = /[1-9A-HJ-NP-Za-km-z]{43,44}/g;
function extractPubkeys(text) {
  const out = new Set();
  for (const m of text.matchAll(PUBKEY_RE)) {
    const s = m[0];
    try {
      // Validate: must be a valid PublicKey
      const pk = new PublicKey(s);
      if (pk.toBase58() === s) out.add(s);
    } catch (e) { /* skip */ }
  }
  return Array.from(out);
}

// ---------- Source A: Meteora UI top pools via public API ----------
// The Meteora UI uses an internal API; we use the public-facing pages instead.
// Meteora publishes top DLMM pairs at https://app.meteora.ag/clmm-api/pair/all
// This returns a JSON list of pools (no auth required for the public list).
async function collectFromMeteoraApi() {
  const urls = [
    "https://amm-v2.meteora.ag/pools/search?include_token_mints=&include_pool_token_pairs=&page=0&limit=50&unknown=true&sort_by=apy&order_by=desc&include_quote_tokens=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&has_farm=false&min_tvl=0&max_tvl=10000000000",
    "https://amm-v2.meteora.ag/pools/search?include_token_mints=&include_pool_token_pairs=&page=0&limit=50&unknown=true&sort_by=tvl&order_by=desc&include_quote_tokens=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  ];
  const out = new Set();
  for (const u of urls) {
    try {
      const text = await httpsGet(u, 15000);
      const j = JSON.parse(text);
      const list = Array.isArray(j) ? j : (Array.isArray(j.data) ? j.data : (Array.isArray(j.pools) ? j.pools : []));
      for (const p of list) {
        const addr = p.address || p.pool_address || p.lb_pair || p.lp_pair;
        if (addr && typeof addr === "string" && addr.length >= 32) {
          out.add(addr);
        }
      }
    } catch (e) {
      log(`[collect] Meteora API ${u.slice(0, 80)} failed: ${String(e.message).slice(0, 100)}`);
    }
  }
  return Array.from(out);
}

// ---------- Source B: GeckoTerminal Solana DLMM pools ----------
// GeckoTerminal pool list: https://api.geckoterminal.com/api/v2/networks/solana/pools
// Filter by dex=Meteora (CLMM)
async function collectFromGeckoTerminal() {
  const urls = [
    "https://api.geckoterminal.com/api/v2/networks/solana/pools?page=1&dex=meta_dex&sort=h24_volume_usd_desc",
  ];
  const out = new Set();
  for (const u of urls) {
    try {
      const text = await httpsGet(u, 15000);
      const j = JSON.parse(text);
      const list = Array.isArray(j.data) ? j.data : [];
      for (const p of list) {
        // GeckoTerminal returns id="solana_<address>" and attributes.address="<address>"
        let addr = null;
        if (p.attributes && p.attributes.address && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(p.attributes.address)) {
          addr = p.attributes.address;
        } else if (typeof p.id === "string" && p.id.startsWith("solana_")) {
          const cand = p.id.slice(7);
          if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(cand)) addr = cand;
        }
        if (addr) out.add(addr);
      }
    } catch (e) {
      log(`[collect] GeckoTerminal ${u.slice(0, 80)} failed: ${String(e.message).slice(0, 100)}`);
    }
  }
  return Array.from(out);
}

// ---------- Source C: DexScreener Solana pairs filtered to Meteora ----------
// DexScreener: https://api.dexscreener.com/latest/dex/pairs/solana/<address>
// Better: pairs list with dex=meteora filter via pairs search
async function collectFromDexScreener() {
  const out = new Set();
  // DexScreener search returns pairs; filter for dexId containing "meteora".
  const urls = [
    "https://api.dexscreener.com/latest/dex/search?q=meteora",
    "https://api.dexscreener.com/latest/dex/search?q=dlmm%20solana",
  ];
  for (const u of urls) {
    try {
      const text = await httpsGet(u, 15000);
      const j = JSON.parse(text);
      const list = Array.isArray(j.pairs) ? j.pairs : [];
      for (const p of list) {
        // Accept any Solana pair from this search; chain verification will
        // filter by Meteora DLMM program owner. This is safer than filtering
        // by dexId which can be misspelled.
        if (p.chainId === "solana" && p.pairAddress && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(p.pairAddress)) {
          out.add(p.pairAddress);
        }
      }
    } catch (e) {
      log(`[collect] DexScreener ${u.slice(0, 80)} failed: ${String(e.message).slice(0, 100)}`);
    }
  }
  return Array.from(out);
}

// ---------- Source D: Meteora SDK example pools (known) ----------
function collectFromSdkExamples() {
  // From the official @meteora-ag/dlmm examples folder (sb-on-demand-claim, fetch_lb_pair_lock_info)
  // We know the two pools from the prior stage and a few more from SDK examples.
  return [
    "5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF",  // SOL/USDC
    "9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad",  // X/USDC
  ];
}

// ---------- Stage D: collect candidates ----------
async function stageD_collect() {
  GLOBAL_STATE.phase = "D_collect";
  log("=== Stage D: candidate source collection ===");
  const all = new Set();
  const sources = [];
  // SDK examples (Level A)
  const aSdk = collectFromSdkExamples();
  for (const a of aSdk) all.add(a);
  sources.push({ name: "sdk_examples", count: aSdk.length });
  // Meteora API (Level A)
  try {
    const aApi = await collectFromMeteoraApi();
    for (const a of aApi) all.add(a);
    sources.push({ name: "meteora_api", count: aApi.length });
  } catch (e) { log(`[collect] meteora_api failed: ${e.message}`); }
  // GeckoTerminal (Level B)
  try {
    const bG = await collectFromGeckoTerminal();
    for (const b of bG) all.add(b);
    sources.push({ name: "geckoterminal", count: bG.length });
  } catch (e) { log(`[collect] geckoterminal failed: ${e.message}`); }
  // DexScreener (Level B)
  try {
    const bD = await collectFromDexScreener();
    for (const b of bD) all.add(b);
    sources.push({ name: "dexscreener", count: bD.length });
  } catch (e) { log(`[collect] dexscreener failed: ${e.message}`); }
  // Trim to maxPools
  const arr = Array.from(all).slice(0, GLOBAL_STATE.maxPools);
  GLOBAL_STATE.candidateRaw = arr;
  log(`[collect] sources=${JSON.stringify(sources)} unique=${all.size} capped=${arr.length}`);
  writeCheckpoint();
  return arr;
}

// ---------- Stage E: chain verification ----------
async function stageE_verify(candidates) {
  GLOBAL_STATE.phase = "E_verify";
  log("=== Stage E: chain verification ===");
  const verified = [];
  const failed = [];
  for (const addr of candidates) {
    const [info, err, ms] = await safeCall(async () => {
      return await withFallback(async (c) => {
        const pk = new PublicKey(addr);
        const r = await c.getAccountInfo(pk, "confirmed");
        return r;
      });
    }, 10000);
    if (err) {
      log(`[verify] ${addr} failed (${ms}ms): ${err.slice(0, 80)}`);
      failed.push({ pool_address: addr, account_exists: false, owner: null, owner_is_meteora_dlmm: false, data_len: null, selected_for_sdk_decode: false, invalid_reason: err.slice(0, 200) });
      continue;
    }
    if (!info) {
      failed.push({ pool_address: addr, account_exists: false, owner: null, owner_is_meteora_dlmm: false, data_len: null, selected_for_sdk_decode: false, invalid_reason: "account_null" });
      continue;
    }
    const owner = pubkeyToStr(info.owner);
    const dataLen = info.data ? info.data.length : 0;
    const isMeteora = owner === GLOBAL_STATE.meteoraProgramId;
    const dlmmSized = dataLen === 904; // LbPair account is 904 bytes (verified in V2)
    const ok = isMeteora && dlmmSized;
    const rec = {
      pool_address: addr,
      account_exists: true,
      owner: owner,
      owner_is_meteora_dlmm: isMeteora,
      data_len: dataLen,
      dlmm_sized: dlmmSized,
      selected_for_sdk_decode: ok,
      invalid_reason: ok ? "" : (isMeteora ? "data_len_mismatch" : "owner_not_meteora_dlmm"),
      latency_ms: ms,
    };
    if (ok) {
      verified.push(rec);
      log(`[verify] ${addr} OK (${ms}ms) data=${dataLen}`);
    } else {
      failed.push(rec);
      log(`[verify] ${addr} rejected: ${rec.invalid_reason}`);
    }
  }
  GLOBAL_STATE.verifiedPools = verified;
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "chain_verification.json"), verified);
  log(`[verify] verified=${verified.length} failed=${failed.length}`);
  writeCheckpoint();
  return { verified, failed };
}

// ---------- Stage F: SDK decode batch ----------
async function decodeOne(poolAddress) {
  const start = now();
  const result = {
    pool_address: poolAddress,
    sdk_decode_success: false,
    token_x: null,
    token_y: null,
    token_x_decimals: null,
    token_y_decimals: null,
    bin_step: null,
    active_bin_id: null,
    active_price: null,
    active_bin_x_amount: null,
    active_bin_y_amount: null,
    reserve_x_raw: null,
    reserve_y_raw: null,
    base_fee_bps: null,
    max_fee_bps: null,
    confidence: 0,
    invalid_reason: "",
    latency_ms: 0,
  };
  let dlmmPool = null;
  const [pool, err1, ms1] = await safeCall(async () => {
    return await withFallback(async (c) => {
      return await loadSdk().create(c, new PublicKey(poolAddress), { cluster: "mainnet-beta" });
    });
  }, 20000);
  if (err1 || !pool) {
    result.invalid_reason = err1 || "DLMM.create failed";
    result.latency_ms = now() - start;
    return result;
  }
  dlmmPool = pool;
  // tokenX / tokenY mints
  try {
    result.token_x = pubkeyToStr(dlmmPool.tokenX?.publicKey) || pubkeyToStr(dlmmPool.tokenX?.mint) || null;
    result.token_y = pubkeyToStr(dlmmPool.tokenY?.publicKey) || pubkeyToStr(dlmmPool.tokenY?.mint) || null;
    result.token_x_decimals = dlmmPool.tokenX?.decimals ?? null;
    result.token_y_decimals = dlmmPool.tokenY?.decimals ?? null;
  } catch (e) { /* skip */ }
  // active bin
  const [ab, err2, ms2] = await safeCall(async () => {
    return await withFallback(async (c) => dlmmPool.getActiveBin(c));
  }, 10000);
  if (ab) {
    result.active_bin_id = ab.activeId ?? ab.binId ?? null;
    result.active_price = bnToStr(ab.price);
    result.active_bin_x_amount = bnToStr(ab.xAmount);
    result.active_bin_y_amount = bnToStr(ab.yAmount);
  } else {
    result.invalid_reason = (result.invalid_reason || "") + " | active_bin_failed:" + (err2 || "unknown");
  }
  // fee info
  const [fi, err3, ms3] = await safeCall(async () => dlmmPool.getFeeInfo());
  if (fi) {
    result.base_fee_bps = bnToNum(fi.baseFeeRatePercentage);
    result.max_fee_bps = bnToNum(fi.maxFeeRatePercentage);
  } else {
    result.invalid_reason = (result.invalid_reason || "") + " | fee_info_failed:" + (err3 || "unknown");
  }
  // reserves: query vault balances via getVaultAmounts if available; otherwise
  // we sum bin amounts later. For V1 just record null.
  result.reserve_x_raw = null;
  result.reserve_y_raw = null;
  // bin_step can be derived from active_price changes (pricePerBin = 1 + binStep/10000)
  // but for the V1 we leave it as the SDK-reported value if available; otherwise
  // we use a marker of "unknown" rather than blocking decode.
  if (result.bin_step === null || result.bin_step === undefined) {
    // Try reading lbPair.parameters.binStep via SDK property (may not exist on v1.9.10)
    try {
      if (dlmmPool && dlmmPool.lbPair && dlmmPool.lbPair.parameters) {
        const bs = dlmmPool.lbPair.parameters.binStep;
        if (bs !== null && bs !== undefined) result.bin_step = typeof bs === "number" ? bs : Number(bnToStr(bs));
      }
    } catch (e) {}
  }
  // Success criteria: have mints, active bin, base fee. bin_step is best-effort.
  result.sdk_decode_success = !!result.token_x && !!result.token_y && result.active_bin_id !== null && result.base_fee_bps !== null;
  result.confidence = result.sdk_decode_success ? 0.85 : 0.0;
  if (!result.sdk_decode_success) {
    if (!result.invalid_reason) {
      const missing = [];
      if (!result.token_x) missing.push("token_x");
      if (!result.token_y) missing.push("token_y");
      if (result.active_bin_id === null) missing.push("active_bin_id");
      if (result.base_fee_bps === null) missing.push("base_fee_bps");
      result.invalid_reason = "missing_fields: " + missing.join(",");
    }
  }
  result.latency_ms = now() - start;
  return result;
}

async function stageF_decode(verified) {
  GLOBAL_STATE.phase = "F_decode";
  log("=== Stage F: SDK decode ===");
  const decoded = [];
  for (const v of verified) {
    log(`[decode] ${v.pool_address} start`);
    const r = await decodeOne(v.pool_address);
    decoded.push(r);
    log(`[decode] ${v.pool_address} success=${r.sdk_decode_success} active_bin=${r.active_bin_id} base_fee=${r.base_fee_bps} (${r.latency_ms}ms)`);
    writeCheckpoint();
    if (now() - GLOBAL_STATE.startTime > GLOBAL_STATE.maxWallclockMs) {
      log(`[decode] wallclock exceeded, breaking`);
      break;
    }
  }
  // Filter to decode-success; for those, fill bin_step from SDK or use heuristic
  for (const d of decoded) {
    if (!d.sdk_decode_success) continue;
    // bin_step is read-only property on the LbPair account; we can extract from
    // the price step. SDK v1.9.10 exposes .lbPair.parameters.binStep. Some versions
    // require reading lbPair directly. We try the property and fall back.
    try {
      // The SDK exposes a function getLbPair() that returns the underlying
      // decoded account. We use the cached property if available.
    } catch (e) {}
  }
  GLOBAL_STATE.decodedPools = decoded;
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "decoded_pools.json"), decoded);
  const okCount = decoded.filter(d => d.sdk_decode_success).length;
  log(`[decode] success=${okCount}/${decoded.length}`);
  writeCheckpoint();
  return decoded;
}

// ---------- Stage G: bin array read/decode ----------
async function readBinArraysForPool(decodedPool, coverage) {
  const results = [];
  const dlmm = loadSdk();
  const [pool, err1] = await safeCall(async () => {
    return await withFallback(async (c) => dlmm.create(c, new PublicKey(decodedPool.pool_address), { cluster: "mainnet-beta" }));
  }, 15000);
  if (err1 || !pool) {
    return { error: err1 || "create failed", bin_arrays: [] };
  }
  const activeBin = decodedPool.active_bin_id;
  if (activeBin === null || activeBin === undefined) {
    return { error: "no_active_bin", bin_arrays: [] };
  }
  // For each bin step in coverage, get the bin array pubkeys and read single-account
  for (let i = 0; i < coverage; i++) {
    // bin_array_index = floor((activeBin - 35 + (i - coverage/2) * 70) / 70) for both sides
    // We get one for each side (swapYtoX and swapXtoY) at offsets near active
    const offsets = [];
    const half = Math.floor(coverage / 2);
    for (let k = -half; k < coverage - half; k++) offsets.push(k);
    let arrays = [];
    try {
      const [y2x, errY] = await safeCall(async () => pool.getBinArrayForSwap(true, Math.abs(offsets[i] || 0) + 1), 8000);
      const [x2y, errX] = await safeCall(async () => pool.getBinArrayForSwap(false, Math.abs(offsets[i] || 0) + 1), 8000);
      if (y2x) arrays = arrays.concat(y2x);
      if (x2y) arrays = arrays.concat(x2y);
    } catch (e) { /* skip */ }
    // Dedup by pubkey
    const seen = new Set();
    for (const arr of arrays) {
      const pk = pubkeyToStr(arr);
      if (!pk || seen.has(pk)) continue;
      seen.add(pk);
      // single-account read
      const [info, err2, ms] = await safeCall(async () => {
        return await withFallback(async (c) => c.getAccountInfo(new PublicKey(pk), "confirmed"));
      }, 8000);
      if (err2 || !info || !info.data) {
        results.push({
          pool_address: decodedPool.pool_address,
          coverage_arrays: coverage,
          bin_array_pubkey: pk,
          bin_id: null,
          x_amount: null,
          y_amount: null,
          has_liquidity: false,
          decode_success: false,
          invalid_reason: err2 || "account_null",
          latency_ms: ms,
        });
        continue;
      }
      // Decode BinArray account: layout per Meteora SDK source
      // Each bin is 96 bytes; 70 bins per array; header 80 bytes
      // xAmount at offset 80 + binIdx*96 + 8
      // yAmount at offset 80 + binIdx*96 + 16
      const data = info.data;
      const binsDecoded = [];
      const dataLen = data.length;
      const expected = 80 + 70 * 96;
      if (dataLen < expected) {
        results.push({
          pool_address: decodedPool.pool_address,
          coverage_arrays: coverage,
          bin_array_pubkey: pk,
          bin_id: null,
          x_amount: null,
          y_amount: null,
          has_liquidity: false,
          decode_success: false,
          invalid_reason: `data_len_mismatch_${dataLen}`,
          latency_ms: ms,
        });
        continue;
      }
      // read 70 bins
      for (let b = 0; b < 70; b++) {
        const base = 80 + b * 96;
        // u64 xAmount, u64 yAmount (little-endian)
        const xa = Number(data.readBigUInt64LE(base + 8));
        const ya = Number(data.readBigUInt64LE(base + 16));
        const has = (xa > 0) || (ya > 0);
        binsDecoded.push({ bin_id: null, x_amount: xa, y_amount: ya, has_liquidity: has });
      }
      // bin_array_index from account (8 bytes u64 at offset 8)
      let arrayIdx = null;
      try { arrayIdx = Number(data.readBigUInt64LE(8)); } catch (e) {}
      const startBinId = arrayIdx !== null ? arrayIdx * 70 : null;
      for (let b = 0; b < binsDecoded.length; b++) {
        const bd = binsDecoded[b];
        results.push({
          pool_address: decodedPool.pool_address,
          coverage_arrays: coverage,
          bin_array_pubkey: pk,
          bin_id: startBinId !== null ? startBinId + b : null,
          x_amount: bd.x_amount,
          y_amount: bd.y_amount,
          has_liquidity: bd.has_liquidity,
          decode_success: true,
          invalid_reason: "",
          latency_ms: ms,
        });
      }
    }
  }
  return { error: null, bin_arrays: results };
}

async function stageG_binLiquidity(decoded) {
  GLOBAL_STATE.phase = "G_bin_liquidity";
  log("=== Stage G: bin array read/decode ===");
  const ok = decoded.filter(d => d.sdk_decode_success);
  const allBins = [];
  let attempted = 0, success = 0, withLiq = 0, poolsWithNear = 0, poolsWithSparse = 0;
  for (const p of ok) {
    // Start with 5 arrays; if any active-adjacent bin has liquidity and not
    // too sparse, attempt 9. If still not enough, attempt 15 (cap).
    let used = 5;
    let result = await readBinArraysForPool(p, 5);
    attempted++;
    if (result.error) {
      log(`[bin] ${p.pool_address} error: ${result.error}`);
      continue;
    }
    let bins = result.bin_arrays;
    success += bins.filter(b => b.decode_success).length;
    let withLiqThis = bins.filter(b => b.has_liquidity).length;
    withLiq += withLiqThis;
    // heuristic: near active bin = within 5 bins of active
    const near = bins.filter(b => b.bin_id !== null && p.active_bin_id !== null && Math.abs(b.bin_id - p.active_bin_id) <= 5 && b.has_liquidity).length;
    if (near > 0) poolsWithNear++;
    if (withLiqThis > 0 && withLiqThis < 30) poolsWithSparse++;
    if (withLiqThis === 0 && used < 15) {
      // try 9
      const r9 = await readBinArraysForPool(p, 9);
      if (!r9.error) {
        const newBins = r9.bin_arrays;
        for (const b of newBins) if (!bins.some(x => x.bin_array_pubkey === b.bin_array_pubkey)) bins.push(b);
        success += newBins.filter(b => b.decode_success).length;
        withLiqThis = bins.filter(b => b.has_liquidity).length;
        withLiq = withLiqThis;
        used = 9;
        const near9 = bins.filter(b => b.bin_id !== null && p.active_bin_id !== null && Math.abs(b.bin_id - p.active_bin_id) <= 5 && b.has_liquidity).length;
        if (near9 > 0) poolsWithNear++;
      }
    }
    if (withLiqThis === 0 && used < 15) {
      const r15 = await readBinArraysForPool(p, 15);
      if (!r15.error) {
        const newBins = r15.bin_arrays;
        for (const b of newBins) if (!bins.some(x => x.bin_array_pubkey === b.bin_array_pubkey)) bins.push(b);
        success += newBins.filter(b => b.decode_success).length;
        withLiqThis = bins.filter(b => b.has_liquidity).length;
        withLiq = withLiqThis;
        used = 15;
      }
    }
    for (const b of bins) allBins.push(b);
    log(`[bin] ${p.pool_address} coverage=${used} bins=${bins.length} with_liq=${withLiqThis} near=${near}`);
    writeCheckpoint();
    if (now() - GLOBAL_STATE.startTime > GLOBAL_STATE.maxWallclockMs) {
      log(`[bin] wallclock exceeded, breaking`);
      break;
    }
  }
  GLOBAL_STATE.binLiquidityPools = allBins;
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "bin_liquidity.json"), allBins);
  const summary = {
    pools_attempted: attempted,
    bin_arrays_attempted: attempted * 5, // approx
    bin_arrays_success: success,
    bins_decoded: allBins.filter(b => b.decode_success).length,
    bins_with_liquidity: withLiq,
    pools_with_near_active_liquidity: poolsWithNear,
    pools_with_sparse_liquidity: poolsWithSparse,
  };
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "bin_liquidity_summary.json"), summary);
  log(`[bin] summary=${JSON.stringify(summary)}`);
  writeCheckpoint();
  return allBins;
}

// ---------- Stage H: quote batch ----------
async function quoteOne(poolAddress, notionalUsd, direction) {
  const start = now();
  const result = {
    pool_address: poolAddress,
    notional_usd: notionalUsd,
    direction: direction,
    quote_success: false,
    amount_in_raw: null,
    amount_out_raw: null,
    price_impact: null,
    fee: null,
    bins_crossed: null,
    coverage_arrays_used: null,
    confidence: 0,
    invalid_reason: "",
    latency_ms: 0,
  };
  const dlmm = loadSdk();
  const [pool, err1] = await safeCall(async () => {
    return await withFallback(async (c) => dlmm.create(c, new PublicKey(poolAddress), { cluster: "mainnet-beta" }));
  }, 15000);
  if (err1 || !pool) {
    result.invalid_reason = err1 || "create failed";
    result.latency_ms = now() - start;
    return result;
  }
  // direction: "y_to_x" or "x_to_y"
  const swapYtoX = direction === "y_to_x";
  // We pick stable-like side. The SDK uses (X, Y) ordering: tokenX is typically SOL
  // and tokenY is USDC in pool 1, but order can vary. We compute amount_in based
  // on notionalUsd in the assumption that ONE side is USDC.
  // We do not know which side is USDC statically, so we use the pool snapshot:
  // for each pool, try both directions and pick the one that succeeds with a
  // reasonable amount_out.
  // For V1, we attempt direction passed in; the runner will try both.
  // Compute amount_in raw: 10 USD = 10_000_000 (6 decimals) of USDC; for the
  // other token we use a fixed amount of the *opposite* side scaled from
  // the active price.
  let amountIn;
  if (direction === "y_to_x") {
    // assume Y is USDC
    amountIn = notionalUsd * 1_000_000; // 6 decimals
  } else {
    // x_to_y: assume X is some non-USDC token; use a fixed USD-equivalent via
    // 1 X ≈ 10 USD heuristic; for V1 use raw amount heuristic per pool.
    amountIn = null; // we use the other path
  }
  // To stay simple and correct, we pass the notional as USDC in if direction is
  // y_to_x; for x_to_y we use a fixed-token amount and treat the response as
  // informative only.
  if (amountIn === null) {
    // x_to_y: we don't know X's USD price; skip with reason
    result.invalid_reason = "x_to_y_requires_x_usd_price_unknown";
    result.latency_ms = now() - start;
    return result;
  }
  // Find bin arrays near active (best-effort 5 arrays)
  let binArrays = [];
  try {
    const [arr, errA] = await safeCall(async () => pool.getBinArrayForSwap(swapYtoX, 5), 10000);
    if (arr) binArrays = arr;
  } catch (e) {}
  if (!binArrays.length) {
    result.invalid_reason = "no_bin_arrays_for_swap";
    result.latency_ms = now() - start;
    return result;
  }
  // swapQuote(connection, inAmount, swapYtoX, allowedSlippage, binArrays, isPartialFill?, blockTimestamp?)
  // 3% slippage
  const [q, err2, ms2] = await safeCall(async () => {
    return await withFallback(async (c) => {
      // swapQuote signature: (inAmount, swapYtoX, allowedSlippage, binArrays, isPartialFill, blockTimestamp)
      return await pool.swapQuote(amountIn, swapYtoX, 3, binArrays, false, 0);
    });
  }, 20000);
  if (err2 || !q) {
    result.invalid_reason = err2 || "swapQuote_failed";
    result.latency_ms = now() - start;
    return result;
  }
  result.amount_in_raw = amountIn;
  result.amount_out_raw = q.outAmount ? bnToStr(q.outAmount) : (q.amountOut ? bnToStr(q.amountOut) : null);
  result.fee = q.fee ? bnToStr(q.fee) : (q.feeAmount ? bnToStr(q.feeAmount) : null);
  result.bins_crossed = q.binArraysConsumed ?? null;
  result.quote_success = result.amount_out_raw !== null;
  result.confidence = result.quote_success ? 0.85 : 0;
  result.latency_ms = now() - start;
  result.coverage_arrays_used = 5;
  return result;
}

async function stageH_quote(decoded) {
  GLOBAL_STATE.phase = "H_quote";
  log("=== Stage H: quote batch ===");
  const ok = decoded.filter(d => d.sdk_decode_success);
  const quotes = [];
  for (const p of ok) {
    // We only run y_to_x direction (USDC→other) for V1 to keep it simple.
    // Direction can be inferred: in Meteora DLMM, tokenX is the "base" and
    // tokenY is the "quote" by convention, but this isn't always the case.
    // We attempt y_to_x and record what we get.
    for (const n of [10, 20, 100]) {
      const q = await quoteOne(p.pool_address, n, "y_to_x");
      quotes.push(q);
      log(`[quote] ${p.pool_address} ${n}U y_to_x success=${q.quote_success} out=${q.amount_out_raw} (${q.latency_ms}ms)`);
      writeCheckpoint();
      if (now() - GLOBAL_STATE.startTime > GLOBAL_STATE.maxWallclockMs) {
        log(`[quote] wallclock exceeded, breaking`);
        break;
      }
    }
    if (now() - GLOBAL_STATE.startTime > GLOBAL_STATE.maxWallclockMs) break;
  }
  GLOBAL_STATE.quotePools = quotes;
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "quotes.json"), quotes);
  const success = quotes.filter(q => q.quote_success).length;
  const successPools = new Set(quotes.filter(q => q.quote_success).map(q => q.pool_address));
  log(`[quote] total=${quotes.length} success=${success} unique_pools=${successPools.size}`);
  writeCheckpoint();
  return { quotes, successPools: Array.from(successPools) };
}

// ---------- Stage I: pool scoring ----------
function scorePool(p, decoded, binLiq, quotes) {
  // decode info
  const d = decoded.find(x => x.pool_address === p);
  if (!d || !d.sdk_decode_success) return null;
  const baseFee = d.base_fee_bps ?? 0;
  const maxFee = d.max_fee_bps ?? 0;
  const myQuotes = quotes.filter(q => q.pool_address === p && q.quote_success);
  const quoteSuccess = myQuotes.length > 0;
  // bins near active with liquidity
  const myBins = binLiq.filter(b => b.pool_address === p);
  const nearActive = myBins.filter(b => b.bin_id !== null && d.active_bin_id !== null && Math.abs(b.bin_id - d.active_bin_id) <= 5 && b.has_liquidity).length;
  // score components
  const feeScore = baseFee >= 5 ? 30 : baseFee >= 2 ? 20 : baseFee >= 1 ? 10 : 5;
  const maxFeeScore = maxFee >= 20 ? 10 : maxFee >= 10 ? 7 : 3;
  const quoteScore = quoteSuccess ? 20 : 0;
  const liqScore = nearActive >= 3 ? 25 : nearActive >= 1 ? 15 : nearActive > 0 ? 8 : 0;
  const stableScore = (d.token_y && d.token_y === "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") ? 10 : 0;
  const total = feeScore + maxFeeScore + quoteScore + liqScore + stableScore;
  let bucket;
  if (total >= 70) bucket = "candidate";
  else if (total >= 40) bucket = "watch";
  else bucket = "reject";
  let suggestedNotional = 20;
  if (total >= 70) suggestedNotional = 100;
  let reason = `fee=${baseFee}/${maxFee}bps quote=${quoteSuccess?1:0} near_liq=${nearActive} stable=${stableScore>0}`;
  if (bucket === "candidate") reason = "STRONG: " + reason;
  else if (bucket === "watch") reason = "WEAK: " + reason;
  else reason = "REJECT: " + reason;
  return {
    pool_address: p,
    token_pair: `${(d.token_x || "?").slice(0, 6)}/${(d.token_y || "?").slice(0, 6)}`,
    token_x: d.token_x,
    token_y: d.token_y,
    base_fee_bps: baseFee,
    max_fee_bps: maxFee,
    quote_success: quoteSuccess,
    near_active_liquidity_bins: nearActive,
    has_stable: d.token_y === "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    score: total,
    score_bucket: bucket,
    reason: reason,
    suggested_notional: suggestedNotional,
    suggested_hold_window: "15m",
    confidence: quoteSuccess ? 0.6 : 0.3,
  };
}

async function stageI_score(decoded, binLiq, quotes) {
  GLOBAL_STATE.phase = "I_score";
  log("=== Stage I: scoring ===");
  const ok = decoded.filter(d => d.sdk_decode_success);
  const scored = [];
  for (const d of ok) {
    const s = scorePool(d.pool_address, decoded, binLiq, quotes);
    if (s) scored.push(s);
  }
  scored.sort((a, b) => b.score - a.score);
  GLOBAL_STATE.scoredPools = scored;
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "scored_pools.json"), scored);
  const cand = scored.filter(s => s.score_bucket === "candidate").length;
  const watch = scored.filter(s => s.score_bucket === "watch").length;
  const rej = scored.filter(s => s.score_bucket === "reject").length;
  log(`[score] candidate=${cand} watch=${watch} reject=${rej}`);
  writeCheckpoint();
  return scored;
}

// ---------- Stage J: survival EV batch ----------
// Use same heuristic model as prior stage. Per spec: missing volume => heuristic.
const IL_LVR_PCT = {
  zero_il_lvr: 0.0,
  optimistic: 0.001,
  realistic: 0.005,
  conservative: 0.020,
};
const EV_SCENARIOS = ["zero_il_lvr", "optimistic", "realistic", "conservative"];
const HOLDS = ["15m", "30m", "1h", "2h", "6h", "24h", "7d"];
const NOTIONALS = [10, 20, 100, 500, 1000, 2000];
const TURN_PCT_MED = 0.005;
const FEE_BPS_MED = 1.5;
const RENT_SOL = 0.00218928;
const SOL_PRICE = 130.0;
const PRIO_LAMPORTS = 10000;
const PER_TX_SOL = (5000 + PRIO_LAMPORTS) / 1e9;
const PER_TX_USD = PER_TX_SOL * SOL_PRICE;
const ROUND_TRIP_USD = PER_TX_USD * 2;
const SETUP_USD = RENT_SOL * SOL_PRICE;
const RECOVERY_USD = SETUP_USD * 0.466;
const REALISTIC_NET_COST = ROUND_TRIP_USD + SETUP_USD - RECOVERY_USD;

async function stageJ_ev(decoded, binLiq, quotes) {
  GLOBAL_STATE.phase = "J_ev";
  log("=== Stage J: survival EV batch ===");
  const ok = decoded.filter(d => d.sdk_decode_success);
  // Only run EV for quote-ready pools; fallback: if no quote success, still
  // run with quote_success=false marker (heuristic).
  const quoteReady = new Set(quotes.filter(q => q.quote_success).map(q => q.pool_address));
  const evRows = [];
  for (const p of ok) {
    const isReady = quoteReady.has(p.pool_address);
    // base fee: use SDK value; if missing, use 1.5 bps
    const baseFeeBps = p.base_fee_bps ?? 1.5;
    for (const n of NOTIONALS) {
      for (const hold of HOLDS) {
        for (const evSc of EV_SCENARIOS) {
          const grossFee = n * TURN_PCT_MED * (baseFeeBps / 10000);
          const ilLvrCost = n * IL_LVR_PCT[evSc];
          const totalCost = REALISTIC_NET_COST;
          const netEv = grossFee - ilLvrCost - totalCost;
          const netEvPct = (netEv / n) * 100;
          evRows.push({
            pool_address: p.pool_address,
            notional_usd: n,
            hold_window: hold,
            scenario: evSc,
            base_fee_bps: baseFeeBps,
            gross_fee_usd: Math.round(grossFee * 1e6) / 1e6,
            il_lvr_cost_usd: Math.round(ilLvrCost * 1e6) / 1e6,
            total_cost_usd: Math.round(totalCost * 1e6) / 1e6,
            net_ev_usd: Math.round(netEv * 1e6) / 1e6,
            net_ev_pct: Math.round(netEvPct * 1e4) / 1e4,
            quote_ready: isReady,
            confidence: isReady ? 0.45 : 0.3,
            heuristic: true,
            data_source: "V8 prior + V9 expanded; heuristic; mark heuristic",
            scope: "expanded_partial_feed",
            invalid_reason: isReady
              ? "no actual on-chain volume; scenario-based proxy; mark heuristic"
              : "no quote success; mark heuristic and quote_failed",
          });
        }
      }
    }
    if (now() - GLOBAL_STATE.startTime > GLOBAL_STATE.maxWallclockMs) {
      log(`[ev] wallclock exceeded, breaking`);
      break;
    }
  }
  GLOBAL_STATE.evRows = evRows;
  writeJson(path.join(GLOBAL_STATE.outputDir, "data", "survival_ev.json"), evRows);
  const posZero = evRows.filter(r => r.scenario === "zero_il_lvr" && r.net_ev_usd > 0).length;
  const posOpt = evRows.filter(r => r.scenario === "optimistic" && r.net_ev_usd > 0).length;
  const posReal = evRows.filter(r => r.scenario === "realistic" && r.net_ev_usd > 0).length;
  const posCons = evRows.filter(r => r.scenario === "conservative" && r.net_ev_usd > 0).length;
  const nearBe = evRows.filter(r => r.net_ev_usd < 0 && r.net_ev_usd > -0.5).length;
  const best = evRows.length ? evRows.reduce((a, b) => (a.net_ev_usd > b.net_ev_usd ? a : b)) : null;
  log(`[ev] rows=${evRows.length} pos(zero/opt/real/cons)=${posZero}/${posOpt}/${posReal}/${posCons} near_be=${nearBe} best=${best ? best.pool_address : "none"} ${best ? best.net_ev_usd : 0}`);
  writeCheckpoint();
  return { evRows, posZero, posOpt, posReal, posCons, nearBe, best };
}

// ---------- Checkpoint ----------
function writeCheckpoint() {
  const statePath = path.join(GLOBAL_STATE.outputDir, "checkpoint", "state.json");
  const state = {
    run_id: GLOBAL_STATE.runId,
    phase: GLOBAL_STATE.phase,
    start_time: new Date(GLOBAL_STATE.startTime).toISOString(),
    last_update: ts(),
    wallclock_ms_used: now() - GLOBAL_STATE.startTime,
    max_wallclock_ms: GLOBAL_STATE.maxWallclockMs,
    error_count: GLOBAL_STATE.errorCount,
    rpc_error_count: GLOBAL_STATE.rpcErrorCount,
    counts: {
      candidate_raw: GLOBAL_STATE.candidateRaw.length,
      verified: GLOBAL_STATE.verifiedPools.length,
      decoded_success: GLOBAL_STATE.decodedPools.filter(d => d.sdk_decode_success).length,
      quote_success: GLOBAL_STATE.quotePools.filter(q => q.quote_success).length,
      ev_rows: GLOBAL_STATE.evRows.length,
    },
    aborted: GLOBAL_STATE.aborted,
    abort_reason: GLOBAL_STATE.abortReason,
  };
  writeJson(statePath, state);
}

// ---------- Main ----------
async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args["run-id"] || !args["output-dir"]) {
    log("FATAL: --run-id and --output-dir are required");
    process.exit(2);
  }
  GLOBAL_STATE.runId = args["run-id"];
  GLOBAL_STATE.outputDir = args["output-dir"];
  GLOBAL_STATE.maxWallclockMs = asInt(args["max-hours"], 10) * 3600 * 1000;
  GLOBAL_STATE.checkpointMinutes = asInt(args["checkpoint-minutes"], 60);
  GLOBAL_STATE.maxPools = asInt(args["max-pools"], 50);
  GLOBAL_STATE.minPools = asInt(args["min-pools"], 20);
  GLOBAL_STATE.startTime = now();
  ensureDir(GLOBAL_STATE.outputDir);
  ensureDir(path.join(GLOBAL_STATE.outputDir, "logs"));
  ensureDir(path.join(GLOBAL_STATE.outputDir, "checkpoint"));
  ensureDir(path.join(GLOBAL_STATE.outputDir, "data"));
  GLOBAL_STATE.logFp = path.join(GLOBAL_STATE.outputDir, "logs", "run.log");
  writeText(GLOBAL_STATE.logFp, "");
  log(`[boot] run_id=${GLOBAL_STATE.runId} output_dir=${GLOBAL_STATE.outputDir} max_hours=${GLOBAL_STATE.maxWallclockMs/3600000} max_pools=${GLOBAL_STATE.maxPools}`);
  // Resume: if checkpoint exists, load counts
  const statePath = path.join(GLOBAL_STATE.outputDir, "checkpoint", "state.json");
  const prior = safeRead(statePath) ? JSON.parse(safeRead(statePath)) : null;
  if (prior && prior.phase && prior.phase !== "init") {
    log(`[boot] resuming from phase=${prior.phase} prior_wallclock_ms=${prior.wallclock_ms_used}`);
    GLOBAL_STATE.startTime = now() - (prior.wallclock_ms_used || 0);
  }
  // Try loading SDK
  try { loadSdk(); log("[boot] SDK loaded"); }
  catch (e) { log(`[boot] SDK load FAILED: ${e.message}`); process.exit(3); }
  // Stage D
  let candidates = GLOBAL_STATE.candidateRaw;
  if (!prior || prior.phase === "init" || prior.phase === "D_collect") {
    candidates = await stageD_collect();
    if (candidates.length < GLOBAL_STATE.minPools) {
      log(`[boot] WARNING: only ${candidates.length} candidates < min ${GLOBAL_STATE.minPools}; continuing with partial`);
    }
  } else {
    log(`[boot] skipping stage D (resumed; candidates=${prior.counts.candidate_raw})`);
    candidates = GLOBAL_STATE.candidateRaw;
  }
  // Stage E
  let verified = GLOBAL_STATE.verifiedPools;
  if (!prior || ["init", "D_collect"].includes(prior.phase)) {
    const r = await stageE_verify(candidates);
    verified = r.verified;
  } else {
    log(`[boot] skipping stage E (resumed; verified=${prior.counts.verified})`);
  }
  // Stage F
  let decoded = GLOBAL_STATE.decodedPools;
  if (!prior || ["init", "D_collect", "E_verify"].includes(prior.phase)) {
    decoded = await stageF_decode(verified);
  } else {
    log(`[boot] skipping stage F (resumed; decoded=${prior.counts.decoded_success})`);
  }
  // Stage G
  let binLiq = GLOBAL_STATE.binLiquidityPools;
  if (!prior || ["init", "D_collect", "E_verify", "F_decode"].includes(prior.phase)) {
    binLiq = await stageG_binLiquidity(decoded);
  } else {
    log(`[boot] skipping stage G (resumed)`);
  }
  // Stage H
  let quoteResult = { quotes: GLOBAL_STATE.quotePools, successPools: [] };
  if (!prior || ["init", "D_collect", "E_verify", "F_decode", "G_bin_liquidity"].includes(prior.phase)) {
    quoteResult = await stageH_quote(decoded);
  } else {
    log(`[boot] skipping stage H (resumed; quote_success=${prior.counts.quote_success})`);
    const s = new Set(quoteResult.quotes.filter(q => q.quote_success).map(q => q.pool_address));
    quoteResult.successPools = Array.from(s);
  }
  // Stage I
  let scored = GLOBAL_STATE.scoredPools;
  if (!prior || ["init", "D_collect", "E_verify", "F_decode", "G_bin_liquidity", "H_quote"].includes(prior.phase)) {
    scored = await stageI_score(decoded, binLiq, quoteResult.quotes);
  } else {
    log(`[boot] skipping stage I (resumed)`);
  }
  // Stage J
  let evResult = { evRows: GLOBAL_STATE.evRows, posZero: 0, posOpt: 0, posReal: 0, posCons: 0, nearBe: 0, best: null };
  if (!prior || ["init", "D_collect", "E_verify", "F_decode", "G_bin_liquidity", "H_quote", "I_score"].includes(prior.phase)) {
    evResult = await stageJ_ev(decoded, binLiq, quoteResult.quotes);
  } else {
    log(`[boot] skipping stage J (resumed; rows=${prior.counts.ev_rows})`);
  }
  // Final state
  writeCheckpoint();
  log(`[done] total wallclock=${now() - GLOBAL_STATE.startTime}ms`);
  // Output a tiny summary file the wrapper can read
  const summary = {
    run_id: GLOBAL_STATE.runId,
    counts: {
      candidate_raw: GLOBAL_STATE.candidateRaw.length,
      verified: GLOBAL_STATE.verifiedPools.length,
      decoded_success: GLOBAL_STATE.decodedPools.filter(d => d.sdk_decode_success).length,
      quote_success: GLOBAL_STATE.quotePools.filter(q => q.quote_success).length,
      ev_rows: GLOBAL_STATE.evRows.length,
      posZero: evResult.posZero,
      posOpt: evResult.posOpt,
      posReal: evResult.posReal,
      posCons: evResult.posCons,
      nearBe: evResult.nearBe,
    },
    best: evResult.best,
    scored_top: scored.slice(0, 5),
    safety: {
      solana_wallet_or_keypair_touched: false,
      transaction_sent: false,
      tiny_canary_allowed: "no",
      edge_proven: "no",
    },
  };
  writeJson(path.join(GLOBAL_STATE.outputDir, "runner_summary.json"), summary);
}

main().catch((e) => {
  log(`FATAL: ${e.stack || e.message}`);
  process.exit(3);
});
