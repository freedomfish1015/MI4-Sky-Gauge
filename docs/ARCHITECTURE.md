# 架构与事实源

## 模块职责

| 模块 | 职责 | 不应做什么 |
|---|---|---|
| gauge_sdl + gauge_home | 原生分辨率、缓存、脏矩形、呈现与主布局 | 每帧载入资源或阻塞蓝牙 |
| gauge_settings/windows | 手势、滚动、数据窗口、配置 | 向任意shell传字符串 |
| gauge_compat + native/mi4_compat.c | 原PID/RPN/事件核心的单所有者FFI | 并发使用/释放同一个handle |
| gauge_compat_ble / obd_ble | 实际上游连接、协议发现和请求 | 将OTA特征当ELM、假定所有适配器都FFE1 |
| elm_bridge_* / elm_passive | 转发IPC、原始流、被动车况、背压 | 和Sky并行交错查询同一个ELM |
| services/motion | IIO加速度、QRTR LOC、轨迹/卫星诊断 | 用无效或过期坐标补假路线 |
| gauge_telemetry/tracks | LOG快照、曲线、轨迹页和行程联动 | 将暂停绘图当停止文件 |
| services/log_transfer | 按需AP/只读HTTP/CSV导出 | NAT、代理外网、任意目录下载 |
| services/power/charge | 外电状态、倒计时、正常关机、充电负载隔离 | 用suspend冒充poweroff |
| services/platform | 首启、绑定与精确版本引导检查 | 自动移植未知aboot |

## 数据契约

- 有效车况使用工程单位；None/缺失不是0；各信号独立过期。
- 图形刷新与传感器/OBD轮询互相独立，60FPS不能换算成60Hz ECU采样。
- 实时状态 `/run` 可丢失，必须跨重启恢复的蓝牙原状态保存在受保护的 `/var/lib/obd-charge`。
- 原始加速度、动态显示值和视觉平滑值分层保存。导出没有经标定的车辆坐标通道。
- LOG/轨迹属于用户隐私，源码和开发测试中只放合成样本，不带真实行程。

## 启动

原厂aboot → lk2nd（boot首512KiB）→ Linux/initramfs → systemd → 首启/BMS/硬件服务 → 静态图接管/仪表。多个阶段可能重新设置显示；当前不承诺全程无黑屏。overlay中的基础service可能仍叫boot movie，实际ExecStart由drop-in覆盖，**要看合并后的单位，不要只看主文件**。

原机已取消视频，旧启动视频模块保留只为原依赖/回退代码可读，不表示会播放。服务依赖的第三方rmtfs/BlueZ/PipeWire/QRTR/firmware必须由目标系统提供。

## 状态来源优先级

1. 当前源码、依赖锁和本次测试结果。
2. metadata中的已验证构建来源、硬件归档哈希。
3. 当前硬件只读检查和用户验收。
4. 开发日志/旧交接仅作历史证据。不能拿旧文件名中的CANDIDATE-NOT-FLASHED当成当前未刷结论，也不能复用已失配的旧回退哈希。
