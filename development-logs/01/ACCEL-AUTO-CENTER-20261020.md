# 加速度表：自动回中模式（用户明确选择）

用户在“固定车载保留持续 G”和“自动回中”之间选择 **自动回中**。这是对上一版含重力直读模式的替换，不再把持续倾斜投影保持在圆盘上。

实现：只使用现有 qcom-smgr-accel、50 Hz 采样，不启用陀螺仪、不积分、不手动归零、不等待静置校准。第一帧直接建立背景估计，输出中心点。每帧用时间常数 0.7 秒的低通背景估计扣除重力/慢偏移，再用每轴 0.025 G 的连续死区抑制抖动；约 1 G 的恒定偏移在约 3 秒后回零。传感器中断超过 1 秒后重新捕获背景，避免假冲击。

这不是车辆持续侧向 G 的精确测量：持续加速、持续转弯都会逐渐被背景估计吸收；快速倾斜过程中仍可能出现瞬态，单靠加速度计无法完美区分倾斜和位移加速。界面和 LOG 明确标注此限制。

主圆点、G 曲线、峰值与历史区域均使用同一动态输出；峰值及拖影是历史显示，不会因为回中立刻消失。当前圆点不额外插值，避免回中滞后。保留原始 `accel_ms2` / `accel_g` 在 LOG 用于核查，不把滤后数据冒充原始采样。

状态字段：`measurement_mode=accelerometer_autocenter`、`gyro_enabled=false`、`calibration_required=false`、`sustained_g_valid=false`、`dynamic_g`、`gravity_estimate_g`、`filter_tau_s`、`deadzone_g`。`total_g` 是动态三轴模长，`raw_total_g` 是原始含重力模长。

部署范围：

- `/usr/local/lib/obd-motion/mi4_accel_autocenter.py`：`1eb6a33ce7e0bcfb1f54f1c74dd6df583822becf32d479d7a4752e2b88a1f254`
- `/usr/local/lib/obd-motion/mi4_motiond.py`：`12e76398e40dcdbb6374ab86eae85f0e6024dd77461c6530f72a1c3d20355ebf`
- `/home/umeko/desktop-offline/gauge_motion.py`：`20cfb569df3bf1e82b477bbba2839a47b030195d4ef9fe6f8a57616c415d0a1e`
- `/home/umeko/desktop-offline/gauge_telemetry.py`：`41e03c689dc4ce02e8212d0537965cf3afbb93a2a323525a218005afaab6e497`
- 手机 `gauge_settings.py`：`8495a4852154fddbddfb64463e3162b73d2affcab031aeca577a9de96c0b347d`，仅定点修改提示文字，不包含 PC 待部署调试息屏改动。

备份：`/home/umeko/desktop-offline/backups/auto-center-before-knlcyupz`，由 `install_auto_center_20261020.py` 在核对旧 SHA 后创建。恢复时停 motion/kiosk，逐个恢复上述四个旧文件（新 helper 可保留不导入），再启动服务。不要覆盖其它 GNSS/BMS/boot 修复。

电脑 33 项测试通过，包括任意初始姿态立即居中、脉冲响应、恒定偏移衰减、倾斜后保持时回中、静止噪声死区、传感器恢复、LOG 和绘图输出一致，以及既有轨迹/记录联动。手机测试见 `auto-center-device-tests-live-20261020.log`。

手机测试必须将 `/usr/local/lib/obd-motion` 放在 `sys.path` 第一位：下载暂存目录中有较旧的 `mi4_motiond.py`，不能让它覆盖实际安装模块，否则会得到误导性的缺少函数错误。

没有修改 boot、内核、充电、电池、背光、触控、蓝牙或定位协议；仅重启 motion 与仪表服务，GPS 记录原有开关保持原样。
