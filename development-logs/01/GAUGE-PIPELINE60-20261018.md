# 原生1080p接近满刷新率优化（2026-10-18）

> 最新追加：已隐藏SDL鼠标指针，保留触摸输入。当前文件SHA256为
> `bc7f9139f1890350609dfc7067f6d6b18510564e0ec582c630547547dded00d1`。
> 以下ecde开头哈希是隐藏指针前的并行版；其余渲染/分辨率/服务设置不变。

## 最新结论

用户确认：**“显示正常，感觉更流畅”**。

保留原生1080×1920纹理、1920×1080横屏视觉、1:1输出及垂直同步。
从原先串行约50FPS提升到常见58–59.3FPS，动态负载较大时仍有约52–57FPS样本。
不是所有场景锁定60；启动扫表仍有低帧阶段，不要宣称稳定60。

系统标称60Hz，但直接读取DRM垂直刷新时间戳（30个间隔）得到：

```
VBLANK samples=30 mean=16.866ms median=16.863ms measured_refresh=59.289Hz
```

59.3FPS已经接近当前显示时序的实测刷新率。没有改变面板时序、超频、关闭同步、
降低分辨率，也没有伪造FPS统计。UI刷新率不等于每项BLE/OBD数据采样率。

## 实施内容

以前同一线程串行执行：Cairo约4ms + SDL上传0.2ms + 显示等待约15ms，总计约20ms。
现在把Cairo绘制放入一个受控工作线程，与上一帧的显示等待重叠：

1. 工作线程读取数据、做动画并更新局部Cairo画面。
2. 主线程等待画面就绪，调用SDL_UpdateTexture复制像素。
3. 复制返回后，主线程才允许工作线程修改下一帧CPU画面。
4. 主线程执行SDL_RenderCopy/SDL_RenderPresent/事件处理，同时下一帧CPU绘制可进行。

只有一张CPU画面、最多一帧待处理，不无限排队，不额外复制全屏像素。
所有SDL显示API仍在主线程；工作线程不调用SDL。
工作线程错误会传回主线程抛出，由原服务Restart策略处理；停止时发通知并等待退出。
日志中的paint/present现在互相重叠，**不能再把它们相加算帧率**。
FPS仍由主线程实际present完成次数/单调时钟窗口计算。

## 当前版本

电脑：`[LOCAL-PATH]`

手机：`/home/umeko/desktop-offline/gauge_sdl.py`

SHA256：`ecde1ed3f76972ebe36edbb3c6a3e4bfca53d7a1611d4fa142a904de2eb01f08`

两端备份：`gauge_sdl.before-pipeline60-20261018.py`，即原生1080p串行版，SHA：
`e92ef7c89460aacaad40c87fbbeb616d401ba2e6a2b13271fe5ff5f238c59083`。

手机继续使用同一个obd-gauge-kiosk.service、BLE地址和目录，没有改service配置。
`install_pipeline60.sh`做SHA预检、备份、原子替换、服务重启与失败回退。
已安装，不要把该一次性迁移脚本当通用更新工具反复运行。

## 测试与测量

- 本地WSL11项：10通过，原生SDL测试因WSL没SDL而跳过。
- 手机9项：全部通过，包括原生SDL像素读回、原生1080p几何、线程所有权、
  上传期间CPU画面不被修改、渲染线程错误传回主线程。
- 像素/增量算法未改；原增量与全量画面对照在本地继续通过。
- 实机日志确认native1080×1920 -> output1080×1920 1:1。
- 稳定运行时主进程PID2480（此PID只是当时值），服务active、NRestarts=0。
- 部分样本：59.3、58.3、58.3、55.3、54.3、51.8、57.2、58.3、59.3、58.8、59.3、57.8、58.3FPS。
- 最新top第二次2秒样本：仪表进程CPU33.0%（单核100%口径），整机CPU约10%，
  仪表RSS119572KiB约117MiB。不是CPU满载，无额外大块帧缓存。
- 启动日志16.1/43.7FPS属于启动扫表及全屏更新阶段。

证据文件：

- `pipeline-benchmark.log`：静止画面58.79FPS；动态demo约28FPS，
  double-buffer hint0/1无明显区别，因此没有添加该提示作为“修复”。
- `pipeline60-local-tests.log` / `pipeline60-phone-tests.log`。
- `pipeline60-install.log`：更新、哈希、1:1日志和起始帧率。
- `pipeline60-vblank-and-load.log`：真实vblank时间戳、运行帧率和CPU/内存。
- `probe_vblank.py`：只读DRM时间戳，不取得master、不更改模式，可用timeout5秒约束。

有限诊断用的 `bench_gauge_pipeline.py` / `run_pipeline_bench.sh` 会暂时停仪表、
跑有时限的测试后在EXIT恢复服务，不应在正常使用中反复运行。

## 回退（当前用户确认正常，不应无故执行）

```bash
cd /home/umeko/desktop-offline
cp -p gauge_sdl.before-pipeline60-20261018.py gauge_sdl.py.rollback
mv -f gauge_sdl.py.rollback gauge_sdl.py
sudo systemctl restart obd-gauge-kiosk.service
```

只回到此前约50FPS的原生1080p串行版；不要误用半分辨率或数字错乱阶段的备份。
长期运行、真实车辆极端更新场景和息屏唤醒不在本轮验证范围内。
电池、触控、背光、声卡、内核及系统裁剪均未修改。

SDL线程约束/缓冲参考：

- [URL REDACTED]
- [URL REDACTED]

## 后续补充：已找到可测GPU忙碌率的接口

此前仅检查标准devfreq/KGSL节点，因此说“GPU占用无法读取”；现已检查实际msm驱动源码，
发现debugfs perf接口可短时启用计数、关闭文件后自动停止：

`/sys/kernel/debug/dri/fd900100.display-controller/perf`

21:40左右12个约250ms样本：11.1、12.4、11.4、13.4、11.6、12.7、12.2、12.2、12.2、
12.2、11.5、12.8%，平均约12.1%。这是驱动%BUSY待处理任务时间比例，不等于各着色单元
利用率；ALUACTIVE/ALUFULL列也不是百分数，不要直接当作使用率。
测量结束文件已关闭、计数释放，服务仍active/NRestarts0，帧率58.3–59.3。

同时top第二次2秒样本：仪表33.3%单核口径，online CPUs0-3，折合四核总算力约8.3%；
整机user8.5%+system1.1%=9.6%。
证据：`pipeline60-cpu-gpu-status.log` / `pipeline60-gpu-busy-samples.log`。

GNU head在这个不可seek流读足行后可能报告Illegal seek，已保存的12个采样有效。
以后建议用有时限的Python with-open/readline读取固定行数再close，不要长期占有perf文件。
不要读取debugfs gpu文件代替perf；gpu是较重的状态抓取，不是利用率指标。

## 后续追加：隐藏鼠标指针

用户要求仪表只呈现触屏界面，不显示鼠标图标。窗口创建后只调用
`SDL_ShowCursor(0)`，再用`SDL_ShowCursor(-1)`验证state0；没有禁用触摸设备、
mouse/touch事件、输入驱动，也没有改BLE、像素尺寸、并行绘制或垂直同步。

当前SHA：`bc7f9139f1890350609dfc7067f6d6b18510564e0ec582c630547547dded00d1`。
两端备份：`gauge_sdl.before-hidecursor-20261018.py`（此前ecde开头并行版）。
本地12项测试11通过/原生SDL一项跳过；手机新增可见性测试和真实SDL像素读回均通过。
已部署，服务active/NRestarts0，实际KMS启动日志确认：
`Mouse cursor hidden (SDL cursor state=0)`，native1080×1920 1:1和BLE仍正常。
证据`hidecursor-local-tests.log` / `hidecursor-phone-tests.log` / `hidecursor-installed.log`。
只是隐藏光标，不代表已实现任何新的仪表触摸按钮或手势功能。
