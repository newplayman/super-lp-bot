(function () {
    const charts = {
        tier: null,
        chain: null,
        cumulativePnl: null,
        revenueBreakdown: null,
        strategyRadar: null,
        auditDistribution: null,
        rebalanceTimeline: null,
        strategyComparison: null,
        knobCpu: null,
        knobMem: null,
        knobDisk: null
    };

    window.addEventListener('DOMContentLoaded', () => {
        if (window.lucide) lucide.createIcons();
        initCharts();
        bindReadOnlyInteractions();
        refreshDashboard();
        setInterval(refreshDashboard, window.DashboardConfig.refreshInterval || 15000);
        window.addEventListener('resize', () => Object.values(charts).forEach(chart => chart && chart.resize()));
    });

    async function refreshDashboard() {
        try {
            const res = await fetch(apiURL(), { cache: 'no-store' });
            if (!res.ok) throw new Error('API ' + res.status);
            const data = await res.json();
            document.getElementById('degrade-alert').classList.add('hidden');
            render(data);
        } catch (err) {
            const alert = document.getElementById('degrade-alert');
            alert.classList.remove('hidden');
            const hasToken = new URLSearchParams(location.search).get('token') || localStorage.getItem('lpbot_dashboard_token');
            alert.querySelector('span').textContent = hasToken ? '无法读取真实 API：token 可能错误或服务暂不可用' : '无法读取真实 API：URL 缺少 ?token=DashboardToken';
            appendLog('warn', 'dashboard', '无法读取真实 API: ' + err.message);
        }
    }

    function apiURL() {
        const params = new URLSearchParams(location.search);
        const tokenFromURL = params.get('token') || '';
        if (tokenFromURL) {
            try { localStorage.setItem('lpbot_dashboard_token', tokenFromURL); } catch (_) {}
        }
        let token = tokenFromURL;
        if (!token) {
            try { token = localStorage.getItem('lpbot_dashboard_token') || ''; } catch (_) { token = ''; }
        }
        const base = window.DashboardConfig.apiBaseUrl || '/api/dashboard';
        return base + (token ? '?token=' + encodeURIComponent(token) : '');
    }

    function render(data) {
        const marks = data.position_marks || [];
        const positions = data.positions || [];
        const closed = data.closed_positions || [];
        const decisions = data.decisions || [];
        const latestAudit = (data.strategy_audit || [])[0] || {};
        const health = data.health || {};
        const counts = data.counts || {};
        const markSeries = data.mark_series || [];
        const ledgerSeries = data.ledger_series || [];
        const ledgerSummary = data.ledger_summary || [];
        const baseCanary = data.base_canary || {};
        const canaryRounds = data.canary_rounds || [];
        const canarySummary = data.canary_summary || {};
        const solanaCanary = data.solana_canary || {};
        const currentLive = data.live_readiness || {};
        const canaryLive = data.canary_readiness || {};
        const live = canaryLive.build_mode ? canaryLive : currentLive;

        const totalValue = sum(marks, 'valuation_usd');
		const totalFees = sum(marks, 'fee_usd');
		const totalIL = sum(marks, 'il_usd');
		const totalNet = sum(marks, 'net_pnl_usd');
		const summaryByKind = ledgerSummary.reduce((out, item) => {
			out[item.kind] = num(item.amount);
			return out;
		}, {});
		const ledgerLatest = ledgerSeries.length ? ledgerSeries[ledgerSeries.length - 1] : {};
		const ledgerFeeTotal = ledgerSeries.length ? num(ledgerLatest.fee_usd) : totalFees;
		const ledgerILTotal = ledgerSeries.length ? num(ledgerLatest.il_usd) : totalIL;
		const ledgerNetTotal = ledgerSeries.length ? num(ledgerLatest.net_pnl_usd) : totalNet;
		const ledgerFee24h = summaryByKind.fee || 0;
		const ledgerIL24h = summaryByKind.il || 0;
		const ledgerNet24h = ledgerFee24h + ledgerIL24h;
		const activeAmount = sum(marks, 'amount_usd');
        const worstILPct = marks.reduce((max, m) => Math.max(max, Math.abs(num(m.il_usd)) / Math.max(num(m.amount_usd), 1) * 100), 0);
        const selected = num(latestAudit.selected);
        const scanned = num(latestAudit.scanned);
        const chainFailures = num(health.recent_chain_failures);
        const pipelineFailures = num(health.recent_pipeline_failures);
        const staleMarks = num(health.recent_stale_marks);
        const healthPct = Math.max(0, 100 - chainFailures * 8 - pipelineFailures * 8 - staleMarks * 5);

        setText('update-time', new Date(data.generated_at || Date.now()).toLocaleString());
        setText('val-aum', money(totalValue));
        setText('val-deployed', money(activeAmount));
        setText('val-available', money(0));
		setText('val-pnl-today', signedMoney(ledgerNet24h));
		setText('val-pnl-7d', signedMoney(ledgerNetTotal));
		setText('val-pnl-total', signedMoney(ledgerNetTotal));
		setText('val-fee', money(ledgerFeeTotal));
		setText('val-incentives', '0');
		setText('val-il', money(Math.abs(ledgerILTotal)));
		setText('val-gas', '0');
		setText('val-net-pnl', signedMoney(ledgerNetTotal));

        setText('metric-bots', canaryLive.build_mode ? '1 shadow + canary plan' : '1 shadow');
        setText('metric-pools', scanned || counts.pools || '-');
        setText('metric-chains', (num(baseCanary.broadcasts) > 0 && num(solanaCanary.broadcasts) > 0) ? 'Base + Solana' : 'Base');
        setText('metric-templates', selected || '-');
        setText('metric-events', `${counts.scores || '-'} / Base闭环 ${num(baseCanary.closed)}/${num(baseCanary.opened)} / Solana ${num(solanaCanary.broadcasts)}`);
        setText('metric-latency', health.last_mark_age_seconds !== undefined ? health.last_mark_age_seconds + 's' : '-');
        setText('health-pct', healthPct.toFixed(1) + '%');
        const healthBar = document.getElementById('health-bar');
        if (healthBar) healthBar.style.width = healthPct.toFixed(1) + '%';

        setHeaderStatus(data, healthPct);
        renderStrategyCards(latestAudit, marks, health, live);
        renderLiveReadiness(data, live, health, baseCanary);
        renderScanner(decisions, data.pools || []);
        renderPositions(marks);
        renderExitPreflights(data.exit_preflights || []);
        renderLatestCanary(canaryRounds, canarySummary, baseCanary);
        renderCanaryRounds(canaryRounds);
        renderAudit(data);
        renderExecution(data);
        renderLogs(data, live, baseCanary, solanaCanary);
        updateCharts(data, marks, markSeries, ledgerSeries, ledgerSummary);
    }

    function setHeaderStatus(data, healthPct) {
        const env = document.querySelector('.env-badge');
        if (env) {
            const canary = data.canary_readiness || {};
            const canaryLabel = canary.build_mode
                ? (canary.ready ? 'canary ready' : 'canary gated')
                : 'canary unavailable';
            setBadgeText(env, 'green-dot', (data.mode || 'shadow') + ' / ' + canaryLabel);
        }
        const health = document.querySelector('.health-badge');
        if (health) setBadgeText(health, 'green-dot-breath', healthPct >= 90 ? '系统健康' : '需要关注');
        const alarm = document.querySelector('.alarm-count');
        if (alarm) alarm.textContent = String((data.recent_issues || []).length || 0);
    }

    function renderStrategyCards(audit, marks, health, live) {
        const cards = document.querySelectorAll('.strategy-mode-chip .chip-number');
        if (cards[0]) setChipNumber(cards[0], String(num(audit.scanned)), 'scan');
        if (cards[1]) setChipNumber(cards[1], String(marks.length), 'marks');
        if (cards[2]) setChipNumber(cards[2], String(live.ready ? 1 : 0), live.canary ? 'canary' : 'live');
        if (cards[3]) setChipNumber(cards[3], String(num(audit.pipeline_ok)), live.ready ? 'ready' : 'ok');

        setText('decision-risk-score', `chain ${num(health.recent_chain_failures)} / pipeline ${num(health.recent_pipeline_failures)}`);
        setText('active-positions-count', String(marks.length));
        setText('active-positions-val', compactMoney(sum(marks, 'valuation_usd')));
    }

    function renderLiveReadiness(data, live, health, baseCanary) {
        const blockers = Array.isArray(live.blockers) ? live.blockers : [];
        const blockerText = blockers.length ? blockers.slice(0, 3).join(' | ') : '无';
        const txs = data.transactions || [];
        const lastTx = txs[0] || {};
        const allowedChains = Array.isArray(live.allowed_chains) && live.allowed_chains.length ? live.allowed_chains.join(', ') : '-';
        const wallet = live.wallet_address || '未配置';
        const backend = live.execution_backend || 'shadow';
        const readinessTarget = live.canary ? 'canary' : 'live';
        const backendSummary = live.execution_configured ? `${backend} / configured` : `${backend} / config missing`;
        const backendStatus = live.execution_backend_wired ? (live.ready ? '可执行' : '已接线待放行') : '执行器未接线';
        const whitelistStatus = num(live.allowed_pools_count) > 0 ? '白名单已加载' : '白名单为空';
        const poolChecks = Array.isArray(live.allowed_pool_checks) ? live.allowed_pool_checks : [];
        const poolCheck = poolChecks[0] || {};
        const poolStatus = poolCheck.pool_id
            ? `${poolCheck.pair_ok ? 'WETH/USDC 已链上确认' : '池子不匹配'} / fee ${poolCheck.fee || '-'}`
            : whitelistStatus;
        const rpcStatus = live.rpc_primary_configured ? 'RPC 已配置' : 'RPC 缺失';
        const okxStatus = backend === 'okx-onchain'
            ? ((live.okx_api_configured && live.okx_project_configured) ? 'OKX 凭据已配置' : 'OKX 凭据缺失')
            : '未使用 OKX';
        const walletStatus = live.wallet_passphrase_set
            ? ((live.keystore_present) ? 'Keystore + passphrase 已配置' : 'passphrase 已配 / keystore 缺失')
            : 'wallet passphrase 缺失';
        const npmStatus = live.npm_base_configured ? 'NPM 地址已配置' : 'NPM 地址缺失';
        const sizingStatus = live.sizing_path_ready ? 'sizing 已实现' : 'sizing 未实现';
        const balances = live.wallet_balances || {};
        const allowanceStatus = balances.error
            ? ''
            : ` / allowance USDC ${fmtBalance(balances.usdc_allowance)} WETH ${fmtBalance(balances.weth_allowance)}`;
        const balanceStatus = balances.error
            ? `余额读取失败: ${balances.error}`
            : `ETH ${fmtBalance(balances.eth)} / USDC ${fmtBalance(balances.usdc)} / WETH ${fmtBalance(balances.weth)}${allowanceStatus}`;

        setText('decision-exposure', `$${money(live.max_order_usd)} / $${money(live.daily_loss_limit_usd)}`);
        setText('decision-kill-switch', live.kill_switch ? '已触发 / 拒绝新单' : (live.live_enabled ? '未触发 / 等待全量通过' : 'live 未启用'));
        const activeBase = baseCanary.active_token_id
            ? `active NFT #${baseCanary.active_token_id} ${baseCanary.active_status || 'open'} ${num(baseCanary.active_hold_minutes)}m pnl ${signedMoney(baseCanary.active_net_pnl_usd)} / fee ${signedMoney(baseCanary.active_fee_usd)} / il ${signedMoney(baseCanary.active_il_usd)}`
            : '';
        const baseCycle = num(baseCanary.broadcasts)
            ? `Base ${num(baseCanary.closed)}/${num(baseCanary.opened)} 已闭环 / ${activeBase || `latest NFT #${baseCanary.last_token_id || '-'} ${baseCanary.last_status || 'unknown'} ${num(baseCanary.last_hold_minutes)}m pnl ${signedMoney(baseCanary.last_net_pnl_usd)} / fee ${signedMoney(baseCanary.last_fee_usd)} / il ${signedMoney(baseCanary.last_il_usd)}`}`
            : 'Base canary 尚未广播';
        setText('decision-canary', live.canary ? `已配置 canary / ${baseCycle}` : '未配置 canary');
        setText('decision-live-gate', live.ready ? `YES / ${readinessTarget} 配置已就绪` : `NO / ${readinessTarget} 仍为 fail-closed`);
        setText('decision-live-blockers', blockerText);

        setText('execution-backend', backendSummary);
        setText('execution-backend-status', backendStatus);
        setText('execution-wallet', wallet);
        setText('execution-wallet-status', wallet === '未配置' ? '缺失' : balanceStatus);
        setText('execution-whitelist', `${allowedChains} / ${num(live.allowed_pools_count)} pools`);
        setText('execution-whitelist-status', poolStatus);
        const lastBaseTx = baseCanary.last_tx_hash || lastTx.tx_hash || '';
        setText('execution-last-tx', lastBaseTx ? short(lastBaseTx) : (live.canary ? 'canary not started' : 'shadow only'));
        setText('execution-last-tx-status', lastBaseTx ? `${baseCanary.last_status || lastTx.status || 'recorded'} / closed ${num(baseCanary.closed)}/${num(baseCanary.opened)} / pnl ${signedMoney(baseCanary.last_net_pnl_usd)}` : `${rpcStatus} | ${okxStatus}`);
        setText('execution-blockers', `${blockerText} | ${balanceStatus} | ${rpcStatus} | ${okxStatus} | ${walletStatus} | ${npmStatus} | ${sizingStatus}`);
    }

    function renderScanner(decisions, pools) {
        const tbody = document.getElementById('alpha-scanner-tbody');
        if (!tbody) return;
        const rows = decisions.slice().sort((a, b) => num(b.score_total) - num(a.score_total)).slice(0, 12);
        const decisionRows = rows.map((row, idx) => buildScannerDecisionRow(row, idx));
        const solanaRows = (pools || []).filter(pool => num(pool.chain) === 2).slice(0, 6).map((pool, idx) => buildScannerSolanaRow(pool, idx));
        tbody.replaceChildren(...decisionRows, ...solanaRows);
    }

    function renderPositions(marks) {
        const tbody = document.getElementById('lp-positions-tbody');
        if (!tbody) return;
        tbody.replaceChildren(...marks.map((pos, idx) => buildPositionRow(pos, idx)));
    }

    function renderExitPreflights(preflights) {
        const list = document.getElementById('exit-preflight-list');
        if (!list) return;
        if (!preflights.length) {
            const empty = document.createElement('div');
            empty.className = 'exit-preflight-empty';
            empty.textContent = '暂无真实 NFT 退出预估。等待 position mark 写入 token_id 与 onchain_value。';
            list.replaceChildren(empty);
            return;
        }
        list.replaceChildren(...preflights.map(buildExitPreflightCard));
    }

    function renderAudit(data) {
        const list = document.getElementById('audit-events-list');
        if (!list) return;
        const issues = data.recent_issues || [];
        const quality = data.strategy_quality || [];
        const items = issues.length ? issues.map(i => ({
            type: 'warning',
            title: i.stage || 'issue',
            desc: `${short(i.pool_id)} ${i.reason || ''}`,
            time: timeText(i.tick_time)
        })) : quality.map(q => ({
            type: q.segment === 'passed_pipeline' ? 'success' : 'warning',
            title: q.segment,
            desc: `${q.count} pools, bottleneck ${q.bottleneck}, avg ${num(q.avg_total).toFixed(1)}`,
            time: 'latest'
        }));
        list.replaceChildren(...items.slice(0, 8).map(buildAuditEventCard));
    }

    function renderExecution(data) {
        const list = document.getElementById('execution-flow-list');
        if (!list) return;
        const canaryEvents = data.canary_events || [];
        const actions = data.exit_actions || [];
        const txs = data.transactions || [];
        const flows = [
            ...canaryEvents.map(e => ({
                time: timeText(e.created_at),
                module: e.command || 'canary',
                type: e.status || e.stage || '-',
                chain: (e.chain || 'base'),
                hash: e.tx_hash || '',
                desc: formatCanaryEventDesc(e),
                source: 'canary'
            })),
            ...actions.map(a => ({time: timeText(a.decision_time), module: 'exit', type: a.action, chain: 'Base', hash: a.tx_hash || '', desc: a.reason || 'shadow exit action'})),
            ...txs.map(t => ({time: timeText(Math.floor(num(t.created_at) / 1000)), module: 'transaction', type: t.status, chain: t.chain, hash: t.tx_hash || '', desc: t.status || 'transaction'}))
        ].slice(0, 20);
        const normalizedFlows = flows.length ? flows : [{time: 'latest', module: 'shadow', type: 'no live tx', chain: 'Base', hash: '', desc: '当前仍是 shadow 观测，没有真实链上执行'}];
        list.replaceChildren(...normalizedFlows.map(buildExecutionFlowItem));
    }

    function renderLatestCanary(rounds, canarySummary, baseCanary) {
        const card = document.getElementById('latest-canary-card');
        if (!card) return;
        const round = rounds[0];
        if (!round) {
            const empty = document.createElement('div');
            empty.className = 'latest-canary-metric';
            const label = document.createElement('span');
            label.textContent = '状态';
            const value = document.createElement('strong');
            value.textContent = '暂无 Base live canary 记录';
            empty.append(label, value);
            card.replaceChildren(empty);
            return;
        }

        const top = document.createElement('div');
        top.className = 'latest-canary-top';

        const title = document.createElement('div');
        title.className = 'latest-canary-title';
        const strong = document.createElement('strong');
        strong.textContent = `NFT #${round.token_id || '-'}`;
        const sub = document.createElement('div');
        sub.className = 'latest-canary-sub';
        sub.textContent = `${short(round.position_id)} · ${timeText(round.opened_at)}${round.closed_at ? ` -> ${timeText(round.closed_at)}` : ''}`;
        title.append(strong, sub);

        const status = document.createElement('span');
        status.className = String(round.status || '').toLowerCase() === 'closed' ? 'badge-success-glow' : 'green-badge';
        status.textContent = String(round.status || 'unknown');
        top.append(title, status);

        const summaryGrid = document.createElement('div');
        summaryGrid.className = 'latest-canary-grid';
        summaryGrid.append(
            buildLatestCanaryMetric('ETH/USD', `$${money(canarySummary.eth_price_usd)}`),
            buildLatestCanaryMetric('24h rounds', `${num(canarySummary.rounds_24h)} / ${num(canarySummary.closed_24h)} closed`),
            buildLatestCanaryMetric('24h Net(after gas)', signedMoney(canarySummary.total_net_after_gas_usd_24h)),
            buildLatestCanaryMetric('24h Gas', `${num(canarySummary.total_gas_used_24h)} / ${fmtGasEth(canarySummary.total_gas_eth_24h)} ETH / $${money(canarySummary.total_gas_usd_24h)}`),
            buildLatestCanaryMetric('7d rounds', `${num(canarySummary.rounds_7d)} / ${num(canarySummary.closed_7d)} closed`),
            buildLatestCanaryMetric('7d Net(after gas)', signedMoney(canarySummary.total_net_after_gas_usd_7d)),
            buildLatestCanaryMetric('7d Gas', `${num(canarySummary.total_gas_used_7d)} / ${fmtGasEth(canarySummary.total_gas_eth_7d)} ETH / $${money(canarySummary.total_gas_usd_7d)}`),
            buildLatestCanaryMetric('All rounds', `${num(canarySummary.rounds_all)} / ${num(canarySummary.closed_all)} closed`),
            buildLatestCanaryMetric('All Net(after gas)', signedMoney(canarySummary.total_net_after_gas_usd_all)),
            buildLatestCanaryMetric('All Gas', `${num(canarySummary.total_gas_used_all)} / ${fmtGasEth(canarySummary.total_gas_eth_all)} ETH / $${money(canarySummary.total_gas_usd_all)}`)
        );

        const grid = document.createElement('div');
        grid.className = 'latest-canary-grid';
        grid.append(
            buildLatestCanaryMetric('投入', `$${money(round.amount_usd)}`),
            buildLatestCanaryMetric(String(round.status || '').toLowerCase() === 'closed' ? '退出' : '当前估值', `$${money(round.status === 'closed' ? round.exit_usd : round.valuation_usd)}`),
            buildLatestCanaryMetric('净值变化', signedMoney(round.value_delta_usd)),
            buildLatestCanaryMetric('Net(after gas)', signedMoney(round.net_after_gas_usd)),
            buildLatestCanaryMetric('Fee', signedMoney(round.fee_usd)),
            buildLatestCanaryMetric('IL', signedMoney(round.il_usd)),
            buildLatestCanaryMetric('Hold', `${num(round.hold_minutes)}m`),
            buildLatestCanaryMetric('Gas Real', `${num(round.total_gas_used)} / ${fmtGasEth(round.total_gas_eth)} ETH / $${money(round.total_gas_usd)}`)
        );

        const links = document.createElement('div');
        links.className = 'latest-canary-links';
        if (round.pool_id) {
            const poolWrap = document.createElement('span');
            poolWrap.appendChild(poolLinkNode(round.pool_id));
            links.appendChild(poolWrap);
        }
        if (round.mint_tx_hash) {
            const mint = document.createElement('span');
            mint.append(document.createTextNode('mint '), txLinkNode(round.mint_tx_hash));
            links.appendChild(mint);
        }
        if (round.decrease_tx_hash) {
            const decrease = document.createElement('span');
            decrease.append(document.createTextNode('decrease '), txLinkNode(round.decrease_tx_hash));
            links.appendChild(decrease);
        }
        if (round.collect_tx_hash) {
            const collect = document.createElement('span');
            collect.append(document.createTextNode('collect '), txLinkNode(round.collect_tx_hash));
            links.appendChild(collect);
        } else if (baseCanary.last_tx_hash && !round.last_tx_hash) {
            const last = document.createElement('span');
            last.append(document.createTextNode('last '), txLinkNode(baseCanary.last_tx_hash));
            links.appendChild(last);
        }

        card.replaceChildren(top, summaryGrid, grid, links);
    }

    function renderCanaryRounds(rounds) {
        const tbody = document.getElementById('canary-rounds-tbody');
        if (!tbody) return;
        if (!rounds.length) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 11;
            td.className = 'mono';
            td.textContent = '暂无 Base canary rounds。';
            tr.appendChild(td);
            tbody.replaceChildren(tr);
            return;
        }
        tbody.replaceChildren(...rounds.map(buildCanaryRoundRow));
    }

    function renderLogs(data, live, baseCanary, solanaCanary) {
        const box = document.getElementById('console-log-box');
        if (!box) return;
        const audit = (data.strategy_audit || [])[0] || {};
        const health = data.health || {};
        const logs = [
            ['info', 'runtime', `commit ${data.commit || '-'} / mode ${data.mode || 'shadow'}`],
            ['info', 'scanner', `scanned ${num(audit.scanned)}, selected ${num(audit.selected)}, pipeline ok ${num(audit.pipeline_ok)}`],
            ['info', 'mark', `last mark age ${health.last_mark_age_seconds || '-'}s, source ${health.last_mark_source || '-'}`],
            ['info', 'live', `ready ${live.ready ? 'yes' : 'no'}, blockers ${(live.blockers || []).length}, canary ${live.canary ? 'on' : 'off'}`],
            [num(baseCanary.broadcasts) ? 'success' : 'info', 'base', num(baseCanary.broadcasts) ? `closed ${num(baseCanary.closed)}/${num(baseCanary.opened)}, tx ${num(baseCanary.tx_broadcasts)}, ${baseCanary.active_token_id ? `active NFT ${baseCanary.active_token_id} hold ${num(baseCanary.active_hold_minutes)}m pnl ${signedMoney(baseCanary.active_net_pnl_usd)} fee ${signedMoney(baseCanary.active_fee_usd)} il ${signedMoney(baseCanary.active_il_usd)}` : `last NFT ${baseCanary.last_token_id || '-'} ${baseCanary.last_status || 'unknown'} hold ${num(baseCanary.last_hold_minutes)}m pnl ${signedMoney(baseCanary.last_net_pnl_usd)} fee ${signedMoney(baseCanary.last_fee_usd)} il ${signedMoney(baseCanary.last_il_usd)}`}` : 'no base canary broadcast yet'],
            [num(solanaCanary.broadcasts) ? 'success' : 'info', 'solana', num(solanaCanary.broadcasts) ? `swaps ${num(solanaCanary.broadcasts)}, wallet SOL ${formatTokenAmount(solanaCanary.sol_balance_raw || '0', 'So11111111111111111111111111111111111111112')} / USDC ${formatTokenAmount(solanaCanary.usdc_balance_raw || '0', 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v')}` : 'no solana canary broadcast yet'],
            [num(health.recent_chain_failures) ? 'warn' : 'success', 'chain', `chain failures / 30m: ${num(health.recent_chain_failures)}`],
            [num(health.recent_pipeline_failures) ? 'warn' : 'success', 'pipeline', `pipeline failures / 30m: ${num(health.recent_pipeline_failures)}`]
        ];
        box.replaceChildren(...logs.map(([level, module, msg]) => buildLogLine({
            time: new Date().toLocaleTimeString(),
            level,
            module,
            msg
        })));
    }

    function updateCharts(data, marks, markSeries, ledgerSeries, ledgerSummary) {
        const tiers = groupSum(marks, 'tier', 'valuation_usd');
        charts.tier && charts.tier.setOption(getPieOption('资金分布 (Tier)', Object.entries(tiers).map(([name, value]) => ({ name: name || 'unknown', value }))));
        charts.chain && charts.chain.setOption(getPieOption('资金分布 (链)', [{ name: 'Base', value: sum(marks, 'valuation_usd') || 1 }]));
        const summaryByKind = (ledgerSummary || []).reduce((out, item) => {
            out[item.kind] = num(item.amount);
            return out;
        }, {});

        const pnlSeries = ledgerSeries.length ? ledgerSeries : markSeries;
        const pnlValues = pnlSeries.map(p => Number(num(p.net_pnl_usd).toFixed(4)));
        const labels = pnlSeries.map(p => new Date(num((p.block_time || p.mark_time)) * 1000).toLocaleTimeString());
        charts.cumulativePnl && charts.cumulativePnl.setOption({ xAxis: { data: labels }, series: [{ data: pnlValues }] });
        charts.revenueBreakdown && charts.revenueBreakdown.setOption({
            xAxis: { data: ['24h ledger'] },
            series: [
                { name: 'Fee', type: 'bar', stack: 'total', itemStyle: { color: '#10b981' }, data: [summaryByKind.fee || 0] },
                { name: 'IL', type: 'bar', stack: 'total', itemStyle: { color: '#ef4444' }, data: [summaryByKind.il || 0] }
            ]
        });

        const quality = data.strategy_quality || [];
        charts.strategyRadar && charts.strategyRadar.setOption({ series: [{ data: [{ value: radarFromQuality(quality), name: '策略质量' }] }] });
        const health = data.health || {};
        charts.auditDistribution && charts.auditDistribution.setOption({ series: [{ data: [
            { value: Math.max(1, 100 - num(health.recent_chain_failures) - num(health.recent_pipeline_failures)), itemStyle: { color: '#10b981' } },
            { value: num(health.recent_chain_failures), itemStyle: { color: '#fbbf24' } },
            { value: num(health.recent_pipeline_failures), itemStyle: { color: '#ef4444' } }
        ] }] });
    }

    function initCharts() {
        const darkTheme = { textStyle: { color: '#8c9ba5', fontFamily: 'Inter, sans-serif' } };
        const ids = {
            tier: 'chart-tier-distribution', chain: 'chart-chain-distribution', cumulativePnl: 'chart-cumulative-pnl', revenueBreakdown: 'chart-revenue-breakdown', strategyRadar: 'chart-strategy-radar', auditDistribution: 'chart-audit-distribution', rebalanceTimeline: 'chart-rebalance-timeline', strategyComparison: 'chart-strategy-comparison', knobCpu: 'knob-cpu', knobMem: 'knob-mem', knobDisk: 'knob-disk'
        };
        Object.entries(ids).forEach(([key, id]) => { const el = document.getElementById(id); if (el) charts[key] = echarts.init(el, null, darkTheme); });
        charts.tier && charts.tier.setOption(getPieOption('资金分布 (Tier)', []));
        charts.chain && charts.chain.setOption(getPieOption('资金分布 (链)', []));
        charts.cumulativePnl && charts.cumulativePnl.setOption(lineOption('Net PnL'));
        charts.revenueBreakdown && charts.revenueBreakdown.setOption(barOption());
        charts.strategyRadar && charts.strategyRadar.setOption(radarOption());
        charts.auditDistribution && charts.auditDistribution.setOption(getPieOption('风险分布', []));
        charts.rebalanceTimeline && charts.rebalanceTimeline.setOption(barOption());
        charts.strategyComparison && charts.strategyComparison.setOption(lineOption('Strategy'));
        charts.knobCpu && charts.knobCpu.setOption(getKnobOption(0, '#10b981'));
        charts.knobMem && charts.knobMem.setOption(getKnobOption(0, '#3b82f6'));
        charts.knobDisk && charts.knobDisk.setOption(getKnobOption(0, '#a855f7'));
    }

    function getPieOption(name, data) { return { tooltip: { trigger: 'item' }, series: [{ name, type: 'pie', radius: ['45%', '75%'], label: { show: false }, data }] }; }
    function lineOption(name) { return { tooltip: { trigger: 'axis' }, grid: { top: '15%', left: '3%', right: '3%', bottom: '5%', containLabel: true }, xAxis: { type: 'category', data: [] }, yAxis: { type: 'value' }, series: [{ name, type: 'line', smooth: true, data: [], itemStyle: { color: '#10b981' }, areaStyle: {} }] }; }
    function barOption() { return { tooltip: { trigger: 'axis' }, legend: { textStyle: { color: '#8c9ba5' } }, grid: { top: '18%', left: '3%', right: '3%', bottom: '5%', containLabel: true }, xAxis: { type: 'category', data: [] }, yAxis: { type: 'value' }, series: [] }; }
    function radarOption() { return { radar: { indicator: [{ name: 'Pool选择', max: 100 }, { name: '波动率', max: 100 }, { name: 'IL风险', max: 100 }, { name: '深度', max: 100 }, { name: '安全', max: 100 }, { name: 'APR', max: 100 }], axisName: { color: '#8c9ba5', fontSize: 10 } }, series: [{ type: 'radar', data: [{ value: [0, 0, 0, 0, 0, 0], name: '策略质量', areaStyle: { color: 'rgba(0,240,255,0.15)' } }] }] }; }
    function getKnobOption(val, color) { return { series: [{ type: 'gauge', startAngle: 90, endAngle: -270, pointer: { show: false }, progress: { show: true, roundCap: true, itemStyle: { color } }, axisLine: { lineStyle: { width: 4, color: [[1, 'rgba(255,255,255,0.02)']] } }, splitLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false }, data: [{ value: val }], detail: { show: false } }] }; }

    function bindReadOnlyInteractions() {
        const circuit = document.getElementById('btn-circuit-breaker');
        if (circuit) circuit.addEventListener('click', () => alert('只读面板：当前不允许从前端修改熔断状态。'));
        const range = document.getElementById('btn-range-adjust');
        if (range) range.addEventListener('click', () => alert('只读面板：当前不允许从前端修改 Range 策略。'));
    }

    function setBadgeText(el, dotClass, text) {
        if (!el) return;
        const dot = document.createElement('span');
        dot.className = `dot ${dotClass}`;
        el.replaceChildren(dot, document.createTextNode(text));
    }
    function setChipNumber(el, value, badgeText) {
        if (!el) return;
        const badge = document.createElement('span');
        badge.className = 'plus-badge';
        badge.textContent = badgeText;
        el.replaceChildren(document.createTextNode(value), badge);
    }
    function buildLogLine(log) {
        const row = document.createElement('div');
        row.className = 'log-line';

        const time = document.createElement('span');
        time.className = 'log-time';
        time.textContent = `[${log.time}]`;

        const level = document.createElement('span');
        level.className = `log-level ${String(log.level || '').toLowerCase()}`;
        level.textContent = String(log.level || '').toUpperCase();

        const module = document.createElement('span');
        module.className = 'log-module';
        module.textContent = `${log.module}:`;

        const msg = document.createElement('span');
        msg.className = 'log-msg';
        msg.textContent = String(log.msg || '');

        row.append(time, level, module, msg);
        return row;
    }
    function buildAuditEventCard(ev) {
        const card = document.createElement('div');
        card.className = 'audit-event-card';

        const top = document.createElement('div');
        top.className = 'audit-event-top';

        const time = document.createElement('span');
        time.className = 'audit-time';
        time.textContent = String(ev.time || '-');

        const type = document.createElement('span');
        type.className = `audit-type ${String(ev.type || '')}`;
        type.textContent = String(ev.type || '-');

        top.append(time, type);

        const desc = document.createElement('div');
        desc.className = 'audit-desc';

        const strong = document.createElement('strong');
        strong.textContent = String(ev.title || '-');

        desc.append(strong, document.createTextNode(`: ${String(ev.desc || '-')}`));
        card.append(top, desc);
        return card;
    }
    function buildExecutionFlowItem(fl) {
        const item = document.createElement('div');
        item.className = 'flow-item';

        const left = document.createElement('div');
        left.className = 'flow-left';

        const header = document.createElement('div');
        header.className = 'flow-header';

        const time = document.createElement('span');
        time.className = 'flow-time';
        time.textContent = String(fl.time || '-');

        const module = document.createElement('span');
        module.className = 'flow-module';
        module.textContent = String(fl.module || '-');

        const tag = document.createElement('span');
        tag.className = 'flow-tag';
        tag.textContent = String(fl.type || '-');

        header.append(time, module, tag);

        const desc = document.createElement('div');
        desc.className = 'flow-desc';
        desc.textContent = String(fl.desc || '-');

        left.append(header, desc);

        const right = document.createElement('div');
        right.className = 'flow-right';
        if (fl.hash) {
            const link = document.createElement('a');
            const normalized = String(fl.chain || '').toLowerCase();
            link.target = '_blank';
            link.rel = 'noreferrer';
            link.className = 'flow-tx';
            link.href = `${normalized === 'solana' ? 'https://solscan.io/tx/' : 'https://basescan.org/tx/'}${String(fl.hash)}`;
            link.textContent = short(fl.hash);
            right.appendChild(link);
        } else {
            const source = document.createElement('span');
            source.className = 'flow-tx';
            source.textContent = String(fl.source || 'shadow');
            right.appendChild(source);
        }
        const badge = document.createElement('span');
        badge.className = 'badge-success-glow';
        badge.textContent = 'DB';
        right.appendChild(badge);

        item.append(left, right);
        return item;
    }
    function buildScannerDecisionRow(row, idx) {
        const tr = document.createElement('tr');
        tr.append(
            buildCellWithSpan(String(idx + 1), 'mono'),
            buildScannerPoolCell(row.pool_id, 1),
            buildBadgeCell('Base', 'badge-chain base'),
            buildBadgeCell(String(row.protocol || 'AMM'), 'badge-dex'),
            buildValueCell(num(row.score_total).toFixed(1), 'green-text mono', true),
            buildCellText(row.intent_open ? '通过' : '跳过', 'mono'),
            buildCellText(row.chain_stage || '-', 'mono font-12'),
            buildCellText(row.pipeline_stage || '-', 'mono font-12'),
            buildValueCell(num(row.score_total).toFixed(1), 'green-text mono', true),
            buildBadgeCell(String(row.final_action || 'skip'), row.selected ? 'badge-success-glow' : 'green-badge')
        );
        return tr;
    }
    function buildScannerSolanaRow(pool, idx) {
        const tr = document.createElement('tr');
        const tvlCell = document.createElement('td');
        tvlCell.className = 'green-text mono';
        const tvlStrong = document.createElement('strong');
        tvlStrong.textContent = `$${compactMoney(pool.tvl_usd)}`;
        const tvlMini = document.createElement('div');
        tvlMini.className = 'muted-mini';
        tvlMini.textContent = 'TVL';
        tvlCell.append(tvlStrong, tvlMini);

        const volCell = document.createElement('td');
        volCell.className = 'mono';
        volCell.append(document.createTextNode(`$${compactMoney(pool.vol24h_usd)}`));
        const volMini = document.createElement('div');
        volMini.className = 'muted-mini';
        volMini.textContent = '24h vol';
        volCell.appendChild(volMini);

        tr.append(
            buildCellWithSpan(`S${idx + 1}`, 'mono'),
            buildScannerPoolCell(pool.pool_id, pool.chain),
            buildBadgeCell('Solana', 'badge-chain'),
            buildBadgeCell(String(pool.protocol || 'AMM'), 'badge-dex'),
            tvlCell,
            volCell,
            buildCellText(pool.risk_reason || '-', 'mono font-12'),
            buildCellText(pool.tier || '-', 'mono font-12'),
            buildValueCell(pool.risk_eligible ? 'OK' : '-', 'green-text mono', true),
            buildBadgeCell(pool.risk_eligible ? 'eligible' : 'observe', pool.risk_eligible ? 'badge-success-glow' : 'green-badge')
        );
        return tr;
    }
    function buildPositionRow(pos, idx) {
        const amount = Math.max(num(pos.amount_usd), 1);
        const ilPct = Math.abs(num(pos.il_usd)) / amount * 100;
        const feeCover = Math.abs(num(pos.il_usd)) > 0.000001 ? num(pos.fee_usd) / Math.abs(num(pos.il_usd)) : 0;

        const tr = document.createElement('tr');
        const poolCell = document.createElement('td');
        const strong = document.createElement('strong');
        strong.appendChild(poolLinkNode(pos.pool_id));
        const nft = document.createElement('div');
        nft.className = 'muted-mini';
        nft.textContent = `NFT #${pos.token_id || '-'}`;
        const pid = document.createElement('div');
        pid.className = 'muted-mini';
        pid.textContent = short(pos.position_id);
        poolCell.append(strong, nft, pid);

        const feeCell = document.createElement('td');
        feeCell.className = 'green-text mono';
        const feeStrong = document.createElement('strong');
        feeStrong.textContent = signedMoney(pos.fee_usd);
        const feeMini = document.createElement('div');
        feeMini.className = 'muted-mini';
        feeMini.textContent = `cover ${feeCover ? feeCover.toFixed(2) + 'x' : '-'}`;
        feeCell.append(feeStrong, feeMini);

        const ilCell = document.createElement('td');
        ilCell.className = 'red-text mono';
        ilCell.append(document.createTextNode(signedMoney(pos.il_usd)));
        const ilMini = document.createElement('div');
        ilMini.className = 'muted-mini';
        ilMini.textContent = `${ilPct.toFixed(4)}%`;
        ilCell.appendChild(ilMini);

        const actionCell = document.createElement('td');
        const action = document.createElement('a');
        action.className = 'action-btn-mini';
        action.target = '_blank';
        action.rel = 'noreferrer';
        action.href = dexscreenerURL(pos.pool_id);
        action.textContent = '查看池子';
        actionCell.appendChild(action);

        tr.append(
            buildCellWithSpan(String(idx + 1), 'mono'),
            poolCell,
            buildBadgeCell('Base', 'badge-chain base'),
            buildBadgeCell(String(pos.source || 'datasource'), 'badge-dex'),
            buildValueCell(`$${money(pos.valuation_usd)}`, 'mono', true),
            feeCell,
            ilCell,
            buildCellText(signedMoney(pos.net_pnl_usd), 'mono'),
            actionCell
        );
        return tr;
    }
    function buildCanaryRoundRow(round) {
        const tr = document.createElement('tr');

        const timeCell = document.createElement('td');
        const timeStrong = document.createElement('strong');
        timeStrong.textContent = timeText(round.opened_at);
        const timeMini = document.createElement('div');
        timeMini.className = 'muted-mini';
        timeMini.textContent = round.closed_at ? `closed ${timeText(round.closed_at)}` : 'still open';
        timeCell.append(timeStrong, timeMini);

        const nftCell = document.createElement('td');
        const nftStrong = document.createElement('strong');
        nftStrong.textContent = `NFT #${round.token_id || '-'}`;
        const poolMini = document.createElement('div');
        poolMini.className = 'muted-mini';
        poolMini.appendChild(poolLinkNode(round.pool_id));
        nftCell.append(nftStrong, poolMini);

        const statusClass = String(round.status || '').toLowerCase() === 'closed' ? 'badge-success-glow' : 'green-badge';
        const shownValue = String(round.status || '').toLowerCase() === 'closed' ? round.exit_usd : round.valuation_usd;

        const txCell = document.createElement('td');
        if (round.last_tx_hash) {
            txCell.appendChild(txLinkNode(round.last_tx_hash));
        } else {
            txCell.textContent = '-';
        }
        const txMini = document.createElement('div');
        txMini.className = 'muted-mini';
        txMini.textContent = `${num(round.hold_minutes)}m / gross ${signedMoney(round.net_pnl_usd)}`;
        txCell.appendChild(txMini);

        tr.append(
            timeCell,
            nftCell,
            buildBadgeCell(String(round.status || '-'), statusClass),
            buildCellText(`$${money(round.amount_usd)}`, 'mono'),
            buildCellText(`$${money(shownValue)}`, 'mono'),
            buildCellText(`${num(round.total_gas_used) || (num(round.mint_gas_estimate) + num(round.exit_gas_estimate) || 0)}${num(round.total_gas_used) ? ` / ${fmtGasEth(round.total_gas_eth)} ETH / $${money(round.total_gas_usd)}` : ' est'}`, 'mono'),
            buildCellText(signedMoney(round.value_delta_usd), 'mono'),
            buildCellText(signedMoney(round.fee_usd), 'mono green-text'),
            buildCellText(signedMoney(round.il_usd), 'mono red-text'),
            buildCellText(signedMoney(round.net_after_gas_usd), 'mono'),
            txCell
        );
        return tr;
    }
    function buildExitPreflightCard(item) {
        const card = document.createElement('div');
        card.className = 'exit-preflight-card';

        const top = document.createElement('div');
        top.className = 'exit-preflight-top';
        const left = document.createElement('div');
        const title = document.createElement('div');
        title.className = 'exit-preflight-title';
        title.textContent = `NFT #${item.token_id || '-'}`;
        const pool = document.createElement('div');
        pool.className = 'muted-mini';
        pool.appendChild(poolLinkNode(item.pool_id));
        left.append(title, pool);
        const badge = document.createElement('span');
        badge.className = item.broadcast_enabled ? 'badge-danger' : 'badge-success-glow';
        badge.textContent = item.broadcast_enabled ? 'broadcast enabled' : 'broadcast=false';
        top.append(left, badge);

        const metrics = document.createElement('div');
        metrics.className = 'exit-preflight-metrics';
        metrics.append(
            buildMetricPair('可退出总值', `$${money(item.total_usd)}`),
            buildMetricPair('本金估值', `$${money(item.principal_usd)}`),
            buildMetricPair('未领取手续费', signedMoney(item.fee_usd), 'green-text'),
            buildMetricPair('IL', signedMoney(item.il_usd), 'red-text'),
            buildMetricPair('净 PnL', signedMoney(item.net_pnl_usd), num(item.net_pnl_usd) >= 0 ? 'green-text' : 'red-text'),
            buildMetricPair('Gas', `${item.decrease_gas || '-'} / ${item.collect_gas || '-'}`)
        );

        const footer = document.createElement('div');
        footer.className = 'exit-preflight-footer';
        const status = document.createElement('span');
        status.textContent = String(item.status || 'mark_estimate');
        const code = document.createElement('code');
        code.textContent = String(item.command || '');
        footer.append(status, code);

        const txs = document.createElement('div');
        txs.className = 'muted-mini';
        txs.append(
            document.createTextNode('decrease tx: '),
            txLinkNode(item.decrease_tx_hash),
            document.createTextNode(' / collect tx: '),
            txLinkNode(item.collect_tx_hash)
        );

        const nodes = [top, metrics, footer, txs];
        if (item.error_msg) {
            const err = document.createElement('div');
            err.className = 'muted-mini red-text';
            err.textContent = `error: ${item.error_msg}`;
            nodes.push(err);
        }
        const meta = document.createElement('div');
        meta.className = 'muted-mini';
        meta.textContent = `source: ${item.source || '-'} / updated ${timeText(item.updated_at)}`;
        nodes.push(meta);

        card.append(...nodes);
        return card;
    }
    function buildCellWithSpan(text, className) {
        const td = document.createElement('td');
        const span = document.createElement('span');
        span.className = className;
        span.textContent = text;
        td.appendChild(span);
        return td;
    }
    function buildCellText(text, className) {
        const td = document.createElement('td');
        if (className) td.className = className;
        td.textContent = String(text);
        return td;
    }
    function buildBadgeCell(text, className) {
        const td = document.createElement('td');
        const span = document.createElement('span');
        span.className = className;
        span.textContent = String(text);
        td.appendChild(span);
        return td;
    }
    function buildValueCell(text, className, strong) {
        const td = document.createElement('td');
        if (className) td.className = className;
        if (strong) {
            const node = document.createElement('strong');
            node.textContent = String(text);
            td.appendChild(node);
        } else {
            td.textContent = String(text);
        }
        return td;
    }
    function buildScannerPoolCell(poolId, chain) {
        const td = document.createElement('td');
        const strong = document.createElement('strong');
        strong.appendChild(poolLinkNode(poolId, chain));
        const mini = document.createElement('div');
        mini.className = 'muted-mini';
        mini.textContent = short(poolId);
        td.append(strong, mini);
        return td;
    }
    function buildMetricPair(label, value, valueClass) {
        const wrap = document.createElement('div');
        const span = document.createElement('span');
        span.textContent = String(label);
        const strong = document.createElement('strong');
        if (valueClass) strong.className = valueClass;
        strong.textContent = String(value);
        wrap.append(span, strong);
        return wrap;
    }
    function buildLatestCanaryMetric(label, value) {
        const wrap = document.createElement('div');
        wrap.className = 'latest-canary-metric';
        const span = document.createElement('span');
        span.textContent = String(label);
        const strong = document.createElement('strong');
        strong.textContent = String(value);
        wrap.append(span, strong);
        return wrap;
    }
    function appendLog(level, module, msg) {
        const box = document.getElementById('console-log-box');
        if (!box) return;
        box.appendChild(buildLogLine({ time: new Date().toLocaleTimeString(), level, module, msg }));
        box.scrollTop = box.scrollHeight;
    }
    function radarFromQuality(quality) { const pass = quality.find(q => q.segment === 'passed_pipeline') || {}; return [num(pass.count) * 20, num(pass.avg_volatility), 100 - Math.min(100, num(pass.avg_volatility)), num(pass.avg_tvl), num(pass.avg_security), num(pass.avg_fee_apr)].map(v => Math.max(0, Math.min(100, v || 0))); }
    function groupSum(rows, key, valueKey) { return rows.reduce((out, row) => { const k = row[key] || 'unknown'; out[k] = (out[k] || 0) + num(row[valueKey]); return out; }, {}); }
    function sum(rows, key) { return rows.reduce((total, row) => total + num(row[key]), 0); }
    function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
    function num(value) { const n = Number(value || 0); return Number.isFinite(n) ? n : 0; }
    function fmtBalance(value) { const n = num(value); return n ? n.toLocaleString(undefined, { maximumFractionDigits: 8 }) : '0'; }
    function money(value) { return Math.abs(num(value)).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
    function signedMoney(value) { const n = num(value); return (n >= 0 ? '+' : '-') + money(n); }
    function compactMoney(value) { const n = num(value); if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M'; if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(2) + 'K'; return n.toFixed(2); }
    function fmtGasEth(value) { const n = num(value); return n ? n.toFixed(6) : '0'; }
    function short(value) { const s = String(value || ''); return s.length > 18 ? s.slice(0, 8) + '...' + s.slice(-6) : s; }
    function timeText(unix) { return unix ? new Date(num(unix) * 1000).toLocaleTimeString() : '-'; }
    function dexscreenerURL(poolId, chain) { return `https://dexscreener.com/${num(chain) === 2 ? 'solana' : 'base'}/${encodeURIComponent(poolId || '')}`; }
    function geckoURL(poolId, chain) { return `https://www.geckoterminal.com/${num(chain) === 2 ? 'solana' : 'base'}/pools/${encodeURIComponent(poolId || '')}`; }
    function poolLinkNode(poolId, chain) {
        const frag = document.createDocumentFragment();
        const dex = document.createElement('a');
        dex.target = '_blank';
        dex.rel = 'noreferrer';
        dex.href = dexscreenerURL(poolId, chain);
        dex.textContent = short(poolId);
        const gt = document.createElement('a');
        gt.target = '_blank';
        gt.rel = 'noreferrer';
        gt.href = geckoURL(poolId, chain);
        gt.textContent = 'GT';
        frag.append(dex, document.createTextNode(' '), gt);
        return frag;
    }
    function txLinkNode(hash) {
        if (!hash) return document.createTextNode('-');
        const link = document.createElement('a');
        link.target = '_blank';
        link.rel = 'noreferrer';
        link.href = `https://basescan.org/tx/${String(hash)}`;
        link.textContent = short(hash);
        return link;
    }
    function chainTxLink(chain, hash) {
        const normalized = String(chain || '').toLowerCase();
        const host = normalized === 'solana' ? 'https://solscan.io/tx/' : 'https://basescan.org/tx/';
        return `<a target="_blank" rel="noreferrer" href="${host}${escapeHTML(hash)}" class="flow-tx">${short(hash)}</a>`;
    }
    function formatCanaryEventDesc(e) {
        const parts = [`${e.stage || '-'}: ${e.error_msg || e.message || ''}`];
        if (e.input_mint && e.output_mint && e.input_amount_raw && e.output_amount_raw) {
            parts.push(`${formatTokenAmount(e.input_amount_raw, e.input_mint)} -> ${formatTokenAmount(e.output_amount_raw, e.output_mint)}`);
        }
        if (e.chain === 'solana' && (e.sol_balance_raw || e.usdc_balance_raw)) {
            parts.push(`wallet SOL ${formatTokenAmount(e.sol_balance_raw || '0', 'So11111111111111111111111111111111111111112')} / USDC ${formatTokenAmount(e.usdc_balance_raw || '0', 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v')}`);
        }
        if (e.pool_id) parts.push(`pool ${short(e.pool_id)}`);
        if (e.position_id) parts.push(`pos ${short(e.position_id)}`);
        return parts.join(' / ');
    }
    function formatTokenAmount(raw, mint) {
        const decimals = tokenDecimals(mint);
        const symbol = tokenSymbol(mint);
        const value = num(raw) / Math.pow(10, decimals);
        return `${value.toFixed(decimals === 9 ? 6 : 4)} ${symbol}`;
    }
    function tokenDecimals(mint) {
        if (mint === 'So11111111111111111111111111111111111111112') return 9;
        if (mint === 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') return 6;
        return 6;
    }
    function tokenSymbol(mint) {
        if (mint === 'So11111111111111111111111111111111111111112') return 'SOL';
        if (mint === 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') return 'USDC';
        return short(mint);
    }
    function escapeHTML(value) { return String(value || '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c])); }
})();
