# 开机加速：视频并行预热 + 服务裁剪（2026-10-19）

目标：接电到仪表从 34 秒压到 20-22 秒，**完整保留 12 秒开机视频**。

## 冷启动基线（改动前实测，内核单调时钟）

| 时刻 | 事件 |
|---|---|
| 0 → 5.75s | 内核 + initramfs + rootfs + systemd |
| 5.75s | 幕布首帧 |
| 5.77 → 8.48s | `mi4-audio-init`（等 vreg-boost） |
| 8.48 → 14.20s | kiosk 起来 + SDL/KMS + GStreamer 管线 |
| 14.20 → 26.25s | 视频播放（12.05s 媒体，125 帧） |
| 26.25 → 30.65s | 交接 + 仪表构造 + 首帧 |
| 30.65 → 32.01s | BLE 连上 |

视频结束后到出画面 **4.4 秒**，其中 BLE 握手独占 **5.6 秒**——这段完全是串行浪费。

## 改动 1：视频播放期间并行预热（launch_boot_video.py）

新增 `warmup()`，在视频开始播放后立刻起后台线程（daemon，不阻塞视频解码循环）：

- `gauge_sdl.load_drawing()`：Pango/cairo 字体栈
- 解码 `assets/rei-reference.png`
- 预光栅化两套 `Digits` 字形图集
- **启动 `SettingsBleSource`**，让 BLE 握手在视频播放期间就开始

实测预热耗时：字体栈 0.80s、图集 0.22s、素材 0.07s，合计约 1.1–1.6s。
这些全部落在视频的 12 秒窗口里，原本是 EOS 之后的串行成本。

## 改动 2：交接复用已连接的 BLE（gauge_sdl.py / gauge_settings.py）

- `gauge_sdl.main()` 新增 `preset_source` 参数；非空时直接复用，不再新建连接。
- `SettingsBleSource.__init__` 保存 `self.config`，让调用方能构造匹配的 `TouchSettings`。

行为等价性：原路径用 `Config(address=address)`，预热用 `Config()` 从同一份
`settings.json` 读取地址，配置来源一致。

## 改动 3：裁剪启动服务（trim_services.py）

| 服务 | 原状态 | 现在 | 理由 |
|---|---|---|---|
| `systemd-udev-settle.service` | static | **masked** | 空等所有设备出现，实测 7.9s；显示链路不依赖 |
| `ssh.service` / `ssh.socket` | enabled | **masked** | 用户已确认不再需要远程调试 |
| `NetworkManager.service` | enabled | **masked** | 仪表是纯 BLE 客户端，无网络需求 |

原状态记录在 `/var/lib/obd-gauge-trim-services.state`，可完整回滚。
纯 rootfs 改动：未触碰 boot 分区、内核、DTB、硬件驱动、音频与触摸修复。

## 验证

- `test_boot_warmup.py`（AST 接线，10 项）：本地全过
- `test_boot_warmup_device.py`（真实导入，9 项）：设备全过，确认从 root 目录加载
- 服务重启日志确认并行生效：
  ```
  BOOT_WARMUP_ASSETS 1.56s
  BOOT_WARMUP_BLE_STARTED [BT-ADDRESS]
  KMS mode 1080x1920 @60Hz
  BLE connected [BT-ADDRESS]
  ```
  预热线程、KMS 初始化与 BLE 连上在同一秒内完成。
- 稳态 FPS 48–58，`paint` 3–6ms，CPU 温度 37°C，无性能退化。

## 第一次冷启动实测：33s（只省 1s）——三个问题已定位并修正

首次冷启动时间线（单调时钟）：

```
[15.68] BOOT_WARMUP_ASSETS 3.14s
[15.84] BOOT_WARMUP_BLE_STARTED          ← 视频播放期间发起 BLE
[16.86] BLE error: BleakError('No Bluetooth adapters found.')
[16.87] BOOT_VIDEO_FIRST_FRAME           ← 比基线晚 2.7s
[24.05] BLE connected                     ← 视频播到一半才连上
[28.84] BOOT_VIDEO_EOS_COMPLETE
[29.11] BOOT_HANDOFF same_window=1 warm=1
[29.13] BLE preset reused
[32.67] FPS 19.3 paint=44.7ms             ← 交接抖动
```

**判定**：核心目标达成（交接 4.4s → 0.09s，BLE 在视频期间连上），
但被三个问题吃掉，净省仅 1 秒。

| 问题 | 根因 | 修正 |
|---|---|---|
| 首帧晚 2.7s | 预热线程的光栅化与 GStreamer 解码抢 CPU | `warmup()` 开头 `sleep(1.5)`，先把 CPU 让给解码 |
| `No Bluetooth adapters found` | 预热在 15.84s 发起 BLE，但 bluez 16.72s 才 active | 新增 `bluetooth_ready()` 轮询 `/sys/class/bluetooth/hci*`，就绪才连 |
| 交接后 FPS 掉到 19 | 交接瞬间才构建静态底图 + 全部图集 | 新增 `prerender_static()`，视频期间预渲染装饰层，`Gauge` 用 `static_cache` 复用 |

附加收益：`prerender_static()` 的缓存以解析后的 `cards` 布局为键，
若用户在设置里改过窗口布局则自动丢弃并重建，不会显示过期界面。

## 待验收（第二次冷启动）

拔线关机再插线，确认：
1. 首帧回到 14–15s 区间（不再被预热推迟）
2. 日志出现 `BOOT_WARMUP_BLUETOOTH_READY 1`
3. 日志出现 `BOOT_WARMUP_STATIC`，交接行显示 `static=1`
4. 接电到仪表总时长

## 严重回归：prerender_static 丢失插画（已修复并像素级验证）

第二次冷启动后**用户报告仪表界面不正常**。根因：

```python
scratch = Gauge.__new__(Gauge)      # 跳过 __init__
scratch.rei_portrait = None         # ← 插画被硬置空
```

`draw_rei_portrait()` 在 `rei_portrait is None` 时**静默 return**，
所以缓存层少了绫波丽插画，但所有日志都显示"正常"、FPS 也正常——
典型的静默渲染退化，肉眼可见但指标测不出来。

同一个函数还有第二个缺陷：它直接用 `gauge_sdl.cairo`，
而该名字只在 `load_drawing()` 之后才绑定，独立调用会抛
`AttributeError: module 'gauge_sdl' has no attribute 'cairo'`
（当时被 `except` 吞掉，只留一行 SKIPPED 日志）。

**修复**：
- 显式解码 `assets/rei-reference.png` 赋给 `scratch.rei_portrait`
- 补齐 `window_bindings` / `window_profile`
- 函数开头自己调 `gauge_sdl.load_drawing()`
- 日志打印 `portrait=True/False`

**验证**（`test_warmup_static.py`，新增）：
```
ok   cached layer is pixel-identical (0/8294400 bytes differ, 0.0000%)
ok   reference layer has the portrait
cached alpha bytes 2073600, reference alpha bytes 2073600
```
8.3 MB 表面**零字节差异**，插画 alpha 通道一致。
另有 `test_boot_warmup.py` 的 AST 断言（25 项）防止属性再次漏设。

**教训**：用 `__new__` 造"临时实例"绕开 `__init__` 是这次回归的直接原因。
宁可让 `prerender_static` 完整构造一个对象，也不能手搓一个残缺对象——
`None` 默认值让缺失属性变成静默降级而不是报错。

## 第二个严重回归：双 BLE 连接导致闪烁与 `--`（已修复）

用户报告**仪表持续闪烁、大量数据显示 `--`**。日志显示：

```
[13:23:55] HANDOFF same_window=0 warm=0 static=0    ← 视频标记已存在，没播视频
[13:23:56] BLE connected ...                          ← main() 建了连接 #1
[13:23:56] KMS mode ...
[13:23:56] BOOT_WARMUP_BLE_STARTED ...                ← 预热线程又建了连接 #2
[13:23:57] BLE connected ...
```

根因：`warmup()` 线程在 `run()` 里**无条件启动**。当视频标记已存在
（服务重启、不播视频）时它纯属多余，而 `main()` 因 `preset_source` 为空
会自建连接——两个 bleak 客户端同时抢同一个 ESP32：
连接互相干扰 → 数据断续显示 `--` → 频繁重连 → 画面闪烁。

**修复**：
1. 预热线程移入"确实要播视频"的分支内；标记存在时完全不启动。
2. 交接前 `worker.join(timeout=5)`，防止预热在交接后才发布 source
   （那样 source 会被忽略，而它的 BLE 连接仍然活着）。

**验证**：`BLE connected` 计数从 **2 → 1**；`warm=0 static=0` 确认预热未启动；
FPS 从 19-29（paint 27-46ms 尖峰）恢复到 **43-59**（paint 2-9ms）。

`test_boot_warmup.py` 新增 4 项 AST 断言锁定"线程必须在播视频分支内创建"
且"join 必须早于交接"，共 29 项。

**教训**：任何"后台预取 + 主流程消费"的模式，必须保证**预取与消费互斥**，
否则两份资源同时存在就会互相踩踏。这里是 BLE 单例被创建了两次。

## 第三个严重回归：static_pattern 绑定顺序错误（已修复并视觉确认）

用户报告**仪表图形页面缺失**。根因在 `Gauge.__init__`：

```python
self.static = cairo.ImageSurface(...)            # 空白
self.static_pattern = SurfacePattern(self.static) # ← 绑定了空白
...
if static_cache ...:
    self.static = static_cache['surface']         # ← 换成有内容的，但 pattern 没跟上
```

`paint()` 用 `static_pattern` 恢复脏矩形，pattern 仍指向**空白 surface**，
于是每次增量重绘都把刚画好的装饰擦掉——仪表图形全部消失。
日志无异常、FPS 正常，属于纯视觉静默退化。

**修复**：把 `static_pattern` 的创建移到 `self.static` 终态之后，并加注释说明。

**验证**：
- `test_boot_warmup.py` 新增断言：pattern 创建行号必须晚于缓存赋值行号（31 项）
- `test_warmup_static.py` 新增源码顺序检查 + 像素比对
- **视觉确认**：`export_static_preview.py` 导出 480×854 预览并取回本地，
  六边形转速表、绫波丽插画、四角卡片、刻度、红线段、底部进度条**全部正常**
- 运行时 FPS 45–59，`paint` 3–8ms

## 开机白闪修正（boot_video.py，已改待冷启动验证）

视频播放前的白闪来自两个时序漏洞：
1. `SDL_CreateWindow`/`CreateRenderer` 一创建就触发 KMS 扫描输出，
   而此时缓冲区尚未上传任何内容。
2. 背光在**第一个** YUV 帧后就恢复，但纹理格式刚从 ARGB 换成 IYUV，
   swap chain 未必所有 buffer 都已收到 YUV 数据。

**修正**：
- 首帧上传后连续 `present()` 三次，确保 KMS 能触及的每个 buffer 都已有画面
- 纹理格式切换后再 `present()` 一次，让 swap chain 在新格式下稳定
- 背光恢复推迟到**第二个解码帧**之后（新增 `frames_shown` 计数）

## 主题改版：六边形双表（左时速 / 右转速）

用户要求中间六边形左侧显示时速、右侧显示转速，各配一套刻度。

### g 值检测：硬件不支持
设备上**没有任何 IMU 驱动**：
- `/sys/class/sensors` 目录不存在
- `/sys/bus/iio/devices` 只有两个设备，均为 PM8941 的 **ADC**
  （`adc@3600` 电流、`adc@3100` 电压/温度），不是加速度计或陀螺仪
- `/dev/` 下无 accel/gyro 设备，`lsmod` 无 mpu/bma/qmi8 传感器模块

因此不做 g 值显示，也不伪造数据。中间菱形区保留插画作底纹。

### 实现要点
| 项 | 内容 |
|---|---|
| 时速弧 | 左侧 180°（`speed_angle`: 270°→450°），量程 0–240，红线 180 |
| 转速弧 | 右侧 270°（`angle_for`: 135°→405°），量程 0–8000，红线 7000 |
| 数字位置 | `cx ± radius*0.46`，两侧各一片可读性遮罩 |
| 刻度标签 | 内移到 `outer - 30`，避免两套刻度数字互相重叠 |
| 时速刻度 | 每 20 一格，每 60 标注（60/120/180） |
| 平滑 | 新增 `SPEED_STEP=3.0`（原来跟卡片共用 1.5，对弧线太慢） |
| 脏矩形 | 新增 `REGION_SPEED_ARC`/`REGION_SPEED` 掩码、`speed_arc_box()`、`speed_value_box()`，状态加 `prev_speed`/`shown_speed` |
| 配色 | 时速用反向冷色渐变（CYAN→BLUE），与转速弧可区分 |

### 验证
- 设备端跑 60 帧真实增量路径渲染，`FRAME_OK speed=148.0 rpm=2860.0`
- 导出 PNG 取回目视确认：两侧数字、弧线、刻度、红线、插画、四角卡片均正常
- 实机运行 FPS **53–59**，`paint` 4.3–6.4ms，`upload` 0.2ms（双弧未造成性能损失）

装机：`gauge_sdl.py` `2837e11e241076e72bcb96c9e908d779ff7dd4f81b8be13fa7ebe8d2e2822aa8`

## 待验收（冷启动）

拔线关机再插线：确认①图形完整 ②无白闪 ③数据正常 ④双表显示正确 ⑤记录秒数。

## 装机文件与 SHA

| 路径 | SHA256 |
|---|---|
| `/usr/local/lib/obd-gauge/launch_boot_video.py` | `550dd6ba7d5688429273c83801fec6c34d42cc482323139f8046d711fa5b3d02` |
| `/home/umeko/desktop-offline/gauge_sdl.py` | `68b44cbb3d048e41444c10f71c81a400985ec3ace1789fae7205e11bc0fe716f`（pattern 顺序修复） |
| `/usr/local/lib/obd-gauge/boot_video.py` | `e4650cb0d7589bbe52b1943858c2c59d8ee84208d8e5d5c2a4c50e38f0e28d29`（白闪修复，**待装**） |

**注意：开机实际执行的是 `/usr/local/lib/obd-gauge/` 下的版本，用户目录
`/home/umeko/desktop-offline/` 的同名副本被忽略。** 改启动行为必须改 root 目录。

备份：`/usr/local/lib/obd-gauge/before-warmup-20261019/`（含原
`launch_boot_video.py` `22ace6ac…` 与 `boot_video.py` `cb421b15…`）。

## 待验收

~~冷启动（拔线关机再插线）实测接电到仪表的总时长。~~ 第一次实测 33s，
问题已定位修正，见下节。第二次冷启动待做。

## 回滚

- 服务：`unmask systemd-udev-settle ssh ssh.socket NetworkManager` 并按 state 文件恢复 enable
- 播放器：`cp before-warmup-20261019/launch_boot_video.py` 回 root 目录
