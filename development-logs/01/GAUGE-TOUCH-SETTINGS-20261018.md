# Mi4 仪表触控设置（2026-10-18）

## 用户需求及范围

仪表左滑进入设置，右滑或点“返回”回仪表；设置包含 PID 数据包、蓝牙连接、屏幕亮度。
用户确认先做“标准 OBD-II”和“BMW G 模拟器”两套，保留自定义 JSON 扩展。
没有刷内核、改 ESP32 固件，未改电池/OCV、触控驱动、WLED/背光驱动、声卡和服务启动方式。
保留鼠标隐藏、原生 1080×1920 像素 1:1、Cairo/SDL 并行渲染及垂直同步。

## 当前文件

电脑目录：`[LOCAL-PATH]`。
手机目录：`/home/umeko/desktop-offline`，服务 `obd-gauge-kiosk.service`。

- `gauge_sdl.py`：SDL 事件 ABI、触摸坐标旋转、主线程 PollEvent、事件队列及设置页切换。
  SHA256 `27e29eb0e7ca74643fc202dff871daedd4a297f9f0e1f2b37d73f388679ea8f7`。
- `gauge_settings.py`：设置保存、数据包校验、可切换的 BLE 源、后台扫描、亮度控制、设置页绘制。
  SHA256 `c854986674aa3a21a557e2ba8782d1769026770682f9a72226726fa7edb08b35`。
- `test_gauge_settings.py`：触控/设置/重连/原生 SDL 测试。
- `smoke_gauge_settings.py`：有界真实 BLE 两套数据包、扫描及亮度接口测试。
- `90-obd-gauge-backlight.rules`、`91-obd-gauge-touch.rules`：两条严格限定设备/属性的权限规则。
- `install_gauge_settings.sh`：只适用于首次安装（有旧版本哈希和已有规则检查），不要反复运行。
- `settings-preview/settings-{0,1,2}.png`：原生横屏设置页预览。

## 权限问题：真实触摸一度无响应，已经定位并处理

最初软件注入的 SDL 测试正常，但用户实测左滑无效。
证据：`umeko` 仅在 sudo/audio/video 组；触摸屏 `/dev/input/event1` 为 root:input 0660；
运行中的仪表没有任何 input fd，故根本收不到实体触摸事件，不是手势阈值问题。

已安装 `/etc/udev/rules.d/91-obd-gauge-touch.rules`：
只匹配 `Atmel maXTouch Touchscreen` 的 event 节点，group=video、mode=0660。
没有把用户加入整个 input 组，没有开放电源键/其他输入设备。
reload-rules + 对 event1 的 change trigger 后重启仪表，实际已确认 root:video 0660，
仪表进程 fd7 正在读取 `/dev/input/event1`。用户随后确认：现在都正常
（左滑进入、点选标签、亮度调节、右滑返回）。

亮度：只对 `/sys/class/backlight/backlight/brightness` 授予 video 组写入；
规则 `90-obd-gauge-backlight.rules` 在 add 时应用。max_brightness=4095，最低5%，最高100%。
没有改驱动寄存器，没有开放整个 sysfs。初次运行若没有保存值则保留当时亮度（2351）。

## 交互与数据行为

- 视觉横屏左滑 >75 布局单位、纵向偏移 <60、1.8秒内进入设置；反方向回仪表。
- SDL 原始肖像屏归一化坐标转换 `x=ny*640, y=(1-nx)*360`。
  第一根手指独占一次手势，忽略 SDL 的触摸转鼠标重复事件。
- 亮度滑块拖动不触发左右换页；约10Hz节流写入，松手保存。另有5/25/50/75/100%预设。
- PID 切换/设备点选会先取消旧连接、干净 disconnect，再建立新连接。不会同时占两个 BLE 客户端。
- 扫描后台6秒，设备列表上下直接拖动（约3行可视区域，有滚动条），不再用“下一页”。
  已保存目标即使因连接中停止广播，也保留在列表里。
- 蓝牙只支持当前 FFE1 串口型 BLE OBD，不是经典蓝牙 SPP 的完整支持。
- 标准数据包用 Mode01，BMW G 模拟器油温用224402，2字节、raw×0.75−48。
  该包只验证 ESP32 模拟器，不代表适配真实 BMW G 车辆。
- 不支持/无响应的 PID 显示 `--`，不再保留伪造的默认电压/温度。
- 设置页仅状态变化时绘制，后台继续采集；返回仪表会全屏恢复一次，之后继续脏矩形更新。

## 持久化及自定义数据包

手机 `~/.config/obd-gauge/settings.json`，原子替换写入0600文件。
保存 profile/address/enabled 和用户选择过的 brightness。保存的地址优先于服务 `--ble` 默认地址。
真实检查期间用临时目录，不覆盖用户设置；亮度短暂从57%调到58%，随后已精确恢复原值2351。

自定义 JSON 目录：`~/.config/obd-gauge/pid-profiles/*.json`。
最多额外24文件；数据包 id 唯一、name/description、pids 对象，必须有 rpm。
每个 PID 支持 command、bytes(1–4)、scale、offset，无 eval/任意脚本。
只允许 `01xx` / `22xxxx` 只读查询，不允许 AT 指令/写参数/清故障码。
未列出的 coolant/oil/speed/battery 显示 `--`。
示例：

```json
{"id":"my-readonly","name":"我的只读包","description":"请按适配器和车型资料填写",
 "pids":{"rpm":{"command":"010C","bytes":2,"scale":0.25,"offset":0}}}
```

## 已做验证和边界

- 电脑完整23项：21通过，2项依赖真SDL跳过，含完整增量与全量像素比较。
- 手机14项针对性测试全部通过，含真实 SDL_PushEvent/PollEvent、坐标旋转、过滤重复鼠标、
  设置返回重绘一致性、亮度保存、重连顺序、真实 SDL 局部纹理读回及并行缓冲线程约束。
- 最初在手机运行全部像素比较耗时过长，串口50秒超时；随后 Ctrl+C 栈确认停在
  test_incremental_matches_fresh_full_frame 的逐像素 Python 比较。未当作通过；改在电脑跑完整比较，
  手机跑上述14项针对性测试。没有中断仪表服务来“修复”此测试。
- 真实 BLE：标准5项读数正常；BMW G模拟器5项正常（油温84.75℃样本）；
  扫描发现19台，包含实际广播中的 OBDII [BT-ADDRESS]。
- 真实亮度写入成功并恢复原值；服务 active / NRestarts=0。
- 最新仪表运行样本约51–59.2FPS，多次59.2；不是承诺恒定60FPS，新增设置没有改屏幕刷新模式。
- 证据：settings-phone-tests.log / settings-smoke.log / settings-install.log /
  settings-runtime.log / settings-touch-diagnosis.log / settings-touch-permissions.log。
- 用户已确认权限修复后的实体手势与设置操作正常。
  未做整机重启后规则持久性实测、长时间待机或实车测试。

## 后续：蓝牙列表直接滚动

后续用户要求蓝牙列表改成上下滑动，已更新并部署：
纵向拖动超过8布局单位且纵向位移大于横向位移后捕获列表滚动；
拖动不触发连接，轻点按偏移后的实际设备行连接；横向右滑仍回仪表。
列表上下边界钳制，内容裁剪，不覆盖顶部标签/底部按钮。
新增测试涵盖滚动后选中正确设备、上下边界、拖动不误连接及横向返回。
手机最终新增版本12项全部通过；电脑最终完整24项22通过/2项SDL依赖跳过。
服务active/NRestarts0。
证据 settings-scroll-phone-tests.log / settings-scroll-install.log。
这次滚动交互尚待用户实际确认；此前三项设置已确认正常。
手机模块备份 `gauge_settings.before-scroll-20261018.py`（d794开头，分页版）。

## 回退（仅在需要时执行）

两端正确备份：`gauge_sdl.before-settings-20261018.py`，SHA256
`bc7f9139f1890350609dfc7067f6d6b18510564e0ec582c630547547dded00d1`。
电脑备份由手机当前原始文件压缩分块取回并核对 SHA；不要误用 ecde 开头的 cursor-visible 版本。

```bash
cd /home/umeko/desktop-offline
cp -p gauge_sdl.before-settings-20261018.py gauge_sdl.py.rollback
mv -f gauge_sdl.py.rollback gauge_sdl.py
sudo systemctl restart obd-gauge-kiosk.service
```

正常应用回退不会删除设置或两条设备权限规则，也不会调整内核/驱动。
需要完全撤销权限时，先停服务、将本轮两条规则移到备份位置、reload-rules，
brightness恢复root:root0644，触摸event恢复root:input0660；不要对 /dev/input 或 /sys 批量chmod。
