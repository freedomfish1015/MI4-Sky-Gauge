# 隐藏 Sky Gauge 开机图上的 lk2nd 版本文字

## 状态：已写入、整分区读回通过，重启视觉验收通过

已执行正常重启，用户明确确认 **“文字消失，视频和仪表正常”**。系统USB串口恢复、uptime归零，kiosk PID523、motion PID563均active且NRestarts=0。启动后日志约58.8–59.3 FPS。详见 `hide-lk-footer-reboot-20261020.log`、`hide-lk-footer-postboot-20261020.log`。

这次验证为电脑发起的正常重启；未测试拔线完全关机后的冷启动或Fastboot菜单实机操作。下面“尚未重启”等描述为写入当时的历史状态。

照片中的两行文字为 `lk2nd-msm8974` 和 `22.0-next-4a1e26e4-20260419-dirty`，由第二阶段 lk2nd 主动画出，不属于 Sky Gauge 图片，也不是 Linux 日志。

在现有 `/root/mi4-lk2nd-lowbat/lk2nd/device/menu/menu.c` 中定位到 `display_default_image_on_screen()`：它会清除底部三行，画 BOARD 和 LK2ND_VERSION，再 flush。`display_fastboot_menu()` 为独立函数，保留不变。未重编或刷入该目录带低电量测试改动的整套产物。

## 最小修改

- 原始当前 lk2nd 前512KiB SHA256：`45a16cdeda912e255695b5491207b4fbb4740e28da3f11eb1d0d856e3d435767`。
- ARM 入口地址 `0x0f92d988`，对应 boot 分区偏移 **`0x2e188`**。
- 将第一条 `ldr r3,[pc,#204]`（`0xe59f30cc`）替换为 `bx lr`（`0xe12fff1e`），直接返回，不再清屏/画字。
- 同时更新第一阶段 Android boot header 的 SHA1 image ID（offset576，20字节有效摘要，其余12字节仍零）。
- 写入仅涉及两个原512字节扇区：`0x2e000`、`0x200`，没有重排任何镜像内容。
- 原版正常开机 ARM 函数确实画出照片里的两行内容；补丁版执行时不再调用 framebuffer 清屏/画字/flush，SP及保存寄存器保持正确。6项测试通过。
- Fastboot 菜单代码、BOARD/版本字符串、设备树版本信息、Fastboot版本查询均未更改。
- 前512KiB新 SHA256：`c575f86910f82bc2cd87097fd777cbe0bed6d46bae087e7d2f39ee64bc04d36d`。

## 实际写入与备份

安装器 `flash_lk2nd_hide_footer.py --write-hide-footer` 校验机型、块设备号、尺寸、旧32MiB全分区 SHA、前512KiB SHA、供电及 Sky Gauge aboot/logo SHA。

- 新鲜原boot备份：**`/home/umeko/desktop-offline/backups/hide-lk-footer-before-8i_dkxgq/boot.img`**，root目录0700、文件0600、fsync并读回。
- 目录同时含预期新前缀、before.json、success.json。
- 原boot SHA：`1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a`。
- 当前boot SHA：**`edf91d38f7cd87b5a59480ac5b0f00acb79a71aaa5f16577047959e47e4b035d`**。
- Linux完整尾部从偏移524288起逐字节未变，SHA256：`167f412425dbdace3703bbdf4d05aa956af8622f31c78ecb4a1af33126866c1e`。
- aboot仍 `362986d35fe58e55508615fc806483a4533e55f83fa9ab631ed1d7d9cb7c3f40`；logo仍 `47dbe469e9fcb84280f741161e1e76a67abe4b008d17f3f91bcea86fa7b173c5`。
- 日志 `hide-lk-footer-flash-20261020.log`。

未改变 Linux 内核、DTB、电量/充电保护、触控、背光、音频、仪表程序、GPS或蓝牙配置。写入后随后经真实重启及用户视觉确认不再显示文字。尚未验证此补丁下 Fastboot 的实机画面；仅保证对应代码与字符串没有改动。

## 回退

安装器异常时自动恢复同一两个原扇区并比较原boot全分区。若用户后续要求回退且Linux可运行，应先验证当前全分区仍为上述新 SHA，再从此备份只恢复上述两个512字节扇区；不要拿老32MiB镜像覆盖其他agent后续修复。恢复后应为原1852dd... SHA；Sky Gauge图片保持不变。

原厂 Fastboot 属于 aboot，不在本轮修改范围内；lk2nd Fastboot 对 boot 写入会增加512KiB偏移，**不得将整32MiB备份直接通过lk2nd flash boot写入**。若出现故障必须先识别当前阶段再制定恢复步骤。
