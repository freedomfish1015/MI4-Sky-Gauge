# 插线充电需求：当前状态

用户已授权先进入临时充电模式。17:27 左右已执行 temporary_charge_priority.py，正常停止 obd-gauge-kiosk / mi4-motion / mi4-elm-advertiser，背光 brightness 与 actual_brightness 均为 0。USB 调试/系统与充电仍运行；不是关机或 suspend，也未关闭运行中 modem。保留原有服务 enabled 配置，重启会回到原启动流程。

恢复命令（手机）：sudo python3 /home/umeko/desktop-offline/temporary_charge_priority.py --restore

恢复状态 /run/mi4-charge-priority.json 保存原亮度 901、三个服务原均 active。用户正在充电，不要擅自恢复负载或重启。开始前 ADC 约 3.45–3.49 V，减载后约 3.53–3.54 V；这部分变化包含负载减轻引起的回升，不能作为充入容量测量。SOC 一直错误显示 100%。

## 插线自动启动尚未取消

实际 boot / aboot 已只读备份到 /home/umeko/desktop-offline/backups/before-charge-only-j0zgv4zo：

- boot 33554432 bytes, SHA256 1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a
- aboot 4194304 bytes, SHA256 ff7bd7e050e5e91a6f50e8e31025c911f4c2f8b2ec73d2e2b3ccbc247b1c1212

原厂 aboot 的只读字符串明确包含 charger-screen-enabled、oem enable-charger-screen、oem disable-charger-screen、androidboot.mode=charger。没有确认 off-mode-charge 命令，禁止凭别的机型命令直接写未知 OEM 项。尚未查询实际 Fastboot getvar 值，也未执行任何 OEM/引导写入。

上游 aboot 源码显示 charger screen 标志会使内核命令行带 androidboot.mode=charger，不代表 bootloader 本身能独立充电；此机 lk2nd 是否转交标志、Ubuntu 是否有纯充电处理都需验证。不能只打开 flag 就宣称插线不启动 Linux。低压时不能贸然重启/刷引导。调试熄屏新服务也尚未部署。

证据：charging-reconnected-20261020.log、charge-only-bootloader-inspect-20261020.log、charge-only-backup-20261020.log、temporary-charge-priority-20261020.log、temporary-charge-voltage-20261020.log。
# 后续已加入设置页充电模式

2026-10-21 已另行部署带实体电源键恢复、服务状态恢复和防误触确认的充电模式按钮，见 `CHARGE-MODE-20261021.md`。本文件中的temporary_charge_priority.py为早期手动工具记录，不要与新模式同时使用；新模式不改动bootloader或充电驱动。

