# mi4-sky / MI4 Sky Gauge

把小米 4 LTE 改造成原生 Linux 触屏 OBD 仪表、G 值表与行程记录终端。

本仓库提供仪表应用、BLE/ELM327 转发、采样与导出服务、Windows 安装器源码、硬件修改源码/配置及脱敏开发历史。**应用/安装器原创部分采用 GPL-3.0；第三方代码保留自己的许可证。高通固件不是本项目可以重新开源的代码。**

## 先看这三个入口

- 想修改页面、数据和功能：[二次开发指南](docs/二次开发指南.md)。
- 想在电脑编译/测试：[构建说明](docs/BUILD.md)。
- 想上传到 GitHub：[发布指南](docs/GITHUB-PUBLISH.md)。

源码仓库：[freedomfish1015/MI4-Sky-Gauge](https://github.com/freedomfish1015/MI4-Sky-Gauge)。大体积源码附件见 [Releases](https://github.com/freedomfish1015/MI4-Sky-Gauge/releases)。本仓库由原 ESP32 工程整理为小米 4 Linux 项目，迁移范围与历史恢复方法见 [仓库整理说明](docs/REPOSITORY-MIGRATION.md)。

## 当前能力

- Ubuntu 24.04 ARMhf，原生 1920×1080 横屏显示；Cairo 静态缓存/脏矩形 + SDL2 KMSDRM/GLES2 显示，不需要桌面合成器。
- 左车速/右转速状态条、四角可自定义数据窗口、中央 G 值与方向峰值、平滑拖影和半透明区域。
- BLE 连接 ELM327 兼容 OBD，上游真实命令流转发给 SkyGauge；手机不是 ESP-NOW 从机。
- 17 个原版车型 JSON + 标准/模拟器入口；原版 PID 与事件核心的 Linux FFI。事件核心存在，不代表所有可见事件动作都已接入界面。
- 实时 LOG、GPS 路线、同一行程联动记录、GNSS 卫星类型诊断、RaceChrono CSV v3 兼容导出。
- 按需热点与单二维码配对 JSON、离线只读下载页，可用于后续小程序接入；没有已发布的微信小程序。
- 拔外电倒计时、保持开机/关机/充电模式；充电跨重启蓝牙状态恢复；精确版本自动 Fastboot 兔子修复。

**硬件验证范围仅 Mi4 LTE / JDI / Atmel mxt640t。** 不代表所有米4、米3或改装屏通用。仪表帧率不等于 ECU 数据采样率。GPS/北斗接收与参与定位必须看日志，不保证室内定位。

## 状态：系统稳定渠道，安装流程仍在测试

运行基线为用户已验收的 `2026.10.21-stable` / R2 构建。原厂 Fastboot 确实可能不报告 boot 分区大小；Windows 安装器仍会拒绝不充分的布局证明。**尚未完成另一台手机的清空重装和首启验收，不能宣传为通用一键刷机稳定版。**

开源整理版不带动漫插画、开机视频、用户商标图片、原厂 aboot、整机镜像、私有配对和历史轨迹。缺少图片时应用走现有无图回退，不是与原机视觉完全相同的新系统镜像。

## 快速验证（Ubuntu 24.04 / WSL）

```sh
sudo apt-get install build-essential python3-cairo python3-gi python3-gi-cairo gir1.2-pango-1.0 python3-pygame python3-bleak python3-dbus-fast python3-qrcode
python3 tools/build_native.py --target host
python3 tools/run_tests.py --full
```

Windows 仅编译/测试安装器：

```powershell
.\installer\test.ps1
.\installer\build.ps1
```

这些测试入口不刷写手机、不连接真实 OBD。不要把历史日志里的修复命令当成当前部署入口。先读 [安全说明](SECURITY.md) 与 [已知问题](docs/KNOWN-ISSUES.md)。

## 仓库结构

```text
app/                 仪表、页面、BLE 上游与转发客户端
services/            motion / power / charge / log_transfer / platform / startup
native/              PID/事件 FFI 与启动图显示 C 源码
vendor/              锁定版本的原版核心源码、测试向量、cJSON（保留许可证）
vehicles/catalog/    原版车型包
overlay/             systemd、udev、音频与启动配置；不含用户凭据
hardware/            内核配置/补丁/新增驱动、最终设备树、BMS 与引导相关源码
installer/           Windows C# 源码、构建与离线测试
tests/               当前回归与保留的历史测试
development-logs/    脱敏日志、旧交接、索引（历史证据，不是当前事实源）
docs/                二次开发、接口、构建、发布、问题与历史脉络
metadata/            来源/依赖/源码归档/版本与校验信息
```

大体积内核、lk2nd 源码归档放 GitHub Releases，与仓库源码同版关联。见 `metadata/hardware-sources.json`。本仓库不是全开源手机硬件或无专有固件系统的声明；具体边界见 [许可与来源](THIRD-PARTY.md)。
