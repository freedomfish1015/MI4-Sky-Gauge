# 仪表动态数字/进度弧修复记录（2026-10-18）

> 后续已升级原生1080p，用户确认“更清晰，更新正常”。
> 当前状态以 `GAUGE-NATIVE1080-20261018.md` 为准；下文52–54FPS/CPU16%是半分辨率历史值。

## 结果

已安装到小米4，用户明确确认：**“数字和进度弧都正常更新”**。
保持现有 KMSDRM 裸屏、540×960 渲染/整数2×放大、BLE数据源和专用仪表服务。
没有恢复Phosh，没有修改电池、触控、背光、声卡、固件或内核。

运行采样：稳定51.3–53.8 FPS，paint0.9–1.5ms、upload约0.1ms、present约17ms，
top第二次样本CPU16.0%。服务active，NRestarts=0，BLE已连接并收到rpm/coolant。
启动扫表首两秒较慢（首次日志35.6FPS），随后恢复原来的约53FPS性能。

## 真正问题（不只是卡片数值框）

1. `SDLRect` 使用四个 `ctypes.c_int16`，这是错误的SDL2 ABI：
   SDL2实际需要四个C int，共16字节，旧结构只有8字节。
2. `SDL_UpdateTexture` 的源指针始终指向整张Cairo图的起点。
   局部更新必须用 `base + y * stride + x * 4`，且pitch仍是完整原图的stride。
   用户照片里多个数字位置重复出现“OBD-II”，正是复制了错误的图像区域。
3. 原代码忽略SDL上传错误，矩形被错误解释时无法及时发现。
4. 圆弧脏矩形只用外半径求边界，漏掉内半段；恢复静态背景后仅绘制新旧角度之间
   的差量，又会擦掉区域内之前的弧。现在边界覆盖整个线宽/端帽，恢复后重建当前
   进度前缀（限制在局部clip中），并保持端帽样式稳定。
5. 单次矩形合并会漏掉桥接/传递重叠，可能重复清除已有动态内容；已修成传递合并。
6. 文字内容不变但越过告警阈值时颜色会变；现在颜色也参与脏标记。
7. `GAUGE_DUMP=path:300` 曾依赖每两秒清零的FPS计数，通常永远到不了300。
   现在使用独立生命周期 `total_frames`，只导出一次。

数值框已按当前 `CARD_H*0.58` 中心和真实字形高度计算，避免以后布局变化不一致。
原框0.30–0.76其实大体覆盖当前数值，不能把它独立认作“所有数字消失”的根因。

SDL2官方依据（没有下载GitHub文件）：

- [URL REDACTED]
- [URL REDACTED]

## 文件与校验

电脑代码：`[LOCAL-PATH]`

手机实际代码：`/home/umeko/desktop-offline/gauge_sdl.py`

修复版SHA256：
`924d7d6a2e9a140f913e3765a5683c1ad2dfeaee3d705433ead1ac6dc9cae88f`

修复前SHA256：
`baa7ef41fc0a029c2a08f19dbc2f563692a7d9b40c5062a81c1ed3d7b8dc2388`

电脑和手机均保留 `gauge_sdl.before-dirtyfix-20261018.py`，不会覆盖该备份。
手机另保留 `gauge_sdl.dirtyfix-candidate.py` 与 `install_dirtyfix.sh`。
安装脚本校验旧文件/候选/备份哈希，原子替换；若服务启动失败则恢复旧文件。
它仅支持这一次旧版本->新版本部署，不是通用更新器，不要反复执行来刷其他版本。

## 验证

`test_gauge_sdl.py` 使用unittest：

- SDL2矩形ABI、局部上传像素源、向外取整和边界裁剪、跳过空矩形、原生错误抛出。
- 增量帧对照全量帧：跨大小RPM变化、归零、告警阈值颜色变化。
  允许Cairo曲线细分在1像素边缘内的抗锯齿覆盖差异，实心区域仍须一致。
- 桥接矩形合并。
- 真正SDL2 dummy/software渲染器：上传全帧后更新局部，读回屏幕像素与CPU原图完全一致。
  这项测试不占用KMS、不停止仪表、不连接BLE。

本地Mi4Build WSL：7项通过、1项原生SDL测试跳过（未安装SDL2）。
**手机：8项全部通过，耗时35.990秒，含原生SDL2像素读回。**
用户随后确认真实屏幕数字和进度弧持续更新。

重跑手机测试（串口命令超时至少45秒，不与其他串口调用并行）：

```bash
cd /home/umeko/desktop-offline
GAUGE_TEST_NATIVE_SDL=1 python3 -m unittest -v test_gauge_sdl
```

相关文件位于本目录：

- `dirtyfix-before-tests.log`：修复前失败记录。
- `dirtyfix-after-tests.log`：本地WSL修复后测试。
- `dirtyfix-phone-tests.log`：手机8项测试结果。
- `dirtyfix-install.log`：备份、原子更新与服务启动。
- `dirtyfix-runtime-verified.log`：稳定帧率、CPU、当前哈希与服务状态。
- `dirtyfix-before-incremental.png` / `dirtyfix-after-incremental.png`：无头300帧导出。
- `dirtyfix-mismatch-*`：调试中间图，不是最终失败证据。

## 回退（仅在新版本确有问题时）

```bash
cd /home/umeko/desktop-offline
cp -p gauge_sdl.before-dirtyfix-20261018.py gauge_sdl.py.rollback
mv -f gauge_sdl.py.rollback gauge_sdl.py
sudo systemctl restart obd-gauge-kiosk.service
```

备份是旧的错乱版本；当前用户已确认修复成功，不应无故回退。
不会重装桌面，也不需要重启手机或刷机。

## 后续注意

不要继续用旧声卡交接中“Phosh还在、音频未持久化”等历史状态推断当前系统；
用户已借助其他AI完成声卡持久化和系统裁剪，当前主要程序就是本SDL仪表。
当前提交只修动态刷新。真实车辆适配、长期运行/息屏唤醒、BLE断连体验等不在本次验证范围。
