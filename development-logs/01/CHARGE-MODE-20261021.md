# 设置页充电模式（已部署，USB进入/退出实测通过）

> 同日后续：用户已取消开机视频，最新启动器改为launch_gauge_direct.py，重启实测正常；详见`DIRECT-STARTUP-20261021.md`。本充电服务及按钮没有修改，原boot-video.done标记仍保留但新入口不再使用。关于“不重播视频”的描述现已由全局无动画启动实现。

## 用户操作

“设置”顶部“关机”左侧新增 **充电模式** 按钮（逻辑坐标458…544，y6…36）；关机按钮原位置不变。首次点击显示说明，6秒内再次点击确认，防误触。

需已连接外部供电，否则提示“请先连接充电线”。进入时结束并保存GPS行程和LOG，停止仪表渲染、motion/GPS服务、BLE网关和BlueZ，将背光设为0；系统充电与USB串口调试保留。不是关机或Linux suspend，也没有改PMIC、充电电流或modem remoteproc供电。

短按电源键（收到按下及松开）恢复进入前活跃的服务和亮度；保留开机视频完成标记，直接恢复仪表，不重播视频。充电期间仅临时独占电源键，防止logind把恢复动作解释为关机，退出后释放。长按电源的硬件强制关机/复位功能不变。

拔掉外部电源会自动退出充电模式，让原有20秒拔线关机弹窗重新可见；没有修改原 `obd-power.service`。停止motion服务会结束本次轨迹、重启G值内存峰值，恢复后不会自动继续之前的行程记录，原记录文件保留。没有承诺精确充电速度或关闭全部无线/协处理器。

## 实际部署

- 手机UI：`/home/umeko/desktop-offline/gauge_settings.py` SHA256 `38eff83dec8430756c208a54d91b5ffe971623ba8f4f9f3c4d012498faed1e77`。
- 非特权客户端：`/home/umeko/desktop-offline/gauge_charge_mode.py` SHA256 `8f9b36fe502edb8e4fae4dc9f138d47f0aeb0847bed53cb55d40953726214fa4`。
- root守护程序：`/usr/local/lib/obd-charge/gauge_charge_mode_service.py` SHA256 `6ed3f4d458f59a5c9142555a327d7379e91ed06df3e4edb9de8aaa7b81e36a6d`。
- unit：`/etc/systemd/system/mi4-charge-mode.service`，enabled，开机仅正常待命，不会自动进入充电模式。
- Unix socket `/run/mi4-charge-mode/control.sock`，root:umeko、0660；SO_PEERCRED仅允许root和umeko。只接受enter/restore/status固定操作，无任意命令、单位名称或路径RPC。
- 状态 `/run/mi4-charge-mode/state.json`，root-owned；保存原亮度、服务活跃状态、rfkill、视频标记等。`/run`在重启后清空，重启按原流程进入仪表。
- 电源键 `/dev/input/by-path/platform-fc4cf000.spmi-platform-fc4cf000.spmi:pm8941@0:pon@800:pwrkey-event`；input_event原生ABI（armhf16字节），EVIOCGRAB仅在充电模式生效。

### 蓝牙服务自动激活修复

首轮实测发现停止BlueZ后会被系统DBus/WirePlumber重新激活，不能仅凭stop命令宣称已停。最终方案在充电期间使用 **runtime-only mask**，并将蓝牙rfkill按原状态暂时屏蔽；恢复时撤销本次runtime mask并恢复原rfkill，若原本已runtime masked则保留。不更改永久enable配置，也不修改蓝牙固件或网关协议。

原状态保存在停止服务之前，过渡失败时尝试恢复；守护程序崩溃后利用/run状态恢复过渡或继续监控充电模式。充电中若电源键设备无法重新打开，则尝试恢复仪表，不把用户永久留在黑屏状态。系统关机时不从SIGTERM处理里重新启动服务。

## 验证

电脑43项相关测试通过（1项跳过），随后新增runtime mask恢复专项测试通过；手机初版14项专项通过，最终更新版测试见后续实机测试日志。合成布局图 `charge-settings-preview.png`。

实机自动进入与USB恢复：`charge-mode-live-smoke-v2-20261021.log`：

- 充电时 kiosk、motion、BLE网关、bluetooth四项均inactive；brightness=0，usb_online=1。
- 通过非特权客户端restore后四项均active，brightness恢复901。
- `LIVE_ENTER_AND_USB_RESTORE_PASSED`。
- 首轮日志 `charge-mode-live-smoke-20261021.log` 因BlueZ被重新激活而断言失败，但finally已成功恢复；不要把首轮标为通过。

正在等待用户从实际设置按钮进入，并验证实体电源键退出。自动USB恢复通过不等于电源键已通过；未测试充电模式期间拔线恢复/原20秒倒计时的实机联动（逻辑测试通过）。

## 代码与备份（防止覆盖其他agent待部署修改）

电脑根目录 `gauge_sdl.py`、`gauge_settings.py` 有此前未部署的调试待机修改，本轮没有覆盖它们。先导出手机实际settings（原SHA `8495a4852154fddbddfb64463e3162b73d2affcab031aeca577a9de96c0b347d`），只在 **`charge-mode-deploy-20261021/gauge_settings.py`** 这份实际设备分支上加充电按钮。它是当前已部署设置源码；不要把电脑根目录旧settings直接覆盖手机，否则会丢失充电按钮。

安装器 `install_charge_mode_20261021.py` 严格校验上述原settings/main SHA；备份：**`/home/umeko/desktop-offline/backups/charge-mode-before-4ggs3wx5/`**（root0700）。其中含原settings、未变化文件哈希、安装清单、初版daemon备份。`update_charge_mode_runtime_mask.py` 仅在normal状态按精确SHA更新初版daemon，未重启其他服务。

main仍 `a541e6c531255652d42a9f49c8bb255b6b34e2df5d1e1e0d04074ae1acfe1dfc`；原电源策略仍 `05543f3ffe769a219b4f5993a59efbcfba7ba50fd2a0e8f7fe71d7f112756533`。安装器同时比较boot/aboot/logo前后SHA完全不变，没有改动刚验证过的Sky Gauge图标和隐藏文字补丁。

## USB应急退出与回退

Linux串口还可用时，以umeko执行：

`cd /home/umeko/desktop-offline; python3 -c 'from gauge_charge_mode import ChargeModeClient; print(ChargeModeClient().request("restore"))'`

若守护服务异常，先 `sudo systemctl restart mi4-charge-mode.service`，它会恢复/run状态，再发送restore。不要只停止/禁用服务后把仪表留在停机状态。

卸载/回退前先restore到normal，停止并disable新service，核对当前settings SHA后恢复本次备份settings，再restart kiosk；移除本次新增client、unit和root脚本时只删除这些精确文件。若后续有其他修改，先合并，不能整文件回退。旧临时脚本 `temporary_charge_priority.py` 仍是独立历史工具，不要与新模式混用。
