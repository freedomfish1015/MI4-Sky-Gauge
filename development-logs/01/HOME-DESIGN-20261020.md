# 主仪表界面重设计（白色／冰蓝）

重新划分层次：中央保持大 G 表，左侧独立显示车速、右侧独立显示转速及自下而上的进度轨；四角为可自定义的数据卡片。清除原先粗重的六边形进度框、外框和无数据含义的卡片装饰条，保留细六边形与淡绫波丽图作为主题线索。

## 后续调整：加粗进度轨，取消车速红区

两侧进度轨初次由 5 增至 10，用户要求再加粗加长后，最终宽度为 16 逻辑像素（原生渲染宽 48 像素），中心线由 y=124…237 延长到 y=116…244（长度 128、原生 384 像素，不含圆头），刻度同步外移，脏矩形同步扩大以覆盖粗圆头。车速轨背景不再带粉红色段，活动填充全量程保持冰蓝渐变；转速轨红区和转速报警保留。没有改变车速量程或四个窗口绑定。只更新插件并重启 kiosk，motion PID 3712 保持不变，已有累计 G 区域不会因此清空。

最终版安装前的插件备份：`/home/umeko/desktop-offline/backups/home-bars-long-before-3yiblbbb/gauge_home.py`（10 宽版）；最初细轨版备份：`/home/umeko/desktop-offline/backups/home-bars-before-a4c32q91/gauge_home.py`。回退仅需停止 kiosk、恢复对应插件、启动 kiosk。安装器 `install_home_bars_20261020.py` 校验旧/新插件 SHA，避免覆盖其他修改。

10 宽版电脑 63 项回归测试通过（1 项跳过），手机 45 项通过，其中新增满量程车速不转红、转速仍转红、背景车速轨无红区验证。最终加粗加长版另增加脏矩形包含完整粗轨的边界测试。合成预览 `home-thick-long-bars-preview.png`。最新安装日志 `home-bars-long-install-20261020.log`，手机回归和服务日志 `home-bars-long-device-tests-20261020.log`。

最终版电脑 64 项测试通过（1 项跳过），手机 6 项主桌面专项测试通过，kiosk active、NRestarts=0、motion PID=3712。专项测试并发期间的 FPS 日志不能作为日常运行性能依据。

后续复查（22:44:23–25）静置时已恢复 58.9–59.4 FPS、paint≈2.1ms、upload≈0ms。此前测试后短暂出现 26–28 FPS，原因未确定，没有通过更改硬件频率/温控来掩盖；未修改上述逻辑即可恢复。

卡片为 154×90 逻辑像素，位置 (14/472,18/252)；车速数字 43、转速 31、卡片 30。继续原生 1920×1080 渲染、字形缓存、静态图缓存与脏矩形更新，没有改用放大截图或新合成器。

`gauge_home.py` 是显式界面插件，由 `gauge_sdl.py` 在类定义后加载。只替换静态绘制、两侧进度轨、数字及其脏矩形位置。主循环仍为原实现；外层补充零值→缺失、超量程数字变化的刷新区域，防止旧数字残留。各数据绑定、报警阈值和手势不改。

## 手机实际部署

- `gauge_home.py` SHA256 `f5321590f768bf89acfa44c8579d9da1a472516be0de434f5531231ba85fa536`
- `gauge_sdl.py` SHA256 `a541e6c531255652d42a9f49c8bb255b6b34e2df5d1e1e0d04074ae1acfe1dfc`
- 目录 `/home/umeko/desktop-offline/`
- 旧主程序备份 `/home/umeko/desktop-offline/backups/home-design-before-q4sjuqub/gauge_sdl.py`

`install_home_design_20261020.py` 严格检查旧 main SHA `c6b928a915a3fb14e7eaa39283122e1e38f890f8d0303a593884bd555a272037`，然后只调整三处字形大小和一处插件加载钩子。**没有把电脑上包含待部署调试息屏逻辑的整个 gauge_sdl.py 覆盖到手机。** 后续部署调试息屏功能必须针对新的手机主程序重新合并，旧哈希安装器应拒绝覆盖，不能强行绕过。

本次只重启 kiosk，motion PID 前后同为 3712，不会因部署清空累计 G 区域。没有修改 GPS、加速度自动回中、区域保留、5 秒拖影、蓝牙网关、充电、电量、锁屏或 boot。

回退：停止 kiosk，将备份的 gauge_sdl.py 恢复至应用目录，再启动 kiosk；新 gauge_home.py 可以保留但不会被旧主程序加载。无需重启 motion 或手机。

## 验证

电脑 61 项回归测试通过（1 项跳过），包含新布局边界、缺失值/温度报警/缩小区域时增量与整帧像素一致、超过量程时数字继续刷新，以及已有窗口、手势、轨迹/LOG 联动。

手机测试与安装输出：`home-design-device-tests-20261020.log`。
手机 43 项测试全部通过；服务 active、NRestarts=0，motion PID 仍为 3712。
当时静置、未连接台架蓝牙源（[BT-ADDRESS] 不在场）的运行日志约 58.9–59.4 FPS；这不是车况实时全负载帧率承诺。见 `home-design-live-verify-20261020.log`。
`home-redesign-preview.png` 为合成数据视觉预览，不是真实车况。
