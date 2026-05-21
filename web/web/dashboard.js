/**
 * AMM LP 自动套利机器人监控中心 - 前端核心驱动与数据泵
 */

(function () {
    // 全局图表实例
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

    // 状态数据
    const state = {
        aum: 58742897,
        deployed: 41238912,
        available: 17503979,
        pnlToday: 238764,
        pnl7d: 1842517,
        pnlTotal: 12463981,
        fee: 6287451,
        incentives: 3145996,
        il: 1238451,
        gas: 412387,
        netPnl: 10045139,
        bots: 268,
        pools: 1842,
        events: 64182,
        cpu: 32.1,
        mem: 58.3,
        disk: 42.6,
        netSpeed: 182,
        wsConnected: false,
        reconnectAttempts: 0
    };

    // 静态与动态日志池 (用于日志控制台和事件流水)
    const mockLogTemplates = [
        { level: 'info', module: 'scanner-service', msg: 'Alpha Scanner 扫描完成，监控 1,842 个流动性池...' },
        { level: 'info', module: 'risk-service', msg: '决策层风控指标重算：当前全局风险评分 48/100，处于安全区间' },
        { level: 'info', module: 'planner-service', msg: 'State Store 状态一致性同步完成，耗时 42ms' },
        { level: 'info', module: 'watchdog-service', msg: '心跳探测：36/36 种子微服务在线，健康度 98.4%' },
        { level: 'info', module: 'simulation-service', msg: '预执行验证：已成功通过 1,842 场景 Fork 模拟，验证率 98.7%' },
        { level: 'warn', module: 'scanner-service', msg: '监测到 BSC PancakeSwap V3 USDC-WBNB 池流动性偏离 0.18%' },
        { level: 'warn', module: 'risk-service', msg: '套利机会机会评分触发警报：107.175.187.160 延迟微幅升高' },
        { level: 'info', module: 'execution-service', msg: '执行层开始构建套利策略：Shadow LP 仓位再平衡...' },
        { level: 'success', module: 'execution-service', msg: '链上交易广播成功！Tx: 0x[HASH] 成功在 [CHAIN] 确认' }
    ];

    const chainsList = ['Ethereum', 'BSC', 'Arbitrum', 'Solana', 'Polygon'];
    const dexsList = ['Uniswap V3', 'Pancake V3', 'Aerodrome', 'Trader Joe', 'SushiSwap'];

    // 页面初始化入口
    window.addEventListener('DOMContentLoaded', () => {
        // 初始化 Lucide 图标
        lucide.createIcons();

        // 初始化所有 ECharts 实例
        initAllCharts();

        // 渲染初始静态表格与数据
        renderInitialData();

        // 开启数据定时驱动 (模拟模式 or 真实模式)
        startDataPump();

        // 绑定按钮交互
        bindInteractions();

        // 自适应调整
        window.addEventListener('resize', () => {
            Object.values(charts).forEach(chart => {
                if (chart) chart.resize();
            });
        });
    });

    // ----------------- ECharts 初始化 -----------------
    function initAllCharts() {
        const darkTheme = {
            textStyle: { color: '#8c9ba5', fontFamily: 'Inter, sans-serif' }
        };

        // 1. 资金分布 (按 Tier)
        charts.tier = echarts.init(document.getElementById('chart-tier-distribution'), null, darkTheme);
        charts.tier.setOption(getPieOption('资金分布 (Tier)', [
            { value: 34100000, name: 'Tier-A 优质池', itemStyle: { color: '#10b981' } },
            { value: 15300000, name: 'Tier-B 稳健型', itemStyle: { color: '#3b82f6' } },
            { value: 9260000, name: 'Tier-C 探索型', itemStyle: { color: '#fbbf24' } }
        ]));

        // 2. 资金分布 (按链)
        charts.chain = echarts.init(document.getElementById('chart-chain-distribution'), null, darkTheme);
        charts.chain.setOption(getPieOption('资金分布 (链)', [
            { value: 45.2, name: 'Ethereum', itemStyle: { color: '#3b82f6' } },
            { value: 22.1, name: 'BSC', itemStyle: { color: '#fbbf24' } },
            { value: 16.3, name: 'Arbitrum', itemStyle: { color: '#00f0ff' } },
            { value: 10.2, name: 'Base', itemStyle: { color: '#6366f1' } },
            { value: 4.1, name: 'Polygon', itemStyle: { color: '#a855f7' } },
            { value: 2.1, name: '其他', itemStyle: { color: '#6b7280' } }
        ]));

        // 3. 累计 PnL 曲线
        charts.cumulativePnl = echarts.init(document.getElementById('chart-cumulative-pnl'), null, darkTheme);
        charts.cumulativePnl.setOption({
            tooltip: { trigger: 'axis', backgroundColor: 'rgba(13, 21, 46, 0.95)', borderColor: 'rgba(255,255,255,0.06)', textStyle: { color: '#fff' } },
            grid: { top: '15%', left: '3%', right: '3%', bottom: '5%', containLabel: true },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: ['05-20', '05-21', '05-22', '05-23', '05-24', '05-25', '05-26', '05-27'],
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
            },
            yAxis: {
                type: 'value',
                axisLabel: { formatter: '${value}M' },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)' } }
            },
            series: [{
                name: '累计 PnL',
                type: 'line',
                smooth: true,
                symbol: 'circle',
                symbolSize: 6,
                data: [10.2, 10.5, 10.9, 11.2, 11.6, 12.0, 12.2, 12.46],
                itemStyle: { color: '#10b981' },
                lineStyle: { width: 3, shadowBlur: 10, shadowColor: 'rgba(16, 185, 129, 0.5)' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(16, 185, 129, 0.25)' },
                        { offset: 1, color: 'rgba(16, 185, 129, 0)' }
                    ])
                }
            }]
        });

        // 4. 收益构成 (24H, USD)
        charts.revenueBreakdown = echarts.init(document.getElementById('chart-revenue-breakdown'), null, darkTheme);
        charts.revenueBreakdown.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(13, 21, 46, 0.95)', borderColor: 'rgba(255,255,255,0.06)' },
            legend: { right: '0%', textStyle: { color: '#8c9ba5' }, itemWidth: 10, itemHeight: 10 },
            grid: { top: '20%', left: '3%', right: '3%', bottom: '5%', containLabel: true },
            xAxis: {
                type: 'category',
                data: ['05-20', '05-21', '05-22', '05-23', '05-24', '05-25', '05-26', '05-27'],
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
            },
            yAxis: {
                type: 'value',
                axisLabel: { formatter: '{value}K' },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)' } }
            },
            series: [
                { name: 'Fee', type: 'bar', stack: 'total', itemStyle: { color: '#10b981' }, data: [120, 150, 180, 140, 190, 210, 175, 238] },
                { name: 'Incentives', type: 'bar', stack: 'total', itemStyle: { color: '#fbbf24' }, data: [45, 60, 55, 70, 65, 80, 75, 95] },
                { name: 'Gas', type: 'bar', stack: 'total', itemStyle: { color: '#ef4444' }, data: [-12, -15, -18, -10, -22, -25, -20, -32] },
                { name: 'IL', type: 'bar', stack: 'total', itemStyle: { color: '#3b82f6' }, data: [-35, -42, -50, -20, -62, -75, -55, -85] }
            ]
        });

        // 5. Strategy层雷达图
        charts.strategyRadar = echarts.init(document.getElementById('chart-strategy-radar'), null, darkTheme);
        charts.strategyRadar.setOption({
            radar: {
                indicator: [
                    { name: 'Pool选择', max: 100 },
                    { name: '波动率评估', max: 100 },
                    { name: 'IL风险审计', max: 100 },
                    { name: '深度评级', max: 100 },
                    { name: '流动性稳定性', max: 100 },
                    { name: 'APR匹配分', max: 100 }
                ],
                center: ['50%', '50%'],
                radius: '65%',
                axisName: { color: '#8c9ba5', fontSize: 10 },
                splitArea: { show: false },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)' } },
                lineStyle: { color: 'rgba(255,255,255,0.05)' }
            },
            series: [{
                type: 'radar',
                data: [{
                    value: [85, 78, 92, 80, 88, 95],
                    name: '策略质量',
                    itemStyle: { color: '#00f0ff' },
                    areaStyle: { color: 'rgba(0, 240, 255, 0.15)' }
                }]
            }]
        });

        // 6. 风险审计环形图
        charts.auditDistribution = echarts.init(document.getElementById('chart-audit-distribution'), null, darkTheme);
        charts.auditDistribution.setOption({
            tooltip: { show: false },
            series: [{
                type: 'pie',
                radius: ['60%', '85%'],
                avoidLabelOverlap: false,
                label: { show: false },
                data: [
                    { value: 94.2, itemStyle: { color: '#10b981' } },
                    { value: 4.6, itemStyle: { color: '#fbbf24' } },
                    { value: 1.2, itemStyle: { color: '#ef4444' } }
                ]
            }]
        });

        // 7. Rebalance 时间线 (7天)
        charts.rebalanceTimeline = echarts.init(document.getElementById('chart-rebalance-timeline'), null, darkTheme);
        charts.rebalanceTimeline.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(13, 21, 46, 0.95)' },
            grid: { top: '15%', left: '3%', right: '3%', bottom: '5%', containLabel: true },
            xAxis: {
                type: 'category',
                data: ['05-21', '05-22', '05-23', '05-24', '05-25', '05-26', '05-27'],
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
            },
            yAxis: {
                type: 'value',
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)' } }
            },
            series: [
                { name: '成功', type: 'bar', stack: 'stack', itemStyle: { color: '#10b981' }, data: [45, 52, 50, 48, 57, 63, 58] },
                { name: '失败', type: 'bar', stack: 'stack', itemStyle: { color: '#ef4444' }, data: [2, 1, 3, 1, 2, 3, 3] },
                { name: '待处理', type: 'bar', stack: 'stack', itemStyle: { color: '#3b82f6' }, data: [1, 2, 1, 3, 1, 3, 3] }
            ]
        });

        // 8. 多策略收益对比
        charts.strategyComparison = echarts.init(document.getElementById('chart-strategy-comparison'), null, darkTheme);
        charts.strategyComparison.setOption({
            tooltip: { trigger: 'axis', backgroundColor: 'rgba(13, 21, 46, 0.95)' },
            legend: { right: '0%', textStyle: { color: '#8c9ba5' }, itemWidth: 8 },
            grid: { top: '18%', left: '3%', right: '3%', bottom: '5%', containLabel: true },
            xAxis: {
                type: 'category',
                data: ['05-21', '05-22', '05-23', '05-24', '05-25', '05-26', '05-27'],
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
            },
            yAxis: {
                type: 'value',
                axisLabel: { formatter: '${value}M' },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)' } }
            },
            series: [
                { name: 'Shadow LP', type: 'line', smooth: true, symbol: 'none', itemStyle: { color: '#a855f7' }, data: [1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.82] },
                { name: 'Tiny Live', type: 'line', smooth: true, symbol: 'none', itemStyle: { color: '#3b82f6' }, data: [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.12] },
                { name: 'Active LP', type: 'line', smooth: true, symbol: 'none', itemStyle: { color: '#10b981' }, data: [0.4, 0.45, 0.5, 0.52, 0.58, 0.62, 0.68] }
            ]
        });

        // 9-11. 系统资源圆环 (Gauge 弧度)
        charts.knobCpu = echarts.init(document.getElementById('knob-cpu'), null, darkTheme);
        charts.knobCpu.setOption(getKnobOption(32.1, '#10b981'));

        charts.knobMem = echarts.init(document.getElementById('knob-mem'), null, darkTheme);
        charts.knobMem.setOption(getKnobOption(58.3, '#3b82f6'));

        charts.knobDisk = echarts.init(document.getElementById('knob-disk'), null, darkTheme);
        charts.knobDisk.setOption(getKnobOption(42.6, '#a855f7'));
    }

    function getPieOption(name, data) {
        return {
            tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)', backgroundColor: 'rgba(13, 21, 46, 0.95)', borderColor: 'rgba(255,255,255,0.06)', textStyle: { color: '#fff' } },
            series: [{
                name: name,
                type: 'pie',
                radius: ['45%', '75%'],
                avoidLabelOverlap: false,
                itemStyle: { borderRadius: 4 },
                label: { show: false },
                labelLine: { show: false },
                data: data
            }]
        };
    }

    function getKnobOption(val, color) {
        return {
            series: [{
                type: 'gauge',
                startAngle: 90,
                endAngle: -270,
                pointer: { show: false },
                progress: { show: true, overlap: false, roundCap: true, clip: false, itemStyle: { color: color } },
                axisLine: { lineStyle: { width: 4, color: [['1', 'rgba(255,255,255,0.02)']] } },
                splitLine: { show: false },
                axisTick: { show: false },
                axisLabel: { show: false },
                data: [{ value: val }],
                detail: { show: false }
            }]
        };
    }

    // ----------------- 初始渲染静态内容 -----------------
    function renderInitialData() {
        // 1. Alpha Scanner 表格
        const scannerTbody = document.getElementById('alpha-scanner-tbody');
        const scannerRows = [
            { rank: 1, pool: 'ETH-USDC (0.05%)', chain: 'Ethereum', dex: 'Uniswap V3', apr: 92.6, il: 1.8, risk: 'A', tier: 'Tier-A', score: 92.1, status: '候选' },
            { rank: 2, pool: 'SOL-USDC (0.25%)', chain: 'Solana', dex: 'Orca', apr: 80.3, il: 2.1, risk: 'A', tier: 'Tier-A', score: 88.7, status: '候选' },
            { rank: 3, pool: 'WETH-USDC (0.01%)', chain: 'Arbitrum', dex: 'Uniswap V3', apr: 71.9, il: 1.6, risk: 'A', tier: 'Tier-A', score: 86.2, status: '候选' },
            { rank: 4, pool: 'BNB-USDT (0.25%)', chain: 'BSC', dex: 'Pancake V3', apr: 66.7, il: 2.7, risk: 'B', tier: 'Tier-B', score: 82.1, status: '候选' },
            { rank: 5, pool: 'ARB-USDC (0.05%)', chain: 'Arbitrum', dex: 'Uniswap V3', apr: 58.2, il: 2.0, risk: 'B', tier: 'Tier-B', score: 78.6, status: '观察' }
        ];

        scannerTbody.innerHTML = scannerRows.map(row => `
            <tr>
                <td><span class="mono">${row.rank}</span></td>
                <td><strong>${row.pool}</strong></td>
                <td><span class="badge-chain ${row.chain.toLowerCase()}">${row.chain}</span></td>
                <td><span class="badge-dex">${row.dex}</span></td>
                <td class="green-text mono"><strong>${row.apr}%</strong></td>
                <td class="mono">${row.il}%</td>
                <td><span class="mono font-12">${row.risk}</span></td>
                <td><span class="mono font-12">${row.tier}</span></td>
                <td class="green-text mono"><strong>${row.score}</strong></td>
                <td><span class="${row.status === '候选' ? 'badge-success-glow' : 'green-badge'}">${row.status}</span></td>
            </tr>
        `).join('');

        // 2. 异常事件初始化
        const auditList = document.getElementById('audit-events-list');
        const auditEvents = [
            { time: '14:31', type: 'danger', title: 'WETH/USDC', desc: '价格偏离异常高 - 成功阻断' },
            { time: '14:26', type: 'warning', title: 'SOL/USDC', desc: '池流动性突然萎缩 - 降配' },
            { time: '14:21', type: 'success', title: 'BNB/USDT', desc: '滑点溢出，合约回滚成功' },
            { time: '14:18', type: 'warning', title: 'ARB/USDC', desc: '跨链事件通知有小幅延迟' }
        ];

        auditList.innerHTML = auditEvents.map(ev => `
            <div class="audit-event-card">
                <div class="audit-event-top">
                    <span class="audit-time">${ev.time}</span>
                    <span class="audit-type ${ev.type}">${ev.type === 'danger' ? '⚠️ 极高风险' : ev.type === 'warning' ? '⚡ 警告' : '✔ 安全成功'}</span>
                </div>
                <div class="audit-desc"><strong>${ev.title}</strong>: ${ev.desc}</div>
            </div>
        `).join('');

        // 3. 主动 LP 持仓与仓位明细
        const lpTbody = document.getElementById('lp-positions-tbody');
        const lpPositions = [
            { id: 1, pool: 'WETH-USDC (0.05%)', chain: 'Ethereum', dex: 'Uniswap V3', value: '5.21M', apr: '18.4%', il: '-$1.2K', share: '12.6%' },
            { id: 2, pool: 'SOL-USDC (0.25%)', chain: 'Solana', dex: 'Orca', value: '3.48M', apr: '17.1%', il: '-$0.8K', share: '8.4%' },
            { id: 3, pool: 'ETH-USDC (0.01%)', chain: 'Arbitrum', dex: 'Uniswap V3', value: '2.95M', apr: '14.6%', il: '-$0.6K', share: '7.1%' },
            { id: 4, pool: 'BNB-USDT (0.25%)', chain: 'BSC', dex: 'Pancake V3', value: '2.28M', apr: '13.2%', il: '-$0.5K', share: '5.5%' },
            { id: 5, pool: 'ARB-USDC (0.05%)', chain: 'Arbitrum', dex: 'Uniswap V3', value: '1.93M', apr: '12.1%', il: '-$0.3K', share: '4.7%' }
        ];

        lpTbody.innerHTML = lpPositions.map(pos => `
            <tr>
                <td><span class="mono">${pos.id}</span></td>
                <td><strong>${pos.pool}</strong></td>
                <td><span class="badge-chain ${pos.chain.toLowerCase()}">${pos.chain}</span></td>
                <td><span class="badge-dex">${pos.dex}</span></td>
                <td class="mono"><strong>$${pos.value}</strong></td>
                <td class="green-text mono"><strong>${pos.apr}</strong></td>
                <td class="red-text mono">${pos.il}</td>
                <td class="mono">${pos.share}</td>
                <td><button class="action-btn-mini">仓位调整</button></td>
            </tr>
        `).join('');

        // 4. 执行流水与事件总线
        const flowList = document.getElementById('execution-flow-list');
        const flowEvents = [
            { time: '14:31:22', module: 'execution-service', type: 'Add LP', chain: 'Ethereum', tx: '0x9a...7b21' },
            { time: '14:28:10', module: 'execution-service', type: 'Rebalance', chain: 'Solana', tx: '0x3b...e912' },
            { time: '14:26:55', module: 'execution-service', type: 'Remove LP', chain: 'Arbitrum', tx: '0x1c...af32' },
            { time: '14:24:18', module: 'execution-service', type: 'Approve', chain: 'Arbitrum', tx: '0xfc...d182' },
            { time: '14:21:07', module: 'execution-service', type: 'Revoke', chain: 'BSC', tx: '0x5d...a773' }
        ];

        flowList.innerHTML = flowEvents.map(fl => `
            <div class="flow-item">
                <div class="flow-left">
                    <div class="flow-header">
                        <span class="flow-time">${fl.time}</span>
                        <span class="flow-module">${fl.module}</span>
                        <span class="flow-tag">${fl.type}</span>
                    </div>
                    <div class="flow-desc">在 ${fl.chain} 上触发 [${fl.type}] 并成功通过滑点与阈值校验</div>
                </div>
                <div class="flow-right">
                    <a href="#" class="flow-tx">${fl.tx}</a>
                    <span class="badge-success-glow">成功</span>
                </div>
            </div>
        `).join('');

        // 5. 日志终端初始填充
        const consoleBox = document.getElementById('console-log-box');
        const initialLogs = [
            { time: '14:29:12', level: 'info', module: 'scanner', msg: 'Alpha Scanner initialized successfully. Monitoring 1,842 pairs...' },
            { time: '14:29:15', level: 'info', module: 'risk', msg: 'Risk manager active. Main Circuit Breaker state: NORMAL (Closed).' },
            { time: '14:30:02', level: 'info', module: 'planner', msg: 'New rebalance strategy generated for Uniswap V3 WETH-USDC.' },
            { time: '14:30:10', level: 'info', module: 'simulation', msg: 'Simulation results: Gas estimation 132,452. Clear touch dev: 0.28%.' },
            { time: '14:31:22', level: 'success', module: 'execution', msg: 'Add LP transaction successfully verified on Ethereum. Tx: 0x9a...7b21' },
            { time: '14:32:05', level: 'info', module: 'watchdog', msg: 'All 36/36 service heartbeats detected. System Health index: 98.4%' }
        ];

        consoleBox.innerHTML = initialLogs.map(getLogLineHtml).join('');
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }

    function getLogLineHtml(log) {
        return `
            <div class="log-line">
                <span class="log-time">[${log.time}]</span>
                <span class="log-level ${log.level}">${log.level.toUpperCase()}</span>
                <span class="log-module">${log.module}:</span>
                <span class="log-msg">${log.msg}</span>
            </div>
        `;
    }

    // ----------------- 数据流驱动核心 (模拟 VS 真实) -----------------
    function startDataPump() {
        if (window.DashboardConfig.enableMockData) {
            // 启用高保真动态模拟发生器
            document.getElementById('degrade-alert').classList.add('hidden'); // 隐藏降级横幅
            
            // 1. 每 1000ms 高频更新 (数值跳动、控制台追加日志、系统资源抖动)
            setInterval(tickHighFrequencyMock, window.DashboardConfig.heartbeatInterval);

            // 2. 每 5000ms 中频更新 (大折线图追加最新数据点，列表追加新事务)
            setInterval(tickMediumFrequencyMock, window.DashboardConfig.refreshInterval);
        } else {
            // 真实数据对接：轮询 REST API
            fetchRealOverviewData();
            setInterval(fetchRealOverviewData, window.DashboardConfig.refreshInterval);

            // 接入 WebSocket
            initRealWebSocket();
        }
    }

    // --- 模拟高频 Tick ---
    function tickHighFrequencyMock() {
        // AUM 微幅跳动 (加减 10-100 美元)
        const aumDiff = Math.floor(Math.random() * 180) - 80;
        state.aum += aumDiff;
        state.deployed += Math.floor(aumDiff * 0.7);
        state.available += Math.floor(aumDiff * 0.3);
        state.pnlToday += Math.floor(aumDiff * 0.05);
        state.pnlTotal += Math.floor(aumDiff * 0.08);
        state.netPnl += Math.floor(aumDiff * 0.07);

        // 更新大字卡片看板 DOM (注意加入千分位格式化)
        document.getElementById('val-aum').innerText = formatMoney(state.aum);
        document.getElementById('val-deployed').innerText = formatMoney(state.deployed);
        document.getElementById('val-available').innerText = formatMoney(state.available);
        
        const todayDom = document.getElementById('val-pnl-today');
        todayDom.innerText = formatMoney(state.pnlToday);
        
        document.getElementById('val-pnl-total').innerText = formatMoney(state.pnlTotal);
        document.getElementById('val-net-pnl').innerText = formatMoney(state.netPnl);

        // CPU & 内存占用波动
        state.cpu = Math.max(10, Math.min(95, state.cpu + (Math.random() * 8 - 4)));
        state.mem = Math.max(30, Math.min(90, state.mem + (Math.random() * 2 - 1)));
        
        document.getElementById('knob-cpu-val').innerText = state.cpu.toFixed(1) + '%';
        document.getElementById('knob-mem-val').innerText = state.mem.toFixed(1) + '%';
        
        charts.knobCpu.setOption({ series: [{ data: [{ value: state.cpu }] }] });
        charts.knobMem.setOption({ series: [{ data: [{ value: state.mem }] }] });

        // 随机产生一条微小日志追加到控制台终端
        if (Math.random() > 0.6) {
            appendRandomConsoleLog();
        }
        
        // 动态更新 Header 顶部的最后更新时钟
        const now = new Date();
        document.getElementById('update-time').innerText = now.getFullYear() + '-' +
            padZero(now.getMonth() + 1) + '-' + padZero(now.getDate()) + ' ' +
            padZero(now.getHours()) + ':' + padZero(now.getMinutes()) + ':' + padZero(now.getSeconds());
    }

    // --- 模拟中频 Tick (流水事件、新异常) ---
    function tickMediumFrequencyMock() {
        // 1. 在累计 PnL 曲线中平滑拉伸
        const pnlData = charts.cumulativePnl.getOption().series[0].data;
        pnlData.shift();
        const lastVal = pnlData[pnlData.length - 1];
        pnlData.push(Number((lastVal + (Math.random() * 0.15 - 0.02)).toFixed(2)));
        charts.cumulativePnl.setOption({ series: [{ data: pnlData }] });

        // 2. 随机在执行流水追加新 Tx
        if (Math.random() > 0.4) {
            appendNewExecutionTx();
        }

        // 3. 随机追加新异常警告
        if (Math.random() > 0.8) {
            appendNewAuditWarning();
        }
    }

    // --- 随机追加控制台日志 ---
    function appendRandomConsoleLog() {
        const consoleBox = document.getElementById('console-log-box');
        const randTemplate = mockLogTemplates[Math.floor(Math.random() * mockLogTemplates.length)];
        
        const now = new Date();
        const timeStr = padZero(now.getHours()) + ':' + padZero(now.getMinutes()) + ':' + padZero(now.getSeconds());
        
        let customMsg = randTemplate.msg;
        if (customMsg.includes('[HASH]')) {
            customMsg = customMsg.replace('[HASH]', Math.random().toString(16).substring(2, 8));
        }
        if (customMsg.includes('[CHAIN]')) {
            customMsg = customMsg.replace('[CHAIN]', chainsList[Math.floor(Math.random() * chainsList.length)]);
        }

        const logLine = {
            time: timeStr,
            level: randTemplate.level,
            module: randTemplate.module.split('-')[0],
            msg: customMsg
        };

        const wrapper = document.createElement('div');
        wrapper.innerHTML = getLogLineHtml(logLine);
        consoleBox.appendChild(wrapper.firstElementChild);

        // 控制只保留最多 100 行
        if (consoleBox.children.length > 100) {
            consoleBox.removeChild(consoleBox.firstChild);
        }
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }

    // --- 随机追加 Tx 执行流水 ---
    function appendNewExecutionTx() {
        const flowList = document.getElementById('execution-flow-list');
        const now = new Date();
        const timeStr = padZero(now.getHours()) + ':' + padZero(now.getMinutes()) + ':' + padZero(now.getSeconds());
        const chain = chainsList[Math.floor(Math.random() * chainsList.length)];
        const dex = dexsList[Math.floor(Math.random() * dexsList.length)];
        const txTypes = ['Add LP', 'Rebalance', 'Remove LP', 'Approve'];
        const type = txTypes[Math.floor(Math.random() * txTypes.length)];
        const hash = '0x' + Math.random().toString(16).substring(2, 6) + '...' + Math.random().toString(16).substring(2, 6);

        const flowItem = document.createElement('div');
        flowItem.className = 'flow-item';
        flowItem.innerHTML = `
            <div class="flow-item">
                <div class="flow-left">
                    <div class="flow-header">
                        <span class="flow-time">${timeStr}</span>
                        <span class="flow-module">execution-service</span>
                        <span class="flow-tag">${type}</span>
                    </div>
                    <div class="flow-desc">在 ${chain} 的 ${dex} 上触发 [${type}]。通过最优 Gas 与滑点验证。</div>
                </div>
                <div class="flow-right">
                    <a href="#" class="flow-tx">${hash}</a>
                    <span class="badge-success-glow">成功</span>
                </div>
            </div>
        `;

        flowList.insertBefore(flowItem.firstElementChild, flowList.firstChild);
        if (flowList.children.length > 30) {
            flowList.removeChild(flowList.lastChild);
        }
    }

    // --- 随机追加审计异常 ---
    function appendNewAuditWarning() {
        const auditList = document.getElementById('audit-events-list');
        const now = new Date();
        const timeStr = padZero(now.getHours()) + ':' + padZero(now.getMinutes());
        const pools = ['ETH-USDT', 'SOL-WETH', 'WBTC-USDC', 'LINK-WETH'];
        const pool = pools[Math.floor(Math.random() * pools.length)];
        const types = ['warning', 'danger'];
        const type = types[Math.floor(Math.random() * types.length)];
        const desc = type === 'danger' ? '监测到异常闪电贷套利套取风险 - 快速降级阻断' : '池子滑点指标短时剧烈跳动 - 启用滑点保护机制';

        const card = document.createElement('div');
        card.className = 'audit-event-card';
        card.innerHTML = `
            <div class="audit-event-card">
                <div class="audit-event-top">
                    <span class="audit-time">${timeStr}</span>
                    <span class="audit-type ${type}">${type === 'danger' ? '⚠️ 极高风险' : '⚡ 警告'}</span>
                </div>
                <div class="audit-desc"><strong>${pool}</strong>: ${desc}</div>
            </div>
        `;

        auditList.insertBefore(card.firstElementChild, auditList.firstChild);
        if (auditList.children.length > 20) {
            auditList.removeChild(auditList.lastChild);
        }
    }

    // ----------------- 真实数据对接 (轮询 + WebSocket) -----------------
    function fetchRealOverviewData() {
        fetch(window.DashboardConfig.apiBaseUrl + '/overview')
            .then(res => {
                if (!res.ok) throw new Error('API server status invalid');
                return res.json();
            })
            .then(data => {
                // 收到真实数据！隐藏警告横幅
                document.getElementById('degrade-alert').classList.add('hidden');
                
                // 绑定到页面 DOM
                bindRealDataToDom(data);
            })
            .catch(err => {
                console.warn('Unable to fetch overview data, degrading to mock:', err);
                // 显示优雅降级横幅
                document.getElementById('degrade-alert').classList.remove('hidden');
            });
    }

    function bindRealDataToDom(data) {
        // 更新大字指标
        state.aum = data.aum;
        state.deployed = data.deployed;
        state.available = data.available;
        state.pnlToday = data.pnl_today;
        state.pnl7d = data.pnl_7d;
        state.pnlTotal = data.pnl_total;
        
        document.getElementById('val-aum').innerText = formatMoney(state.aum);
        document.getElementById('val-deployed').innerText = formatMoney(state.deployed);
        document.getElementById('val-available').innerText = formatMoney(state.available);
        document.getElementById('val-pnl-today').innerText = formatMoney(state.pnlToday);
        document.getElementById('val-pnl-total').innerText = formatMoney(state.pnlTotal);
        
        // 更新图表 (示例：只更新累计折线)
        if (data.cumulative_pnl_chart) {
            charts.cumulativePnl.setOption({
                xAxis: { data: data.cumulative_pnl_chart.dates },
                series: [{ data: data.cumulative_pnl_chart.values }]
            });
        }
    }

    function initRealWebSocket() {
        if (state.wsConnected) return;

        const ws = new WebSocket(window.DashboardConfig.wsUrl);

        ws.onopen = () => {
            console.log('WebSocket connected to lpbot live server');
            state.wsConnected = true;
            state.reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                
                // 根据实时推送的内容刷新不同组件
                if (msg.type === 'log') {
                    // 接收日志流
                    appendLiveLog(msg.data);
                } else if (msg.type === 'system_resource') {
                    // 接收硬件资源实时利用率
                    appendLiveSystemResource(msg.data);
                } else if (msg.type === 'transaction') {
                    // 接收最新交易完成推送
                    appendLiveTransaction(msg.data);
                }
            } catch (err) {
                console.error('Error parsing WebSocket live payload:', err);
            }
        };

        ws.onclose = () => {
            state.wsConnected = false;
            console.warn('WebSocket disconnected, preparing to retry...');
            
            // 自动重连 (退避重试)
            if (state.reconnectAttempts < 10) {
                state.reconnectAttempts++;
                setTimeout(initRealWebSocket, Math.min(10000, 1000 * state.reconnectAttempts));
            }
        };
    }

    function appendLiveLog(log) {
        const consoleBox = document.getElementById('console-log-box');
        const wrapper = document.createElement('div');
        wrapper.innerHTML = getLogLineHtml({
            time: log.time,
            level: log.level,
            module: log.module,
            msg: log.message
        });
        consoleBox.appendChild(wrapper.firstElementChild);
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }

    function appendLiveSystemResource(res) {
        document.getElementById('knob-cpu-val').innerText = res.cpu.toFixed(1) + '%';
        document.getElementById('knob-mem-val').innerText = res.mem.toFixed(1) + '%';
        charts.knobCpu.setOption({ series: [{ data: [{ value: res.cpu }] }] });
        charts.knobMem.setOption({ series: [{ data: [{ value: res.mem }] }] });
        
        if (res.net_speed) {
            document.getElementById('net-speed-val').innerText = res.net_speed + ' Mbps';
        }
    }

    function appendLiveTransaction(tx) {
        const flowList = document.getElementById('execution-flow-list');
        const flowItem = document.createElement('div');
        flowItem.className = 'flow-item';
        flowItem.innerHTML = `
            <div class="flow-item">
                <div class="flow-left">
                    <div class="flow-header">
                        <span class="flow-time">${tx.time}</span>
                        <span class="flow-module">${tx.module}</span>
                        <span class="flow-tag">${tx.type}</span>
                    </div>
                    <div class="flow-desc">在 ${tx.chain} 上成功执行交易，哈希为 ${tx.hash}。成功率 ${tx.success_rate}%。</div>
                </div>
                <div class="flow-right">
                    <a href="#" class="flow-tx">${tx.hash.substring(0, 6)}...${tx.hash.substring(tx.hash.length - 4)}</a>
                    <span class="badge-success-glow">成功</span>
                </div>
            </div>
        `;
        flowList.insertBefore(flowItem.firstElementChild, flowList.firstChild);
    }

    // ----------------- 辅助工具函数 -----------------
    function formatMoney(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    function padZero(num) {
        return num < 10 ? '0' + num : num;
    }

    // ----------------- 绑定控制台开关交互 -----------------
    function bindInteractions() {
        const btnCircuit = document.getElementById('btn-circuit-breaker');
        btnCircuit.addEventListener('click', () => {
            if (btnCircuit.classList.contains('active-on')) {
                btnCircuit.classList.remove('active-on');
                btnCircuit.querySelector('.switch-status-label').innerText = 'ON';
                btnCircuit.querySelector('.switch-txt').innerText = '套利中断中';
                btnCircuit.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
                btnCircuit.style.borderColor = 'var(--red-glow)';
                
                // 弹窗提示
                alert('⚠️ 警告：已手动触发全局熔断！机器人将立刻暂停一切活跃套利行为，进入紧急防御观察模式！');
            } else {
                btnCircuit.classList.add('active-on');
                btnCircuit.querySelector('.switch-status-label').innerText = 'OFF';
                btnCircuit.querySelector('.switch-txt').innerText = '全局暂停';
                btnCircuit.style.backgroundColor = '';
                btnCircuit.style.borderColor = '';
            }
        });

        const btnRange = document.getElementById('btn-range-adjust');
        btnRange.addEventListener('click', () => {
            if (btnRange.classList.contains('active-on-green')) {
                btnRange.classList.remove('active-on-green');
                btnRange.querySelector('.switch-status-label').innerText = 'OFF';
                btnRange.style.backgroundColor = 'rgba(255,255,255,0.03)';
                btnRange.style.borderColor = 'rgba(255,255,255,0.06)';
                btnRange.style.color = 'var(--text-secondary)';
            } else {
                btnRange.classList.add('active-on-green');
                btnRange.querySelector('.switch-status-label').innerText = 'ON';
                btnRange.style.backgroundColor = '';
                btnRange.style.borderColor = '';
                btnRange.style.color = '';
            }
        });
    }

})();
