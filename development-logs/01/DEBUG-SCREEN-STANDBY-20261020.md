# 调试熄屏待机（待部署）

设置页右上角“调试待机”。新 root 服务 obd-debug-screen.service 使用标准 logind handle-power-key inhibitor，将电源短按用于亮/灭背光；长按硬件强制复位不改。sysfs brightness=0 熄背光，不做系统 suspend，不操作 modem/稳压器/充电参数。关机仍在原按钮与拔线倒计时，不修改 obd-power.service。

熄屏期间忽略触摸，跳过 Cairo 重绘，继续 GPS、BLE、LOG 与外部电源心跳；拔线倒计时弹窗触发自动恢复亮度。亮度用实际原始值恢复，不改已保存的百分比。服务退出会恢复；异常重启从 /run 标记恢复。不是低功耗长期待机，也不能替代低电量保护。

文件：gauge_debug_screen.py（客户端）、debug_screen_service.py（root 控制）、obd-debug-screen.service、gauge_settings.py、gauge_sdl.py；install_debug_screen.py 是有旧版本 hash 守卫的安装器。根服务只接受本机 root/umeko 的 blank/wake 固定请求，无通用命令。

桌面 58 项相关测试运行成功（1 项跳过），包括 5 项新测试。2026-10-20 尝试上传时 COM10 已消失，未部署新代码/未安装新服务。需手机正常启动并恢复 USB 连接后继续，先核对实时 hash，再传 debug-new-* 与 service/installer，sudo python3 install_debug_screen.py。不要直接覆盖其他 AI 的后续修改。

部署后必测：服务 active、systemd-inhibit --list 中 handle-power-key 正常；点击按钮 brightness/actual_brightness 是否到 0；电源键恢复同一画面与原亮度、不触发关机；重复两次；拔线安全流程保持正常。未物理验证前不宣称已完成。

回退：先停止 obd-debug-screen.service（正常退出恢复亮度），disable 服务，停止仪表，恢复安装输出备份目录两个 app 文件，再启动仪表。停止服务会释放 inhibitor，使电源短按恢复原 logind 行为。
