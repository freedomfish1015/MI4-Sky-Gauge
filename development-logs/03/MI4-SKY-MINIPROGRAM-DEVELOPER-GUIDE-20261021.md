# mi4-sky 功能与接口说明：微信小程序开发交接

版本：2026-10-21 / 当前已部署接口 v1。面向接手微信小程序的开发者或 AI。

同日后续说明：设置页标题已改为 `MI4 Sky Gauge`，头像改为用户提供的 Logo，不改变本文任何网络接口。设置源码最新版本见 `[LOCAL-PATH]`，SHA256 为 `2a4de0c6d491b5d62ec456bee2d1a40fda0f7fd6490c00c658ebf0813e96ed43`；本文第 13 节与先前 ZIP 中的 74406f... 为品牌更新前的冻结基线，不要用于覆盖当前手机。

本文可单独交接阅读。示例密码、token、坐标和文件名均为演示值，不是真实凭据。本文描述已部署后端，不授权修改手机引导、驱动或 ESP32 固件。

## 0. 接手先读：结论与边界

1. **mi4-sky 是小米 4 上运行的 Linux 触屏仪表**；SkyGauge 是另一块 ESP32 主表。产品名称今后统一使用 `mi4-sky`，不能把两台设备混淆。
2. 本轮小程序的目标只有：**小程序内扫一个二维码 → 用户确认加入 mi4-sky 热点 → 查看记录 → 下载文件 → 保存/分享**。不需要云服务器中转 LOG。
3. 手机端已部署单二维码、按需热点、只读 HTTP 文件接口、RaceChrono CSV v3 按需导出。
4. **小程序尚未发布，没有正式 AppID，未做微信真机全链路验证。**现有源码是草稿，不是已验收成品。不能声称微信扫一扫能直接打开尚未发布的小程序。
5. 用户选择 CSV v3 是为了电脑/第三方分析软件，**不是为了把文件直接导入 RaceChrono App**。不应承诺所有软件都兼容所有自定义通道。
6. 现有网络接口只读：没有远程开热点、删除 LOG、控制记录、调亮度、切 PID、操纵蓝牙、重启或升级接口。UI 中不能接入不存在的 API。
7. 手机端接口已经可用，优先适配它。任何新增后端、协议改动、云上传、设备控制或固件升级均应另行与用户确认。

## 1. 产品与已实现功能

### 1.1 设备概况

- 硬件：白色小米 4 LTE，原生 Ubuntu Linux ARMhf，非 Android/MIUI 容器。
- 用途：专用车载 OBD 仪表与记录终端，不以通用桌面作为主要操作界面。
- 显示：横屏原生 1920×1080 对应屏幕像素；内部 portrait buffer 为 1080×1920。不是 540p 放大图像。
- 渲染：Cairo 绘制，SDL/KMSDRM 显示，静态层缓存与增量刷新。历史已做接近 60 FPS 的优化，但不能把显示帧率当作 OBD 采样率。
- 操作：主要通过触屏滑动/点按，鼠标指针已隐藏。
- 当前数据传输页面与整体 UI 延续白色、冰蓝配色；不要为实现下载功能擅自重做仪表主题。

### 1.2 功能矩阵

| 功能 | mi4-sky 当前能力 | 小程序是否有现成网络接口 |
|---|---|---|
| 仪表显示 | 车速、转速、四角可配置数据窗口、中央加速度显示 | 无实时遥测 API |
| PID 数据包 | 标准 OBD-II、BMW 等已有车型包；仪表内滑动选择 | 无远程读取/切换 API |
| 蓝牙 OBD 直连 | 手机连接 BLE OBD 适配器，解析已有支持的 PID | 无远程蓝牙控制 API |
| 向 SkyGauge 转发 | mi4-sky 作为 BLE ELM327 中间转发端；台架联动已验证 | 与 LOG HTTP 接口独立 |
| G 值 | 加速度显示、自动回中、拖影与峰值区域等展示功能 | 可通过 LOG/CSV 读取历史记录 |
| GPS | 定位状态、行程记录、轨迹绘制、缩放/全览/历史切换 | 下载轨迹文件；无实时定位 API |
| 卫星诊断 | 行程保存 GNSS 元数据，区分观测、信号、参与定位等证据 | 下载 `.gnss.jsonl` |
| 实时 LOG 页面 | 仪表下滑进入曲线，冻结显示/返回；采样与显示逻辑分离 | 不提供 WebSocket 或实时曲线流 |
| 行程联动 | GPS 行程和车况 LOG 联动记录，记录中曲线仍可查看 | 无远程开始/停止记录 API |
| 亮度/电源 | 手机设置中调亮度、关机、充电模式；既有电源保护逻辑 | 不开放远程控制 |
| LOG 直传 | 设置中开启热点、一个配对二维码、15 分钟自动结束共享 | 已实现，本文重点 |
| CSV 分析导出 | 由原始 JSONL 按需生成 RaceChrono CSV v3 兼容文件 | 已实现 |
| ESP32 固件全部功能等价 | **未完成/不能宣称等价**；事件视觉动作曾按用户要求暂缓 | 不在本轮范围 |
| 在线音乐 | 不是当前小程序/仪表数据导出功能 | 无接口 |

注意：蓝牙 BLE ELM 转发与当前 Wi-Fi 下载是不同链路。历史 BLE 广播名可能仍为 `OBDII Mi4`；不能因为产品改名而擅自更改它、UUID 或已配对主表配置。旧 SkyGauge 从机模式已经移除，不应重新加入。

## 2. 小程序目标交互

建议用户流程：

```text
联网打开/加载小程序
  → 在 mi4-sky：设置 → LOG 数据传输 → 开启热点
  → 在小程序点“扫描仪表二维码”
  → 校验 JSON，提示用户即将连接 mi4-sky（此热点没有互联网）
  → 用户确认系统 Wi-Fi 连接
  → 等待 DHCP、重试读取文件列表
  → 按行程/类型浏览，优先下载 RaceChrono CSV v3
  → 保存到小程序本地，再由用户点击分享/导出
  → 手机端关闭共享，或 15 分钟自动关闭
```

首次启动小程序所需资源不能假定可从无互联网热点下载，因此应先联网打开小程序再切热点。Android/iOS 连接授权、权限、微信后台恢复以及无互联网 Wi-Fi 保持行为必须真机验证。

页面建议：连接状态区、扫码/重连/手动连接说明、文件类型筛选、记录列表、下载进度、已下载文件、分享/导出、过期提示。

所有连接/下载应由明确用户操作触发；扫描二维码不等于用户授权永久保存 Wi-Fi 密码或上传轨迹。

## 3. 一个二维码的精确定义

### 3.1 编码内容

二维码是一段 UTF-8 JSON 文本；不是 URL，不是 `WIFI:...` 字符串，不是微信小程序启动码，不含 AppID。

```json
{
  "kind": "skygauge-log",
  "v": 1,
  "ssid": "[REDACTED]",
  "password": "[REDACTED]",
  "host": "[IP-ADDRESS]",
  "port": 8787,
  "token": "[REDACTED]"
}
```

| 字段 | 类型 | v1 当前约定 |
|---|---|---|
| `kind` | string | 必须为 `skygauge-log`，保留历史协议名，不要改成产品名 |
| `v` | integer | 必须为 `1` |
| `ssid` | string | 新版为 `mi4-sky`；如需兼容旧版可接受 `SkyGauge-Mi4` |
| `password` | string | 当前为 12 位小写十六进制随机 Wi-Fi 密码，`^[0-9a-f]{12}$` |
| `host` | string | 当前固定 `[IP-ADDRESS]` |
| `port` | integer | 当前固定 `8787` |
| `token` | string | 当前为 32 位 URL-safe 字符，`^[A-Za-z0-9_-]{32}$` |

当前后端恰好发送以上 7 个字段，JSON 键顺序不应作为协议要求。草稿解析器采用严格字段白名单、输入长度 ≤1024 字符；遇到未知版本应提示升级，不进行猜测或执行。

### 3.2 生命周期与安全

- Wi-Fi 密码跨共享会话沿用；不要写死示例密码。
- `token` 每次开启共享重新生成；共享结束或服务重启后，旧 token/二维码不能继续使用。
- 900 秒共享计时从后端就绪开始，**不会因下载/访问自动续期**。
- 二维码没有 `expires` 字段，HTTP 也没有剩余时间接口。客户端不能显示声称精确同步的到期倒计时。
- token 是会话 bearer 凭据，放在 URL 路径中，而不是 Authorization header。
- 不要在控制台、埋点、截图、分享链接、云日志中输出密码或完整 token URL。
- 建议密码/token 只保存在页面/内存会话，不写长期 storage。下载文件本身需经用户同意保留。
- 从任意二维码接受外网 IP/URL 会形成风险；v1 应限制 host/port/SSID，只连接预期本地设备。

### 3.3 拼接地址

```text
origin = [URL REDACTED]
base   = origin + /s/<token>/
list   = base + api/files
file   = base + file/<kind>/<经过 encodeURIComponent 的 name>
```

保留 `base` 末尾 `/`。不要将 token 再 base64 编码，不要把 JSON 当链接打开，不要生成 `[URL REDACTED] 请求。

## 4. 热点和网络环境

| 项目 | 当前值/行为 |
|---|---|
| 热点 SSID | `mi4-sky` |
| 无线 | 2.4 GHz，channel 6，WPA2-PSK / CCMP |
| 服务端 IPv4 | `[IP-ADDRESS]/24` |
| DHCP 分配范围 | `[IP-ADDRESS]`–`[IP-ADDRESS]` |
| HTTP 端口 | `8787`，仅绑定 AP 地址，不是所有网卡 |
| 互联网/NAT | 不提供 |
| DNS/登录门户 | 不提供 captive portal，不劫持 DNS，不监听端口 80 |
| 开启方式 | 用户在 mi4-sky 设置页开启；不是开机默认开启 |
| 自动关闭 | 就绪后约 15 分钟；手动关闭也会停止服务 |
| Wi-Fi 冲突 | 手机端检测到已有 Wi-Fi 连接/IP/其他管理者时会拒绝抢占 |

不要把 `[URL REDACTED] 当下载入口，它缺少端口与 token。浏览器备用入口是**完整的** `[URL REDACTED]>/`。

建议使用微信原生请求/下载能力，不把浏览器 H5 的跨域行为等同于小程序原生网络能力。此后端没有跨域 CORS/OPTIONS 配置；任意云端 Web 页面跨域 fetch 并不是已支持方案。

微信局域网访问、Wi-Fi API、隐私声明、平台最低版本和正式版域名规则应以接手时官方文档与 Android/iOS 真机结果为准。本次官方微信文档网页访问失败，**不能把开发工具中“关闭域名校验后能请求”当成正式发布可用的证据**。

## 5. 已部署 HTTP 接口一览

以下路径均相对于 `[URL REDACTED]

| 方法 | 路径 | 返回 |
|---|---|---|
| GET / HEAD | `/s/<token>/api/files` | 文件目录 JSON |
| GET / HEAD | `/s/<token>/file/log/<name>` | 原始车况 JSONL 快照 |
| GET / HEAD | `/s/<token>/file/track/<name>` | GPS CSV / GPX / GNSS JSONL |
| GET / HEAD | `/s/<token>/file/racechrono/<name>` | 按需生成 RaceChrono CSV v3 |
| GET / HEAD | `/s/<token>/` | 备用离线 HTML 下载页 |
| GET / HEAD | `/s/<token>/app.js` | 备用页本地脚本，不是小程序代码 |

没有版本协商接口、登录接口、`/api/status`、`/health`、`/download-all`、上传、删除、ZIP 打包、长连接或远程控制接口。

### 5.1 通用请求规则

- HTTP/1.1。鉴权为路径 token；不需要账号密码，不需要 Cookie。
- HTTP Host 必须是 `[IP-ADDRESS]:8787`，正常按 origin 请求会自动正确生成。不要改成域名、自定义 Host 或反向代理外网域名。
- 不支持的 HTTP 方法（如 POST/OPTIONS）目前由标准处理器返回 501；不要设计 PUT/DELETE 调用。
- 不支持分页、查询过滤、`?format=csv` 或 JSON body 参数；筛选、排序和分组在小程序端做。
- 通用响应包含 `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`。
- 不存在 ETag、文件 SHA256 字段或下载完成 ACK API，不要伪造这些校验结果。

## 6. 文件目录 API

### 6.1 请求

```http
GET /s/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/api/files HTTP/1.1
Host: [IP-ADDRESS]:8787
```

返回 `200 application/json; charset=utf-8`。示例中的 3 项对应同一份原始 LOG 的两种表示和一份轨迹，不是 3 次行程：

```json
{
  "schema": "skygauge.log-transfer/1",
  "files": [
    {
      "kind": "log",
      "name": "telemetry-20261021T013117006421Z-56b9edfe.jsonl",
      "size": 7340032,
      "modified": "2026-10-21T01:39:14.000000+00:00",
      "recording": false,
      "url": "/s/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file/log/telemetry-20261021T013117006421Z-56b9edfe.jsonl"
    },
    {
      "kind": "racechrono",
      "name": "telemetry-20261021T013117006421Z-56b9edfe.racechrono.csv",
      "size": 0,
      "generated": true,
      "source_name": "telemetry-20261021T013117006421Z-56b9edfe.jsonl",
      "source_size": 7340032,
      "format": "racechrono-csv-v3",
      "modified": "2026-10-21T01:39:14.000000+00:00",
      "recording": false,
      "url": "/s/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file/racechrono/telemetry-20261021T013117006421Z-56b9edfe.racechrono.csv"
    },
    {
      "kind": "track",
      "name": "20261021T013000Z-123456789.csv",
      "size": 2048,
      "modified": "2026-10-21T01:39:15+00:00",
      "recording": false,
      "url": "/s/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file/track/20261021T013000Z-123456789.csv"
    }
  ]
}
```

### 6.2 字段表

| 字段 | 类型 | 含义 |
|---|---|---|
| `schema` | string | 当前固定 `skygauge.log-transfer/1`；不是产品显示名 |
| `files` | array | 最多 1000 项；没有分页/total 字段 |
| `kind` | string | `log`、`track`、`racechrono` |
| `name` | string | 白名单文件名，不包含磁盘目录 |
| `size` | integer | 物理文件的目录扫描大小；虚拟 CSV 固定 0，详见下文 |
| `modified` | string | 文件 mtime 的 ISO8601 UTC；不是行程开始时间 |
| `recording` | boolean | 对轨迹/CSV 可指示当前关联行程记录中；不是全局运行状态 |
| `url` | string | 带本次 token 的相对下载路径，无外网绝对地址 |
| `generated` | boolean，可缺失 | `true` 表示虚拟按需导出项，不是“已经生成过” |
| `source_name` | string，仅虚拟项 | 对应原始 JSONL 文件名 |
| `source_size` | integer，仅虚拟项 | 原始源文件大小，**不是 CSV 输出大小估算** |
| `format` | string，仅虚拟项 | 当前 `racechrono-csv-v3` |

客户端应接受未来新增可忽略字段，对未知 kind 可隐藏并提示升级；不要因未知文件项导致整个列表崩溃。

### 6.3 特别重要的目录语义

- `generated=true,size=0` 应显示“按需生成 CSV”，**不能显示为空文件并禁用下载**。
- 普通文件 `size` 可能比实际下载 Content-Length 大：目录之后仍可能写入，或完整行快照截去了半行。以本次响应为准。
- 文件按 `modified` 降序排列；时间相同的项不要依赖稳定位置判断类型。
- 文件数包括一个 JSONL 和由它派生的 CSV，也包括同一轨迹的多个格式；不等于行程数。
- `kind=log` 的 `recording` 当前通常为 false，即使源 JSONL 仍可追加。**它不代表该 LOG 已绝对封存**。
- CSV/轨迹标记为 recording 时前端应禁用导出；无论目录显示什么，下载返回 409 都必须处理。
- 目录不包含文件内容、GPS 点数、圈数、统计数据、设备电量或完整行程 ID。不能从这个 API 假装读取这些信息。

## 7. 下载接口与 HTTP 状态

### 7.1 文件名白名单

| kind | 文件名正则 |
|---|---|
| `log` | `^telemetry-[A-Za-z0-9-]+\.jsonl$` |
| `racechrono` | `^telemetry-[A-Za-z0-9-]+\.racechrono\.csv$` |
| `track` | `^\d{8}T\d{6}Z-\d+\.(csv|gpx|gnss\.jsonl)$` |

文件名总长不超过 160，禁止 `..`、`/`、`\`。客户端应自己校验 kind/name，基于扫码得到并校验的 origin/token 构造地址。若使用返回的 url，必须验证仍属于本次 token 和本地 origin，不跟随任意远程地址。

### 7.2 成功响应

普通文件响应为 `application/octet-stream`，CSV 导出为 `text/csv; charset=utf-8`。

```http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=utf-8
Content-Length: 528538
Content-Disposition: attachment; filename*=UTF-8''telemetry-20261021T013117006421Z-56b9edfe.racechrono.csv
Accept-Ranges: bytes
X-Mi4-Sky-Format: racechrono-csv-v3
Cache-Control: no-store
```

`X-Mi4-Sky-Format` 仅 CSV 导出响应提供。保存文件名优先使用已校验目录项的 name，不要依赖微信自动从 Content-Disposition 命名。

HEAD 返回相应响应头而无正文。**对虚拟 CSV，HEAD 也需要先转换文件**，并非免费查询，首版不建议 HEAD 后再 GET。

### 7.3 Range

支持单段 `Range: bytes=0-1023`、`bytes=1024-`、`bytes=-1024`，成功为 206；不支持多段范围。非法/不可满足为 416，含 `Content-Range: bytes */<size>`。

首版建议串行完整下载，不实现跨会话断点续传。原因：源 LOG 可能追加/轮转，CSV 每次重新生成，token 会过期，且没有 ETag/稳定快照 ID；不能把两次不同结果简单拼接。

### 7.4 状态码与前端行为

| 状态/错误 | 当前含义 | 建议处理 |
|---|---|---|
| 200 | 成功目录/文件 | 校验 schema 或保存正确文件 |
| 206 | 单段下载成功 | 仅实现 Range 时按 Content-Range 处理 |
| 403 | token 缺失/错误，或 Host 不被接受 | 先检查地址/Host；否则重新开启共享并扫码 |
| 404 | 路径/文件名不支持、源文件不存在/已轮转、超上限等 | 刷新目录，不无限重试旧项 |
| 409 | 轨迹/关联 CSV 所属行程仍在记录 | 提示到仪表结束行程后重试；小程序不能代停 |
| 416 | Range 不合法或越界 | 重新完整下载 |
| 422 | 没有完整可转换数据、schema 不支持、转换超限等 | 保留原始 LOG；可下载原始文件诊断 |
| 429 | 另一个 CSV 导出占用转换槽 | 短暂退避后由用户重试；没有 Retry-After header |
| 501 | 不支持的方法 | 修正为 GET/HEAD，不尝试删除/上传 |
| 网络超时/断开 | 热点关闭/过期、设备掉电、离开局域网或权限问题 | 明确提示重连/重新扫码；不一定会返回 403 |

错误正文通常是 `text/plain; charset=utf-8`，不是统一 JSON 错误对象。`wx.downloadFile` 的 success 回调不等于 HTTP 200：必须检查 statusCode，否则可能把错误说明保存为 CSV。

### 7.5 限额与重试建议

- 源文件上限：128 MiB（134217728 字节）。超限文件不在支持范围内。
- CSV 输出上限同为 128 MiB；单条 JSONL 记录最多 256 KiB；转换内部限时约 30 秒。
- 总 HTTP 处理并发槽为 4；超额连接可能直接断开，**不是必定返回 429**。
- CSV 转换槽为 1；导出/传输结束前其他 CSV 请求可返回 429。
- 服务端连接 timeout 为 20 秒；客户端建议目录约 10 秒、下载不低于 60 秒并控制整体超时。较长时间没有响应时给出“正在转换”，不要显示假下载百分比。
- 连接 Wi-Fi 回调成功后 DHCP 可能未完成，可有限重试目录（例如每次间隔约 1 秒，最多 6 次）；不要反复调用扫码。
- 保持下载队列串行、前台进行，提供取消。切后台、热点关闭、会话结束都要能恢复到可重试状态。
- 本次共享不因正在下载而延期；距离 15 分钟边界的大文件可能中断。

## 8. RaceChrono CSV v3 数据定义

### 8.1 格式目的

本功能输出“RaceChrono CSV v3 结构兼容”的分析数据，不是 `.rcz`，也不是 RaceChrono App 的通用导入协议。用户已明确选定给电脑或第三方分析软件使用。RaceChrono 作者对 CSV v3 用途的说明见文末来源。

导出由后端读取原始 JSONL，在低优先级下载服务中转换为匿名临时文件，再提供下载；**不改动原始记录、不在仪表渲染线程里做转换**。

### 8.2 文件结构

UTF-8，无 BOM；逗号分隔，必要时 CSV 标准双引号转义；LF 换行。当前结构为：

1. 真实创建者声明：mi4-sky，兼容 RaceChrono CSV v3，不冒充官方生成。
2. `Format,3`。
3. Session title。
4. Session type：`Data logging`。
5. Track name（目前空）。
6. Driver name（目前空）。
7. Created（`dd/mm/YYYY,HH:MM`，UTC）。
8. Note（含数据含义、采样和模拟标记说明）。
9. 空行。
10. 通道名行。
11. 单位行。
12. 数据来源行。
13. 起为数据行。

解析器最好通过首字段 `timestamp` 定位表头，不只固定跳过行数；支持 CSV 引号，不可用单纯字符串 split(',') 解析所有内容。

### 8.3 当前全部通道，顺序与单位

下表序号为 **1 起始的文件列号**；两个 speed 名称相同，必须结合 source 识别。

| 列 | 通道名 | 单位 | source | 真实含义 |
|---|---|---|---|---|
| 1 | timestamp | unix time | 空 | 原 sample.utc 转为 UTC Unix 秒 |
| 2 | fragment_id | 空 | 空 | 本文件片段号，从 0 开始 |
| 3 | elapsed_time | s | 空 | 片段内相对单调时间 |
| 4 | accuracy | m | 100: gps | GPS 原位置精度 |
[LOCATION-BEARING LINE REMOVED]
[LOCATION-BEARING LINE REMOVED]
| 7 | speed | m/s | 100: gps | GPS 原速度 |
| 8 | speed | m/s | 300: obd | OBD km/h 除以 3.6 |
| 9 | rpm | rpm | 300: obd | OBD 转速 |
| 10 | throttle_pos | % | 300: obd | 节气门开度，不是油门踏板 |
| 11 | gear | 空 | 300: obd | 实际记录到的档位 |
| 12 | coolant_temp | .C | 300: obd | 冷却液温度 |
| 13 | engine_oil_temp | .C | 300: obd | 机油温度 |
| 14 | battery_voltage | V | 300: obd | OBD 适配器/车辆电压，不是小米手机电池电压 |
| 15 | engine_load | % | 300: obd | 发动机负荷 |
| 16 | x_acc | G | 200: acc | 原始传感器 X 轴 |
| 17 | y_acc | G | 200: acc | 原始传感器 Y 轴 |
| 18 | z_acc | G | 200: acc | 原始传感器 Z 轴 |
| 19 | acceleration_1 | G | 201: data | 过滤后显示 X 轴 G |
| 20 | acceleration_2 | G | 201: data | 过滤后显示 Y 轴 G |
| 21 | digital_1 | 空 | 201: data | 1=源记录明确标为台架模拟器；0=未标记 |

### 8.4 不可误解的数据语义

- 缺失、非有限数值留空，不补零；零值本身则保留。
- GPS 必须 fix=true 且经纬度有效，才输出这些 GPS 列。没有 fix 不等于坐标为 0,0。
- 不生成圈号、圈速、距离、刹车踏板或车辆标定横纵 G；这些列在当前导出中不存在。
- `x/y/z_acc` 来自原记录 accel_g，可能包含重力；`acceleration_1/2` 是过滤后的显示轴，不是车辆校准的 lateral_acc/longitudinal_acc，也不能保证表示持续弯道的完整稳态 G。
- 不能因为原始/过滤加速度不同就将其平均、任意旋转或改写为车辆横纵 G。可在分析界面如实区分两类。
- 原始采样约 10 Hz，但 OBD 原值可能更慢、重复；GPS也可能更慢。没有为了曲线好看而插值为虚构新读数。
- `digital_1=0` 仅表示没有模拟标记，**不是实车真实性认证**。
- 时间回退会增加 fragment 并重设 elapsed_time 起点，保留真实 UTC；一个文件内可能出现多个片段，不要强行按行号制造 0.1 秒时间轴。
- 当前 CSV 只转换一份 JSONL，不会自动把被轮转拆开的多个 LOG、额外 GPS 轨迹或多次行程合并，也不补入该 JSONL 没有记录的卫星/高度字段。

## 9. 原始 LOG、轨迹与行程关联

这一节适合小程序后续增加本地预览；首版只需下载原文件，不要求在手机上解析大文件。

### 9.1 车况 JSONL

文件名：`telemetry-<创建时UTC>-<随机短ID>.jsonl`。第一行通常为 header，后续为 sample，每行一个 JSON 对象。

header 主要字段：

| 字段 | 含义 |
|---|---|
| type | `header` |
| schema | `mi4.telemetry/1` |
| session | 记录器会话标识，不等于 GPS 行程 ID |
| trip | 关联 GPS 行程 basename，或 null |
| gps_track | 有关联时为 `<trip>.csv`，否则 null |
| sample_hz | 当前标称 10 |
| units | 通道单位，如 speed=km/h、gx/gy=G |
| missing | 当前 `null` |
| channel_meaning / g_coordinates / note | 数据语义说明，需要保留 |

sample 主要字段：

| 字段 | 含义 |
|---|---|
| type | `sample` |
| utc | 记录端 ISO8601 UTC；不是 GPS 接收机时间的替代证明 |
| t | 单调时钟秒，仅适合本次启动内相对时间 |
| trip | 行程 basename 或 null |
| channels | rpm/speed/throttle/gear/coolant/oil/gx/gy 等快照，值可 null |
| values / signals | 原数据源值及有名称信号；CSV 的 OBD 列从 signals 读取，不用 UI 缺省值冒充 |
[LOCATION-BEARING LINE REMOVED]
| acceleration | 模式、是否含重力、原始加速度、过滤/动态量及有效性元数据 |
| connection | 面向人的连接状态字符串，不要当稳定枚举协议解析 |
| context | 地址、车型、模式、sky_forward、simulated_source 等上下文；版本间可增字段 |

记录器现有默认轮转约 5 MiB/文件、保留约 8 个 LOG 文件，GPS 文件另行保存。**下载不删除原文件，但不代表原记录永远不会被记录器轮转清理**。列表读完后文件仍可能消失，必须处理 404。

### 9.2 GPS 原文件

同一 GPS 行程通常保存：

```text
<trip>.csv
<trip>.gpx
<trip>.gnss.jsonl
```

`trip` 例如 `20261021T013000Z-123456789`，包含启动时 UTC 和单调时钟生成的防冲突后缀。它不是设备序列号。

当前轨迹 CSV 表头：

```csv
[LOCATION-BEARING LINE REMOVED]
```

- `utc` 是有效定位时间；`speed_ms` 为 m/s；经纬度为原始 GNSS 坐标值，不在导出中做中国地图偏移转换。
- 旧历史记录的表头可能更短，必须按列名解析，不硬编码新列总数。
- `observed_systems` 等字段可能是 CSV 单元格中的 JSON 文本，要先 CSV 解码再 JSON.parse。
[LOCATION-BEARING LINE REMOVED]
- 无定位时 CSV/GPX 可能只有表头/空轨迹；这不是生成虚假路线的理由。

### 9.3 GNSS 诊断与北斗证据

`.gnss.jsonl` 保存卫星观测元数据，即便没有有效定位也尽量记录，便于解释“为什么这次没有轨迹”。当前 header 为 `event=header,schema=2`；卫星事件带 `event=satellites`、`recorded_utc`、`monotonic`、`status` 等。

不得把“观测到某星座”“某卫星有信号”“参与本次解算”混为一谈。`used_systems_complete`、`sv_report_available` 需要结合解释：未提供报告是未知，不是北斗为 0，也不证明硬件开关已经启用。当前小程序 API 不具备“开启北斗”能力。

### 9.4 推荐行程分组原则

- 同 basename 的 GPS CSV/GPX/GNSS 文件可以组合为一组。
- 目录 API 不直接给 raw LOG 的 trip；要精确关联，读取已下载 JSONL header 的 `trip/gps_track`。不要仅按文件名时间相近就合并。
- 虚拟 CSV 用 `source_name` 找到对应 JSONL。
- 一次行程可能对应多个轮转 LOG；当前后端不自动输出行程 ZIP 或合并后的单个 CSV。
- 若首版不解析 LOG，就提供按时间/类型列表，不声称已经得到准确行程总数或完整行程包。

## 10. 小程序实现建议与示例

下面是按当前后端设计的流程示例，不是已通过微信真机验收的 SDK。接手者应在真实 AppID 下核对微信文档、隐私声明、授权和平台差异。

### 10.1 扫码与联网

```javascript
// 示意：先处理隐私同意和用户主动点击，再执行。
wx.scanCode({
  onlyFromCamera: true,
  scanType: ['qrCode'],
  success(res) {
    // 1. JSON.parse(res.result)，按第 3 节严格校验。
    // 2. 弹窗说明热点无互联网，用户确认后才连接。
    // 3. wx.startWifi → wx.connectWifi({ SSID, password })。
    // 4. 回调后有限重试 GET /s/<token>/api/files，成功才算业务连接完成。
  }
});
```

如果自动连接受权限/系统限制：显示从本次二维码获取的 SSID，提供经用户点击才复制密码的选项，引导手动加入系统 Wi-Fi，返回后刷新列表。**不要让用户每次失败都重新扫描或强制重新配网**。

如果 403 或共享会话已失效，才要求回仪表开启共享并重新扫码。

### 10.2 构造下载地址

```javascript
const origin = '[URL REDACTED]';
// token 必须先满足 /^[A-Za-z0-9_-]{32}$/。
const base = `${origin}/s/${token}/`;
// kind/name 必须先通过第 7 节的白名单。
const url = `${base}file/${file.kind}/${encodeURIComponent(file.name)}`;
```

### 10.3 下载与持久化

```javascript
const task = wx.downloadFile({
  url,
  timeout: 120000,
  success(res) {
    if (res.statusCode !== 200) {
      // 按状态码显示错误，必要时删除这份错误正文临时文件。
      return;
    }
    // res.tempFilePath 只是临时文件，不等于永久保存。
    // 再由 FileSystemManager 保存到 wx.env.USER_DATA_PATH 下。
    // 使用独立目录或冲突处理，不能静默覆盖用户先前下载的版本。
  },
  fail() {
    // 显示连接/超时提示，不输出包含 token 的请求对象。
  }
});
task.onProgressUpdate(info => {
  // 转换阶段可能暂时没有进度事件，显示“正在准备 CSV”。
  // 下载阶段才使用真实 info.progress。
});
```

必须显示“已保存到小程序”和“已导出到系统/分享”的差异。提供用户主动点击的分享/导出按钮，按平台能力使用如 `wx.shareFileMessage`，不假定 CSV 可以用文档查看器直接预览。

本地存储满、微信文件配额、文件被清理、用户取消分享都应可恢复。建议提供仅删除**已下载的本地副本**的清理界面，明确不删除仪表上的原文件。此处不意味着已存在设备端删除接口。

### 10.4 状态机建议

```text
未扫码 → 扫码校验 → 等待用户确认 → 正在连接 Wi-Fi
  → 等待局域网服务 → 已连接/文件列表
  → 正在准备导出 → 正在下载 → 本地已保存 → 用户分享

分支：取消 / 无权限 / Wi-Fi 未连接 / 服务超时 / 会话失效 / 行程记录中 / 本地保存失败
```

每次重新扫码成功后，清理旧 session 的 URL、队列和设备列表缓存；不要把已保存文件删掉。页面退出时取消未完成下载、丢弃内存中的 token/password。不要自动操作用户原来 Wi-Fi 的断开/恢复而不说明。

## 11. 安全、隐私与不能做的事

- LOG 和 GPS 轨迹包含个人位置、驾驶行为、时间和蓝牙地址；默认只做局域网传输与本地保存。
- 默认不接入云同步、第三方分析 SDK、位置埋点或公开分享链接。增加这些功能必须另行取得用户同意。
- 不索要 mi4-sky 的 Linux sudo 密码、AppSecret、微信账号密码；小程序协议不需要它们。
- HTTP 不是端到端 TLS。WPA2 和临时 token 降低暴露面，但不能宣称银行级/不可窃听安全，也不能防范拍摄二维码的旁观者。
- 后端仅按文件白名单导出，不能读取系统配置、Wi-Fi 配置、任意磁盘路径或原始分区。
- 不把后台内部 `state.json` 当公开 HTTP API；它含本地状态和凭据，只供设备 UI 读取。
- 不向 ESP32 刷 mi4-sky 文件，也不把 ESP32 bin/分区表写到手机。
- 不为做小程序擅自刷 boot、aboot、logo、内核、DTB、modem 或更换硬件驱动。
- 不再启用此前被用户取消的 SkyGauge 从机模式，不擅自增加事件换图/闪烁/主题切换。

## 12. 验收清单

### 12.1 已有验证证据

- 手机单二维码后台和本地配对 PNG 已部署；二维码生成尺寸曾为 57×57 模块画布，仪表端整数倍绘制。
- 已做原生 1920×1080 设置页离屏渲染检查，无需改变仪表分辨率。
- PC 上 32 项测试通过，覆盖目录与文件安全、UI 隔离、单 QR 协议、CSV 数值/缺失/模拟标记、Range/HEAD、记录中拒绝、单转换槽。
- 手机通过本地 HTTP 端到端导出：**4,772 行、528,538 字节、3.130 秒**；源文件转换前后 SHA256 一致。
- 最近部署后仪表与运动服务为 active，仪表 NRestarts=0；这不是本次文档编写时重新测得的持续运行承诺。
- 小程序真机联调、正式发布、第三方分析软件导入仍待验收。

### 12.2 小程序开发者必须实测

1. Android 与 iOS，合法二维码一次扫码成功；非本设备 QR、未知版本、非法 IP/token 均拒绝。
2. 用户取消扫码、拒绝 Wi-Fi/隐私权限不死循环，手动连接后刷新可恢复。
3. 无互联网热点能保持局域网请求，不错误要求购买云服务/公网域名来替代尚未验证的本地链路。
4. 读到 `schema` 和三个 kind；`generated=true,size=0` 可正常导出。
5. CSV 准备阶段、下载进度、取消、存储失败、重新下载/同名冲突处理正确。
6. 403/404/409/416/422/429、网络断开和服务自动关闭有清晰反馈。
7. 同行程 CSV/GPX/GNSS 与 raw/派生 CSV 分组不重复算行程；无法确定时不强行合并。
8. 下载内容以 UTF-8/原始字节保存，不增加 BOM、不重新字符串转码破坏文件。
9. 真实用户点击后才能分享/导出；本地副本在下一次打开时仍能找到或明确提示已清理。
10. CSV 在目标电脑分析软件中验证双 speed 源、G 坐标语义、单位、缺失数据与模拟标记。
11. 查看控制台、埋点和错误上报，确认不泄露 PSK/token/完整 GPS 内容。
12. 完成真实 AppID 的真机/体验版验证，不用游客模式或跳过校验的模拟器结果冒充正式完成。

## 13. 实际源码、样例与运维定位

### 13.1 PC 主目录

```text
[LOCAL-PATH]
```

| 文件/目录 | 用途 |
|---|---|
| `miniprogram/` | 可参考的未发布草稿；project.config.json 仍为 touristappid，需正式 AppID 与真机完善 |
| `miniprogram/utils/protocol.js` | QR 校验与路径白名单示例 |
| `log_hotspot.py` | 配对 JSON、热点、DHCP、共享生命周期 |
| `log_download.py` | 当前实际 HTTP 契约与错误处理 |
| `racechrono_export.py` | 21 列导出定义和转换语义 |
| `gauge_log_transfer.py` | 仪表上的单二维码页面 |
| `gauge_settings.py` | 已部署设置页的定点修改基线 |
| `test_*.py` | 已有自动测试 |
| `mi4-sky-racechrono-validation.csv` | 实机生成的约 20 行样例，含台架模拟数据标记；不是完整 4,772 行文件 |
| `mi4-sky-transfer-preview.png` | 使用演示凭据渲染的页面预览；其 QR 不是用户当前会话 |
| `MI4-SKY-LOG-HANDOFF-20261021.md` | 安装、校验与回退补充文档 |
| `pairing-install.log` / `racechrono-install.log` | 部署验证证据，不含当前二维码密钥 |

设备端：

```text
/home/umeko/desktop-offline/gauge_log_transfer.py
/home/umeko/desktop-offline/gauge_settings.py
/usr/local/lib/obd-log-transfer/
/etc/systemd/system/obd-log-transfer.service
/etc/systemd/system/obd-log-download.service
```

小程序只需要 HTTP 接口，不需要串口/root 访问。下列命令仅供另行获授权的设备维护者诊断，不是可从小程序调用的功能：

```sh
systemctl is-active obd-log-transfer.service obd-log-download.service
journalctl -u obd-log-transfer.service -u obd-log-download.service -n 60 --no-pager
```

不要将 `/run/obd-log-transfer/session.json`、config.json、PSK 或 token 整体打印并交给第三方。

### 13.2 当前部署关键 hash

```text
log_hotspot.py       295bf44c1139d3de73357154a4d63ecb0b5cdc81ba38962c76f20a749d2952e5
log_download.py      d163a70b19a1753d9e0d6cd57b52d5670af89e2249c925e7d92dcd28e470cfbc
racechrono_export.py 5df16260ec28ea5f5e20ce47dd5526a2e41472b04320ba863b114d6b53ff8e64
gauge_log_transfer.py a83b6f0ab4d39b91633c62ba63e66b89899b52710229d9589a7a4c080afa3f4a
gauge_settings.py    74406f4bce2646cb30f1a2a128fc9fe05a0594ff54520923ad99ce4f4c815664
```

以实际已部署代码与最近校验为准。若其他 AI 后续改动了文件，先比较版本，不要强行绕过安装器 hash 检查。

**特别警告：**PC 工程根目录的 gauge_sdl.py / gauge_settings.py 含其他未部署的调试待机工作，不能为这个小程序整体覆盖到手机。只做小程序不需要修改它们。

## 14. 给接手 AI 的任务说明，可直接复制

> 请基于本文的已部署 v1 契约开发 mi4-sky 微信小程序。先读取本地 miniprogram 草稿和 log_download.py / log_hotspot.py / racechrono_export.py。实现小程序内一次扫码、用户确认连接热点、列表筛选、RaceChrono CSV v3 优先下载、原始 LOG/轨迹下载、持久保存和用户主动分享。正确区分虚拟导出、记录中、会话过期、缺失数据、GPS 无定位与台架模拟标记。用真实 AppID 做 Android/iOS 真机与体验版测试；缺少 AppID 时报告待办，不能宣称已发布或全链路通过。不要要求 AppSecret，不上传轨迹到云，不擅自修改设备端协议、引导、硬件修复或 ESP32 固件；不要调用本文不存在的接口。新增设备端能力请先列出需求与用户确认。

## 15. 外部参考与核对范围

- RaceChrono 作者对 CSV v3 导出用途的说明：[官方论坛]([URL REDACTED])。
- RaceChrono 通道/设备类型标识：[官方 identifiers]([URL REDACTED])。
- CSV v3 实际文件结构参考：[公开测试样例](https://github.com/ClassicMiniDIY/UltraLog/blob/main/exampleLogs/racechrono/session_massa_finalese_v3_excerpt.csv)。本文列定义以 mi4-sky 已部署转换器为准，不声称完全复制其他设备所有列。
- 微信 Wi-Fi 连接文档入口：[wx.connectWifi]([URL REDACTED])。
- 微信局域网能力入口：[局域网通信]([URL REDACTED])。后两页本次工具未能打开，接手者需自行核对当前内容和权限政策。

本文依据本地源码 hash、最近成功部署记录与已有实测数据编写；本次仅生成交接文档，未为写文档重启设备、开启热点、刷写分区或变更服务。
