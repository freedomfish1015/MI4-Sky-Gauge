# 紧凑设置页与PID上下滑动列表

用户要求：上半部按钮缩小、扩大选择列表、PID由翻页改为滑动。

已部署手机 `/home/umeko/desktop-offline/gauge_settings.py`，SHA256 **`407ae3648dacf034a04d631a12fe2febae27467803aca99b3ee8318fcd61a6f4`**。

- 顶栏按钮高度44→30逻辑像素；标签44→28，标签区域y42–70。
- PID可视区域y82–326，高244，旧180；增加35.6%。每行52，绘制卡片46高，约4个完整项目+部分下一项。上下拖动、越界钳位、独立滚动位置与滚动条，移除下一页按钮。
- 蓝牙可视区域y122–310，高188，旧132；增加42.4%。扫描按钮高34，底部断连/重连高32。
- 点选PID使用滚动偏移计算正确索引；拖动不触发选择，行间隙/底部说明不触发；水平右滑返回仍有效。列表各自保存位置，不相互影响。
- 亮度滑块及快捷档的坐标/保存逻辑不变。Native PID、BLE状态机和17包保留。
- 渲染预览 `compact-settings-preview/settings-0.png` / `settings-1.png` 已人工视觉检查（1920×1080视图）；部分末行被裁剪是有意提示可继续滑动。

测试：设置+native共24项在主机通过（含真实SDL dummy），手机设置15项通过、其中1项真实SDL输入测试未启用而跳过。补充PID拖动不误选/偏移点选/钳位/间隙/右滑返回/标签滚动独立等用例。手机日志 `compact-settings-arm-tests-20261019.log`。

安装器 `install_compact_settings.sh` 核对此前Native设置SHA e07b59af...、拒绝覆盖备份、编译校验后原子替换。原版备份 `/home/umeko/desktop-offline/gauge_settings.before-compact-scroll-20261019.py`。root回退入口 `/usr/local/sbin/rollback-obd-compact-settings`，只恢复该设置代码并重载仪表，不删除PID包或native库。

只重载仪表应用，不重启/不重播视频/不改boot或硬件。安装回退 `obd-compact-settings-guard.timer` 已停止。重载后active/NRestarts0，连接记录显示用户当前选中bmw-g-sim（先前标准选择之后由用户操作切换，不擅自改回）。待用户实机确认布局与滑动。

原976106c总体功能移植尚未完成，详见 `COMPAT-976106C-PHASE1-20261019.md`：本轮按用户新增要求优先完成设置布局；事件核心仍待主题画面动作接入。
