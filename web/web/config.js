// AMM LP 自动套利机器人监控中心 - 前端配置文件
window.DashboardConfig = {
    // 是否启用高保真动态模拟数据。在未对接真实后端 API 时，请保持为 true。
    enableMockData: true,

    // 真实后端 RESTful API 基地址 (若前后端同端口部署，直接写 '/api' 即可)
    apiBaseUrl: '/api',

    // 真实后端 WebSocket 推送地址
    wsUrl: 'ws://' + window.location.host + '/ws',

    // 轮询拉取真实数据时的自动刷新间隔（单位：毫秒）
    refreshInterval: 5000,

    // 模拟数据及高频指标（如 CPU、实时日志）的刷新/心跳间隔（单位：毫秒）
    heartbeatInterval: 1000
};
