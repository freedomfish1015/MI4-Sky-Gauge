# MI4 仪表与 obd-theme-store 功能兼容核对

## 后续纠正与进展

已找到用户另一个任务下载的 `[LOCAL-PATH]` 及干净源码 `[LOCAL-PATH]`，HEAD为976106c（2026-10-18）。因此下面“缺少新版固件源码”的结论仅是发现此目录前的历史，不再是当前阻碍。新版真实设备规则实现位于main/theme_engine/rules，主题ZIP sidecar支持事件；不能继续只以旧版app_event或旧版.bin局限推定功能。

已开始移植，当前状态详见同目录 `COMPAT-976106C-PHASE1-20261019.md`：17原包已进入手机设置页，用户确认正常；原规则/PID/ELM核心复用并通过主机和手机ARM测试。事件画面动作/通用主题导入尚待接入，全部功能对齐未完成。

日期：2026-10-19。状态：完成本地源码初步核对；未确认远端最新版本，未修改手机运行程序或固件。

## 版本与访问证据

- 用户目标仓库：https://github.com/steveEcode/obd-theme-store 。网页读取及已连接 GitHub API均返回404，不能据此断言仓库不存在或一定私有。
- 本地主题商店：`[LOCAL-PATH]`，工作区干净，HEAD `7ac481f`，提交日期2026-10-18，消息 `feat: update frontend theme and vehicle workflows`。git ls-remote因TLS握手失败，不能确认该HEAD等于远端最新。
- 本地旧固件源码：`[LOCAL-PATH]` HEAD `826a507`（2026-09-30）；另一份 `[LOCAL-PATH]` HEAD `1c8ebe9`（2026-09-29）。不能把它们称为10月最新固件。
- `[LOCAL-PATH]` 内build_tag为 `feature/theme-partition-system-104-9c3fa1b`、built为2026-08-28，属于本地历史元数据，不代表服务器现行最新。
- 主题商店后端 `backend/src/routes/firmware.ts` 的“最新固件”由数据库enabled+完整ESP32包+versionCode倒序选择，不等于Git提交日期。
- 本地部署配置中的 `[URL REDACTED] 本次只读GET返回502，未下载任何固件。

## 核对出的两种“事件”不能混淆

1. 固件 `main/app_obd_dsp/app_event.h/.c` 是跨任务队列（BLE连接、ESP-NOW、启动视频完成等），不是用户要配置的主题条件动作系统。
2. 主题商店 `frontend/src/lib/gaugeModel.ts`、`ruleEngine.ts` 与 `components/panels/EventRulesPanel.tsx` 定义可配置主题规则，才是主要兼容对象。

## 优先兼容功能清单（来自本地主题商店，不冒充远端最新）

| 子系统 | 已核对格式/行为 | 手机现状与差距 |
|---|---|---|
| 事件触发 | condition / change / timer | 当前固定SDL主题无通用事件解释器 |
| 条件 | >、>=、<、<=、==、!=；all/any；固定值或compareSource | 需兼容JSON而非只硬编码转速报警 |
| 稳定执行 | enabled、priority、debounceMs、hysteresis、瞬时事件持续时间 | 需独立单调时钟状态；断线/过期值不可当有效0 |
| 动作 | 按元素ID修改color、text、visible、asset | 需与主题元素及脏矩形刷新衔接，避免残影 |
| 动画 | fade / keyframes / strobe、颜色/图片渐变 | 编辑器明确注明当前.bin导出不包含事件动画；不能混称固件全部支持 |
| PID包 | `skygauge.vehicle/1`，id/rev/name/defaults/bus/signals | 目前只接受自定义id/name/pids+固定五数据的简化JSON，不能直接导入原格式 |
| 数据源 | req/raw/can三选一；hdr/rx/cea/expect；多帧；有效范围；失败切换 | 需完善ELM协议与请求调度/响应分发；并非复制PID号码即可 |
| 公式 | RPN字节、位字段、常量、算术、位运算、符号扩展、LUT | 需受限解释器，不允许eval/任意代码 |
| 调度与派生 | period_ms/rate、OBD默认继承、车型单位、档位比值、post处理 | 需兼容profile语义、时间戳、超时和无效数据 |
| 配置生命周期 | vehicle.install/activate、反馈issues、包管理 | 手机需导入/校验/选择/卸载/回退界面及真实协议确认 |
| 完整同等功能 | 主题/资源包、多页面、媒体、设备管理等 | 必须以锁定版本逐项验收，不能仅实现事件/PID就声称全部相同 |

### 本地PID校验器体现的边界

来源 `frontend/src/lib/vehicleProfile.ts`：包最大16KiB，最多48个有效信号、32个veh.*信号、96个源、16个CAN源；RPN 1–32条指令、栈深8；最多8个LUT、每表16项。请求模式包含01/09/21/22并有头地址与AT白名单。连续CAN监听不能混合请求源。数据采集仍应限定读取，不发送ECU写入、清码、执行器或安全解锁操作。真实车辆协议不明确时不得直接激活。

## 建议实施和验收顺序

1. 获取可访问的最新发布说明/源码/实际PID包、主题工程JSON或ZIP，锁定版本、commit及文件SHA；有GitHub文件下载需求时遵守用户国内镜像要求，不把私有源码/令牌交给未知代理。
2. 原格式PID包解析、白名单、受限RPN与可回放测试；覆盖标准包和BMW模拟器；遇不支持字段明确拒绝，不静默降级造成错数据。
3. 事件规则解释器：条件/比较/去抖/迟滞/定时/变化/优先级及动作；用上游规则测试作为对照，明确编辑器与固件不同的语义。
4. 与SDL原生1080p管线衔接，保留双线程、静态缓存、脏矩形、触摸设置、隐藏鼠标；事件关闭时正确恢复原绘制状态。
5. 配置管理UI、包导入及反馈；随后主题/页面/媒体兼容，列出硬件不可能直接等价项（如ESP-NOW）。
6. 手机端独立备份及可回退部署；实测帧率/CPU、USB断电20秒关机、插线开机、视频同步。不得覆盖已修复的电量OCV、WLED、触摸和声卡。

## 当前阻碍及用户所需提供

要声称“与最新固件一样”，至少需要锁定最新固件的真实版本及接口。请提供可访问的发布页/源码压缩包，或确认本地10月18日版本就是本次目标；并提供一个真实的原PID包及带事件规则的主题工程。仅ESP32固件.bin无法替代源码/包规范，也不能直接刷入ARM手机。

本次没有承诺已完成移植，没有对手机、路由器、ESP32或GitHub作写入操作。
