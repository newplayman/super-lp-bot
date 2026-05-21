# AMM LP 自动套利机器人监控中心 - 数据对接与 API 规范文档

本文件旨在为后端开发团队提供完整、无缝的前端数据接入指南。监控中心前端由纯 HTML5 + Vanilla CSS3 + Vanilla JS 构建，采用轻量化、高性能架构。在不需要任何 Node.js 编译构建的情况下，即可实现与 Go 后端服务的无缝对接。

监控中心提供两种工作模式，通过 `web/config.js` 的 `enableMockData` 字段进行控制：
1. **本地模拟模式（`enableMockData: true`）**：前端启用高保真动态模拟数据发生器，自动产生波动指标、实时日志及交易流水，便于离线演示与静态展示。
2. **真实数据模式（`enableMockData: false`）**：前端将通过 RESTful API 进行轮询，并通过 WebSocket 实时订阅系统日志、性能资源与链上交易流。如果真实 API 请求失败，前端右上角会闪烁科技感极强的 **“⚠️ 已降级为模拟数据”** 警告横幅，并平滑切换到本地数据泵，避免页面留白或卡死，在网络恢复后自动切回。

---

## 一、 Go 后端静态资源托管方案

由于前端是纯静态页面，您可以使用 Go 语言的标准库 `net/http` 极简、高效地托管前端资源。

以下是推荐的 Go 代码实现示例：

```go
package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
)

func main() {
	// 定义前端静态资源目录（相对于运行目录的相对路径或绝对路径）
	webDir := "./web"

	// 检查目录是否存在
	if _, err := os.Stat(webDir); os.IsNotExist(err) {
		log.Fatalf("错误: 前端静态目录 %s 不存在，请检查路径！", webDir)
	}

	// 1. 创建静态文件服务
	fileServer := http.FileServer(http.Dir(webDir))

	// 2. 托管静态文件路由
	// 将所有非 /api 和非 /ws 的请求都路由给静态文件服务
	http.Handle("/", fileServer)

	// 3. 注册 REST API 路由（详见第二部分）
	http.HandleFunc("/api/overview", overviewHandler)

	// 4. 注册 WebSocket 路由（详见第三部分）
	http.HandleFunc("/ws", wsHandler)

	// 5. 启动 HTTP 服务
	port := ":8080"
	log.Printf("🤖 LP-Bot 监控中心已启动! 访问地址: http://localhost%s", port)
	if err := http.ListenAndServe(port, nil); err != nil {
		log.Fatalf("服务启动失败: %v", err)
	}
}

// 模拟的 REST 处理器
func overviewHandler(w http.ResponseWriter, r *http.Request) {
	// 实际开发中在此处处理跨域及响应真实 JSON 数据
}

// 模拟的 WebSocket 处理器
func wsHandler(w http.ResponseWriter, r *http.Request) {
	// 实际开发中在此处升级并维持 Websocket 长连接
}
```

> [!TIP]
> **跨域处理 (CORS)**：如果在开发阶段前后端采用分离端口运行（如前端本地双击运行，后端服务在 `8080`），请在 Go 后端对应的 API 响应头中添加 CORS 支持：
> `w.Header().Set("Access-Control-Allow-Origin", "*")`
> `w.Header().Set("Access-Control-Allow-Headers", "Content-Type")`

---

## 二、 RESTful API 规范

前端通过标准 RESTful 接口拉取周期性汇总数据。接口刷新频率由 `web/config.js` 中的 `refreshInterval` 参数决定（默认 `5000ms`）。

### 1. 核心看板汇总接口

* **接口路径**：`/api/overview`
* **请求方法**：`GET`
* **Content-Type**：`application/json`
* **响应 JSON 结构**：
  | 字段名 | 类型 | 说明 | 示例 |
  | :--- | :--- | :--- | :--- |
  | `aum` | `number (int)` | 管理总资产 (AUM)，单位 USD | `58742897` |
  | `deployed` | `number (int)` | 已部署/运行中资金，单位 USD | `41238912` |
  | `available` | `number (int)` | 空闲/可用资金，单位 USD | `17503979` |
  | `pnl_today` | `number (int)` | 今日净收益 (PnL)，单位 USD | `238764` |
  | `pnl_7d` | `number (int)` | 过去 7 天累计收益，单位 USD | `1842517` |
  | `pnl_total` | `number (int)` | 历史累计总收益，单位 USD | `12463981` |
  | `cumulative_pnl_chart` | `object` | 累计收益折线图历史数据点包 | 见下 |
  | `cumulative_pnl_chart.dates` | `array[string]` | 横轴日期数据（最近 8 个节点，按时间顺序排列） | `["05-20", "05-21", ...]` |
  | `cumulative_pnl_chart.values` | `array[number]` | 对应日期的累计收益数值（单位：百万 USD，`M`） | `[10.2, 10.5, ...]` |

* **完整响应样例 (JSON)**：
```json
{
  "aum": 58742897,
  "deployed": 41238912,
  "available": 17503979,
  "pnl_today": 238764,
  "pnl_7d": 1842517,
  "pnl_total": 12463981,
  "cumulative_pnl_chart": {
    "dates": ["05-20", "05-21", "05-22", "05-23", "05-24", "05-25", "05-26", "05-27"],
    "values": [10.2, 10.5, 10.9, 11.2, 11.6, 12.0, 12.2, 12.46]
  }
}
```

---

## 三、 WebSocket 实时推送协议

对于高频、低延迟的动态展示数据，前端基于 WebSocket 协议进行持久订阅。

* **接口路径**：`/ws`
* **协议类型**：`ws` 或 `wss`（取决于 TLS 启用状态）
* **连接行为**：
  * 连接建立后，前端不需要向后端发送任何订阅指令（无状态被动接收）。
  * 后端服务应将各类事件包装为特定 JSON 格式，通过该连接广播推送至前端。
  * 前端具有退避重连保护（最多尝试 10 次，每次间隔逐级递增，最大 10 秒）。

### 1. 数据推送格式协议

所有推送的消息都必须具有统一的顶级信封格式：
```json
{
  "type": "消息类型",
  "data": { ... 消息负载 ... }
}
```

具体支持的三个核心消息类型如下：

#### 🚀 协议 A：实时控制台日志 (Type: `log`)
当机器人微服务输出系统日志时，后端应实时捕获并打包推送，这将在前端控制台终端中瞬间渲染追加。
* **`type`** 字段值：`"log"`
* **`data` 字段结构**：
  * `time`: 字符串，格式 `HH:MM:SS` (如 `"14:35:22"`)
  * `level`: 字符串，可选 `"info"`, `"warn"`, `"danger"`, `"success"`，分别渲染不同的彩色发光标牌。
  * `module`: 字符串，模块标识，如 `"scanner"`, `"risk"`, `"execution"`, `"watchdog"`, `"simulation"`。
  * `message`: 字符串，具体的日志详细内容。

* **推送样例 (JSON)**：
```json
{
  "type": "log",
  "data": {
    "time": "14:35:22",
    "level": "success",
    "module": "execution",
    "message": "Add LP transaction successfully verified on Ethereum. Tx: 0x9a7db21a9c"
  }
}
```

#### 💻 协议 B：系统物理资源利用率 (Type: `system_resource`)
前端需要展示宿主 VPS 机器的负载，后端应以高频（如每 1s）的频率采集系统资源并推送，驱动前端 CPU、Memory、Disk 圆环仪表的动画。
* **`type`** 字段值：`"system_resource"`
* **`data` 字段结构**：
  * `cpu`: 浮点数，表示 CPU 利用率百分比 (`0.0` - `100.0`)
  * `mem`: 浮点数，表示内存利用率百分比 (`0.0` - `100.0`)
  * `net_speed`: 整数，表示网络传输瞬时速率，单位 Mbps

* **推送样例 (JSON)**：
```json
{
  "type": "system_resource",
  "data": {
    "cpu": 38.4,
    "mem": 61.2,
    "net_speed": 182
  }
}
```

#### 📊 协议 C：实战套利交易流水 (Type: `transaction`)
每当后端成功在链上执行滑点调整、再平衡或流转交易时，推送此事件。前端将在“实战执行流水”卡片顶部实时插入一条精美的流水横条，并渐变高亮。
* **`type`** 字段值：`"transaction"`
* **`data` 字段结构**：
  * `time`: 字符串，格式 `HH:MM:SS` (如 `"14:35:22"`)
  * `module`: 字符串，执行服务名，如 `"execution-service"`
  * `type`: 字符串，交易动作，如 `"Add LP"`, `"Rebalance"`, `"Remove LP"`, `"Approve"`
  * `chain`: 字符串，链名称，如 `"Ethereum"`, `"Solana"`, `"Arbitrum"`, `"BSC"`, `"Base"`
  * `hash`: 字符串，链上交易哈希（前端会自动在列表中渲染为蓝绿超链接）
  * `success_rate`: 整数，执行阈值成功分值或概率百分比

* **推送样例 (JSON)**：
```json
{
  "type": "transaction",
  "data": {
    "time": "14:35:22",
    "module": "execution-service",
    "type": "Rebalance",
    "chain": "Solana",
    "hash": "0x3bde9120ac92",
    "success_rate": 100
  }
}
```

---

### 2. Go 语言 WebSocket 广播器实现参考

这里提供一个使用 `github.com/gorilla/websocket` 库的高性能推送框架实现，供开发团队直接复用。它可以自动管理客户端连接，提供线程安全的广播信道：

```go
package main

import (
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// 升级 HTTP 为 Websocket 的配置
var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // 开发环境允许跨域
	},
}

// 客户端管理池
type ClientManager struct {
	clients    map[*websocket.Conn]bool
	broadcast  chan interface{}
	register   chan *websocket.Conn
	unregister chan *websocket.Conn
	mu         sync.Mutex
}

var manager = ClientManager{
	clients:    make(map[*websocket.Conn]bool),
	broadcast:  make(chan interface{}),
	register:   make(chan *websocket.Conn),
	unregister: make(chan *websocket.Conn),
}

func (m *ClientManager) Start() {
	for {
		select {
		case conn := <-m.register:
			m.mu.Lock()
			m.clients[conn] = true
			m.mu.Unlock()
			log.Println("➕ 新增客户端 WebSocket 连接")
		case conn := <-m.unregister:
			m.mu.Lock()
			if _, ok := m.clients[conn]; ok {
				delete(m.clients, conn)
				conn.Close()
				log.Println("➖ 客户端 WebSocket 断开")
			}
			m.mu.Unlock()
		case message := <-m.broadcast:
			m.mu.Lock()
			for conn := range m.clients {
				err := conn.WriteJSON(message)
				if err != nil {
					log.Printf("WebSocket 写入失败: %v", err)
					conn.Close()
					delete(m.clients, conn)
				}
			}
			m.mu.Unlock()
		}
	}
}

func wsHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("升级 WS 失败: %v", err)
		return
	}
	manager.register <- conn

	// 保持连接读取，用于检测连接断开
	go func() {
		defer func() {
			manager.unregister <- conn
		}()
		for {
			_, _, err := conn.ReadMessage()
			if err != nil {
				break
			}
		}
	}()
}

// 示例：在系统后台循环中广播系统负载和日志
func startBackgroundTelemetry() {
	go func() {
		for {
			time.Sleep(1 * time.Second)

			// 1. 构建系统资源负载
			sysMsg := map[string]interface{}{
				"type": "system_resource",
				"data": map[string]interface{}{
					"cpu":       32.5 + (time.Now().Unix()%5), // 模拟轻微波动
					"mem":       58.7,
					"net_speed": 182,
				},
			}
			manager.broadcast <- sysMsg

			// 2. 定期发送模拟日志（业务中应由日志钩子触发）
			if time.Now().Unix()%10 == 0 {
				logMsg := map[string]interface{}{
					"type": "log",
					"data": map[string]interface{}{
						"time":    time.Now().Format("15:04:05"),
						"level":   "info",
						"module":  "scanner",
						"message": "Alpha Scanner 扫描完成，监控中...",
					},
				}
				manager.broadcast <- logMsg
			}
		}
	}()
}
```

---

## 四、 生产部署建议 (Nginx 反向代理)

在生产环境中，强烈建议通过 Nginx 进行流量的反向代理和 TLS (HTTPS/WSS) 卸载。

以下是一份标准的 Nginx 配置片段：

```nginx
server {
    listen 443 ssl;
    server_name lpbot.example.com;

    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/lpbot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lpbot.example.com/privkey.pem;

    # 1. 静态前端托管 (直接定位至 /opt/lpbot/lp-bot-v3/web)
    location / {
        root /opt/lpbot/lp-bot-v3/web;
        index index.html;
        try_files $uri $uri/ =404;
    }

    # 2. 后端 RESTful API 代理（转发到 Go 服务的 8080 端口）
    location /api/ {
        proxy_pass http://127.0.0.1:8080/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 3. WebSocket 实时推送代理（必须显式配置 Upgrade 头部）
    location /ws {
        proxy_pass http://127.0.0.1:8080/ws;
        
        # 开启 Websocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        
        # 延长超时，避免连接被 Nginx 主动回收
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

有了这份高品质的技术文档，后端的工程师（或者是未来的我们）仅需要把这些 API 映射好，在交易流或者日志框架中加入简单的广播代码，即可无痛将前端全部点亮，享受极其生动高保真的暗黑科技监控体验！
