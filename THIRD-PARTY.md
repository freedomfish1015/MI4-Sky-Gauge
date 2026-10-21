# 第三方许可与开源边界

“项目开源”指有权发布的代码、配置和文档，不等于可以把手机中的所有二进制改为 GPL。

| 组件 | 来源/标识 | 处理 |
|---|---|---|
| mi4-sky 原创应用/服务/安装器/文档 | 本项目 | GPL-3.0-only；根目录 LICENSE 与 NOTICE |
| PID/事件核心、原车型包 | steveEcode/obd_brz_gauge，`976106c7bce8421ba7aa689a61d79dce4e8e16df` | vendor 中保留原文和 GPLv3；只搬运需要的源代码/测试闭包，不冒充原作者 |
| cJSON | DaveGamble/cJSON v1.7.19 | MIT；vendor/cjson/LICENSE。经国内镜像下载，以官方 GitHub API 的 Git blob SHA 校验 |
| Linux | bzy-080408/linux-msm8974，`cc180c1fa4d924977a8e0239162c81bb370e1b9b` 加本地硬件修改 | GPL-2.0 与各文件 SPDX；Release 附源码快照，仓库提供配置、差异和新增文件 |
| lk2nd/LK | 本地实际构建源码快照 | BSD/各文件原声明；没有可证实的本地 Git commit，不编造版本，以归档 SHA 标识 |
| 充电中文 glyph | generate_charge_glyphs.py，Noto Sans CJK SC | 保留字体版权/OFL说明；仓库不复制 Windows 字体 |
| Ubuntu 与 Python/SDL/Cairo/BlueZ | 发行版软件包 | 分别保留自己的许可证；metadata/rootfs-packages.json 是清单，不是软件包再授权 |
| Umeko基础集成脚本 | umeiko/umeko-Linux-phones，`f132936d733f998c6fdb38cfe7bf3d1e8e2a7ba7` | 本地快照根目录未见明确LICENSE；原样继承的USB配置/串口、auto_resize、modem提取脚本不收录，列为待核对外部依赖，不能由本项目改授GPL |
| 高通 GPU/无线/modem 固件、原厂 aboot | 厂商二进制 | 没有本项目可发布的完整源代码，不放进源仓库，也不标 GPL；设备持有人按许可自行取得 |
| 动漫插画、原视频、用户 logo/商标 | 外部素材 | 默认排除；贡献者须提供明确授权后才能另行加入，不因可见于手机而推定可再分发 |
| Google fastboot/Windows 驱动 | 原工具供应方 | 本源仓库不带二进制；可自行提供固定版本工具，须保留相应 NOTICE/许可 |

源代码树及硬件源码归档可作为开源交付；旧整机二进制不因本次整理而自动获得公开再分发许可。发布镜像前须核对其全部固件/素材/依赖许可及对应源代码义务。

本仓库中“最终设备树”来自已验证 boot 内 DTB 的文本导出，便于保留 OCV/WLED/音频描述，不是含个人分区的 boot 镜像。内核二进制前缀与本地构建 zImage 一致，但不宣称历史整机包可逐字节复现；见 docs/REPRODUCIBILITY.md。
