const DLMM = require('@meteora-ag/dlmm');
const { StrategyType } = DLMM;
const { Connection, Keypair, PublicKey } = require('@solana/web3.js');
const BN = require('bn.js');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key || !key.startsWith('--') || value === undefined) {
      throw new Error(`invalid args near ${key || '<eof>'}`);
    }
    out[key.slice(2)] = value;
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv);
  const rpc = process.env.SOL_RPC_PRIMARY || 'https://solana-rpc.publicnode.com';
  const pool = new PublicKey(args.pool);
  const user = new PublicKey(args.user);
  const lowerPrice = Number(args['lower-price']);
  const upperPrice = Number(args['upper-price']);
  const amountXRaw = args['amount-x-raw'];
  const amountYRaw = args['amount-y-raw'];
  const slippagePct = Number(args['slippage-pct'] || '1');

  const connection = new Connection(rpc, 'processed');
  const dlmm = await DLMM.create(connection, pool);
  const activeBin = await dlmm.getActiveBin();
  const minBinId = dlmm.getBinIdFromPrice(lowerPrice, true);
  const maxBinId = dlmm.getBinIdFromPrice(upperPrice, false);
  const strategy = {
    minBinId,
    maxBinId,
    strategyType: StrategyType.Spot,
  };

  const position = Keypair.generate();
  const warnings = [];
  const originalConsoleError = console.error;
  console.error = (...items) => {
    warnings.push(items.map((item) => String(item)).join(' '));
  };

  let tx = null;
  let buildError = '';
  try {
    tx = await dlmm.initializePositionAndAddLiquidityByStrategy({
      positionPubKey: position.publicKey,
      totalXAmount: new BN(amountXRaw),
      totalYAmount: new BN(amountYRaw),
      strategy,
      user,
      slippage: slippagePct,
    });
  } catch (err) {
    buildError = err instanceof Error ? err.message : String(err);
  } finally {
    console.error = originalConsoleError;
  }

  let txBase64 = '';
  let feePayer = '';
  let recentBlockhash = '';
  let instructionCount = 0;
  let simulationErr = null;
  let simulationUnits = 0;
  let simulationLogs = [];
  let simulationRpcError = '';
  let simulationReplacementBlockhash = '';

  if (tx) {
    instructionCount = tx.instructions.length;
    feePayer = tx.feePayer ? tx.feePayer.toBase58() : '';
    recentBlockhash = tx.recentBlockhash || '';
    const raw = tx.serialize({ requireAllSignatures: false, verifySignatures: false });
    txBase64 = raw.toString('base64');
    const resp = await connection._rpcRequest('simulateTransaction', [
      txBase64,
      {
        encoding: 'base64',
        sigVerify: false,
        replaceRecentBlockhash: true,
        commitment: 'processed',
      },
    ]);
    if (resp.error) {
      simulationRpcError = JSON.stringify(resp.error);
    } else if (resp.result && resp.result.value) {
      simulationErr = resp.result.value.err;
      simulationUnits = resp.result.value.unitsConsumed || 0;
      simulationLogs = resp.result.value.logs || [];
      simulationReplacementBlockhash =
        (resp.result.value.replacementBlockhash && resp.result.value.replacementBlockhash.blockhash) || '';
    }
  }

  process.stdout.write(
    JSON.stringify({
      poolId: pool.toBase58(),
      user: user.toBase58(),
      positionPubkey: position.publicKey.toBase58(),
      activeBinId: activeBin.binId,
      activeBinPrice: String(activeBin.price),
      minBinId,
      maxBinId,
      strategyType: 'Spot',
      totalXAmountRaw: amountXRaw,
      totalYAmountRaw: amountYRaw,
      instructionCount,
      feePayer,
      recentBlockhash,
      txBase64,
      sdkWarnings: warnings,
      simulationErr,
      simulationUnits,
      simulationLogs,
      simulationRpcError,
      simulationReplacementBlockhash,
      buildError,
    })
  );
}

main().catch((err) => {
  process.stderr.write(err instanceof Error ? err.stack || err.message : String(err));
  process.exit(1);
});
