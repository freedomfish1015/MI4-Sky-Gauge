# 开发历史导读

原始记录保留在项目持有人电脑上，本仓库保留其脱敏副本。494份记录并不都是成功结论；同一天的后续记录可能已经回退早先实验。

| 阶段/问题 | 有用结论 | 到哪里查 |
|---|---|---|
| 早期系统移植/音频 | ALSA路由、vreg-boost时序、S16LE协商分别造成不同静音；必须播放中采样，不能盲增益 | development-logs/05，AUDIO1、RESULT与speaker日志 |
| 电池/SOC/红灯 | OCV表曾有10倍单位错误；低电压/充电功率与SOC显示需分开看 | 01中的BMS、BOOT-RED-LED、CHARGE记录；硬件最终DTS |
| SDL画面 | 静态导出正常不代表增量路径正确；脏框与数值位置不符会消失 | 01中的渲染、1080p、pipeline及UI测试记录 |
| 触摸/设置 | 裸KMS环境input权限影响手势；列表上下滚动与页面左右滑分离 | SETTINGS、touch、scroll相关记录 |
| Sky互联 | BLE连接、RaceChrono遥测、ESP-NOW主从不是同一协议；最终用手机转发ELM原始流 | ELM-GATEWAY、SKYGAUGE、TELEMETRY记录 |
| 延迟 | 保持单所有者队列、被动解码和局部UI刷新，不能用多线程交错查询掩盖延迟 | 01中的latency/forward日志和测试 |
| GNSS/北斗 | 有LOC服务、看到卫星、真正fix三件事要分开；记录系统类型和used/observed | BEIDOU、SATELLITE、GNSS、GPS记录 |
| 挂起/关机 | remoteproc/uptime连续可以证明未重启，不直接证明星历每项都保留；最终正常关机与调试待机分开 | power、suspend、红灯记录 |
| 启动图/视频 | 取消视频、光标持久化、Logo接管经过多轮回退；quiet改动曾导致黑屏 | DIRECT-STARTUP、CURSOR、CONTINUOUS-LOGO及录像分析记录 |
| 原厂兔子 | 只修Fastboot绘图分支4字节，正常Sky图保持；原厂Fastboot仍有参数空缺 | 04中的修复README/读回日志 |
| 充电后蓝牙禁用 | 临时rfkill状态持久化，但原意图在/run丢失；R2保存跨重启日志恢复原状态 | 02目录 |
| LOG导出/小程序 | 看到曲线不等于写文件；记录开关/行程联动与CSV按需导出分别验收 | 03目录及API文档 |
| 发布 | 已用设备稳定 != 新机整机安装通过；源码开源 != 厂商/素材已再授权 | 当前README、KNOWN-ISSUES、许可说明 |

## 日志阅读顺序

1. 先看当前README和metadata的版本/哈希。
2. 通过development-logs/index.json找文件；01为仪表主线，02为R2蓝牙，03为传输，04为兔子，05为音频。
3. 同时阅读成功、失败、rollback/restore/verified，不按单个文件名判断现状。
4. 被标记的URL、MAC、IP、坐标、凭据和编码传输行已经删改；不是可直接重放的原始抓包。
5. 要复现问题时重新采样，并在分享前脱敏，绝不运行旧日志中的任意命令。

账号/音乐登录、cookie、私有传输载荷等24项未纳入公共日志；源码索引保留排除原因。在线音乐已放弃，不将其认证失败当作当前仪表功能缺陷。
