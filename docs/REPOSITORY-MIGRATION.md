# 仓库整理说明 / Repository migration

本仓库的 `main` 由原版 ESP32-S3 SkyGauge 工程整理为 **mi4-sky / MI4 Sky Gauge** 原生 Linux 项目。两者设备、构建工具和刷写目标不同，不可混刷。

整理基点为 `4b056c02ec055c95f17a74767f31b62a1183fc5f`。新提交以该提交为父提交，保留历史，不进行强制推送或历史擦除。需要查看旧 ESP32 工程时，可在 GitHub 历史中打开该提交，或在独立目录检出它；不要用旧 ESP32 固件刷写小米 4。

## 从当前分支移出的内容

- `build/` 与 `firmware/`：ESP32 编译缓存、固件二进制及发布产物，不是小米 4 Linux 镜像。
- `android_app/`、`model/`、`theme_store/`、`themes/`、`bootmedia/` 和 `bootmedia.bin`：原 ESP32 项目的配套应用、设计工程、商城、主题与启动素材，不属于本次 mi4-sky 源码交付。
- 原 `main/`、ESP-IDF 根构建配置、分区表、NVS 修复/启动素材校验脚本和旧 `tools/`：不再作为 mi4-sky 的构建入口；mi4-sky 依赖的 PID/事件核心及原始许可单独保留在 `vendor/obd_brz_gauge/`，来源锁定见 `metadata/dependencies.lock.json`。
- 原 ESP32 专用 README、使用/烧录文档和代理说明：替换为当前 Linux 应用、安装器、接口、硬件边界与二次开发文档，避免设备与烧录地址混淆。

这些内容只从新分支快照移出，旧提交中的文件仍可恢复。源码 GPL 及第三方原始版权说明保持有效，没有将上游工作冒充为本项目原创。

## 保留并新增的内容

应用、服务、17 个车型 JSON、原版 PID/事件核心、Windows 安装器源码、硬件配置/修改、当前测试，以及 494 份脱敏开发记录和历史测试。开发日志明确标为历史证据，不作为自动执行的修复指令。

大体积 Linux/lk2nd 工作源码归档放同版 Release，附 SHA256；它们不进入普通 Git 文件树。没有发布个人数据、旧整机镜像、原厂 aboot、厂商固件或未授权插画/视频。具体许可证与未完成事项见 THIRD-PARTY、KNOWN-ISSUES 和 Release 说明。

## English summary

The repository now targets Mi4 Linux rather than the original ESP32-S3 product. The migration is a normal child commit of `4b056c02ec055c95f17a74767f31b62a1183fc5f`; old files remain recoverable in Git history. ESP32 build outputs, companion apps, design/theme assets and device-specific build instructions are removed from the current snapshot. Required upstream PID/event sources and licenses remain under `vendor/`. Sanitized development history is retained. Large hardware source snapshots are Release assets, not Git blobs. This source publication is not a universally validated, complete flashing image.
