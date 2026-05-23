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
            env.innerHTML = '<span class="dot green-dot"></span>' + (data.mode || 'shadow') + ' / ' + canaryLabel;
        }
        const health = document.querySelector('.health-badge');
        if (health) health.innerHTML = '<span class="dot green-dot-breath"></span>' + (healthPct >= 90 ? '系统健康' : '需要关注');
        const alarm = document.querySelector('.alarm-count');
        if (alarm) alarm.textContent = String((data.recent_issues || []).length || 0);
    }

    function renderStrategyCards(audit, marks, health, live) {
        const cards = document.querySelectorAll('.strategy-mode-chip .chip-number');
        if (cards[0]) cards[0].innerHTML = `${num(audit.scanned)}<span class="plus-badge">scan</span>`;
        if (cards[1]) cards[1].innerHTML = `${marks.length}<span class="plus-badge">marks</span>`;
        if (cards[2]) cards[2].innerHTML = `${live.ready ? 1 : 0}<span class="plus-badge">${live.canary ? 'canary' : 'live'}</span>`;
        if (cards[3]) cards[3].innerHTML = `${num(audit.pipeline_ok)}<span class="plus-badge">${live.ready ? 'ready' : 'ok'}</span>`;

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
        const decisionHTML = rows.map((row, idx) => `
            <tr>
                <td><span class="mono">${idx + 1}</span></td>
                <td><strong>${poolLink(row.pool_id, 1)}</strong><div class="muted-mini">${short(row.pool_id)}</div></td>
                <td><span class="badge-chain base">Base</span></td>
                <td><span class="badge-dex">${escapeHTML(row.protocol || 'AMM')}</span></td>
                <td class="green-text mono"><strong>${num(row.score_total).toFixed(1)}</strong></td>
                <td class="mono">${row.intent_open ? '通过' : '跳过'}</td>
                <td><span class="mono font-12">${row.chain_stage || '-'}</span></td>
                <td><span class="mono font-12">${row.pipeline_stage || '-'}</span></td>
                <td class="green-text mono"><strong>${num(row.score_total).toFixed(1)}</strong></td>
                <td><span class="${row.selected ? 'badge-success-glow' : 'green-badge'}">${row.final_action || 'skip'}</span></td>
            </tr>`).join('');
        const solanaHTML = (pools || []).filter(pool => num(pool.chain) === 2).slice(0, 6).map((pool, idx) => `
            <tr>
                <td><span class="mono">S${idx + 1}</span></td>
                <td><strong>${poolLink(pool.pool_id, pool.chain)}</strong><div class="muted-mini">${short(pool.pool_id)}</div></td>
                <td><span class="badge-chain">Solana</span></td>
                <td><span class="badge-dex">${escapeHTML(pool.protocol || 'AMM')}</span></td>
                <td class="green-text mono"><strong>$${compactMoney(pool.tvl_usd)}</strong><div class="muted-mini">TVL</div></td>
                <td class="mono">$${compactMoney(pool.vol24h_usd)}<div class="muted-mini">24h vol</div></td>
                <td><span class="mono font-12">${escapeHTML(pool.risk_reason || '-')}</span></td>
                <td><span class="mono font-12">${escapeHTML(pool.tier || '-')}</span></td>
                <td class="green-text mono"><strong>${pool.risk_eligible ? 'OK' : '-'}</strong></td>
                <td><span class="${pool.risk_eligible ? 'badge-success-glow' : 'green-badge'}">${pool.risk_eligible ? 'eligible' : 'observe'}</span></td>
            </tr>`).join('');
        tbody.innerHTML = decisionHTML + solanaHTML;
    }

    function renderPositions(marks) {
        const tbody = document.getElementById('lp-positions-tbody');
        if (!tbody) return;
        tbody.innerHTML = marks.map((pos, idx) => {
            const amount = Math.max(num(pos.amount_usd), 1);
            const ilPct = Math.abs(num(pos.il_usd)) / amount * 100;
            const feeCover = Math.abs(num(pos.il_usd)) > 0.000001 ? num(pos.fee_usd) / Math.abs(num(pos.il_usd)) : 0;
            return `
                <tr>
                    <td><span class="mono">${idx + 1}</span></td>
                    <td><strong>${poolLink(pos.pool_id)}</strong><div class="muted-mini">NFT #${escapeHTML(pos.token_id || '-')}</div><div class="muted-mini">${short(pos.position_id)}</div></td>
                    <td><span class="badge-chain base">Base</span></td>
                    <td><span class="badge-dex">${escapeHTML(pos.source || 'datasource')}</span></td>
                    <td class="mono"><strong>$${money(pos.valuation_usd)}</strong></td>
                    <td class="green-text mono"><strong>${signedMoney(pos.fee_usd)}</strong><div class="muted-mini">cover ${feeCover ? feeCover.toFixed(2) + 'x' : '-'}</div></td>
                    <td class="red-text mono">${signedMoney(pos.il_usd)}<div class="muted-mini">${ilPct.toFixed(4)}%</div></td>
                    <td class="mono">${signedMoney(pos.net_pnl_usd)}</td>
                    <td><a class="action-btn-mini" target="_blank" rel="noreferrer" href="${dexscreenerURL(pos.pool_id)}">查看池子</a></td>
                </tr>`;
        }).join('');
    }

    function renderExitPreflights(preflights) {
        const list = document.getElementById('exit-preflight-list');
        if (!list) return;
        if (!preflights.length) {
            list.innerHTML = '<div class="exit-preflight-empty">暂无真实 NFT 退出预估。等待 position mark 写入 token_id 与 onchain_value。</div>';
            return;
        }
        list.innerHTML = preflights.map(item => `
            <div class="exit-preflight-card">
                <div class="exit-preflight-top">
                    <div>
                        <div class="exit-preflight-title">NFT #${escapeHTML(item.token_id || '-')}</div>
                        <div class="muted-mini">${poolLink(item.pool_id)}</div>
                    </div>
                    <span class="${item.broadcast_enabled ? 'badge-danger' : 'badge-success-glow'}">${item.broadcast_enabled ? 'broadcast enabled' : 'broadcast=false'}</span>
                </div>
                <div class="exit-preflight-metrics">
                    <div><span>可退出总值</span><strong>$${money(item.total_usd)}</strong></div>
                    <div><span>本金估值</span><strong>$${money(item.principal_usd)}</strong></div>
                    <div><span>未领取手续费</span><strong class="green-text">${signedMoney(item.fee_usd)}</strong></div>
                    <div><span>IL</span><strong class="red-text">${signedMoney(item.il_usd)}</strong></div>
                    <div><span>净 PnL</span><strong class="${num(item.net_pnl_usd) >= 0 ? 'green-text' : 'red-text'}">${signedMoney(item.net_pnl_usd)}</strong></div>
                    <div><span>Gas</span><strong>${item.decrease_gas || '-'} / ${item.collect_gas || '-'}</strong></div>
                </div>
                <div class="exit-preflight-footer">
                    <span>${escapeHTML(item.status || 'mark_estimate')}</span>
                    <code>${escapeHTML(item.command || '')}</code>
                </div>
                <div class="muted-mini">decrease tx: ${txLink(item.decrease_tx_hash)} / collect tx: ${txLink(item.collect_tx_hash)}</div>
                ${item.error_msg ? `<div class="muted-mini red-text">error: ${escapeHTML(item.error_msg)}</div>` : ''}
                <div class="muted-mini">source: ${escapeHTML(item.source || '-')} / updated ${timeText(item.updated_at)}</div>
            </div>
        `).join('');
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
        list.innerHTML = items.slice(0, 8).map(ev => `
            <div class="audit-event-card">
                <div class="audit-event-top"><span class="audit-time">${ev.time}</span><span class="audit-type ${ev.type}">${ev.type}</span></div>
                <div class="audit-desc"><strong>${escapeHTML(ev.title)}</strong>: ${escapeHTML(ev.desc)}</div>
            </div>`).join('');
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
        list.innerHTML = (flows.length ? flows : [{time: 'latest', module: 'shadow', type: 'no live tx', chain: 'Base', hash: '', desc: '当前仍是 shadow 观测，没有真实链上执行'}]).map(fl => `
            <div class="flow-item">
                <div class="flow-left"><div class="flow-header"><span class="flow-time">${fl.time}</span><span class="flow-module">${escapeHTML(fl.module)}</span><span class="flow-tag">${escapeHTML(fl.type || '-')}</span></div><div class="flow-desc">${escapeHTML(fl.desc || '-')}</div></div>
                <div class="flow-right">${fl.hash ? chainTxLink(fl.chain, fl.hash) : `<span class="flow-tx">${escapeHTML(fl.source || 'shadow')}</span>`}<span class="badge-success-glow">DB</span></div>
            </div>`).join('');
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
        box.innerHTML = logs.map(([level, module, msg]) => getLogLineHtml({ time: new Date().toLocaleTimeString(), level, module, msg })).join('');
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

    function getLogLineHtml(log) { return `<div class="log-line"><span class="log-time">[${escapeHTML(log.time)}]</span><span class="log-level ${escapeHTML(log.level)}">${escapeHTML(String(log.level).toUpperCase())}</span><span class="log-module">${escapeHTML(log.module)}:</span><span class="log-msg">${escapeHTML(log.msg)}</span></div>`; }
    function appendLog(level, module, msg) { const box = document.getElementById('console-log-box'); if (!box) return; box.insertAdjacentHTML('beforeend', getLogLineHtml({ time: new Date().toLocaleTimeString(), level, module, msg })); box.scrollTop = box.scrollHeight; }
    function radarFromQuality(quality) { const pass = quality.find(q => q.segment === 'passed_pipeline') || {}; return [num(pass.count) * 20, num(pass.avg_volatility), 100 - Math.min(100, num(pass.avg_volatility)), num(pass.avg_tvl), num(pass.avg_security), num(pass.avg_fee_apr)].map(v => Math.max(0, Math.min(100, v || 0))); }
    function groupSum(rows, key, valueKey) { return rows.reduce((out, row) => { const k = row[key] || 'unknown'; out[k] = (out[k] || 0) + num(row[valueKey]); return out; }, {}); }
    function sum(rows, key) { return rows.reduce((total, row) => total + num(row[key]), 0); }
    function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
    function num(value) { const n = Number(value || 0); return Number.isFinite(n) ? n : 0; }
    function fmtBalance(value) { const n = num(value); return n ? n.toLocaleString(undefined, { maximumFractionDigits: 8 }) : '0'; }
    function money(value) { return Math.abs(num(value)).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
    function signedMoney(value) { const n = num(value); return (n >= 0 ? '+' : '-') + money(n); }
    function compactMoney(value) { const n = num(value); if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M'; if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(2) + 'K'; return n.toFixed(2); }
    function short(value) { const s = String(value || ''); return s.length > 18 ? s.slice(0, 8) + '...' + s.slice(-6) : s; }
    function timeText(unix) { return unix ? new Date(num(unix) * 1000).toLocaleTimeString() : '-'; }
    function dexscreenerURL(poolId, chain) { return `https://dexscreener.com/${num(chain) === 2 ? 'solana' : 'base'}/${encodeURIComponent(poolId || '')}`; }
    function geckoURL(poolId, chain) { return `https://www.geckoterminal.com/${num(chain) === 2 ? 'solana' : 'base'}/pools/${encodeURIComponent(poolId || '')}`; }
    function poolLink(poolId, chain) { return `<a target="_blank" rel="noreferrer" href="${dexscreenerURL(poolId, chain)}">${short(poolId)}</a> <a target="_blank" rel="noreferrer" href="${geckoURL(poolId, chain)}">GT</a>`; }
    function txLink(hash) { return hash ? `<a target="_blank" rel="noreferrer" href="https://basescan.org/tx/${escapeHTML(hash)}">${short(hash)}</a>` : '-'; }
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
