# Mi4 红灯闪烁、偶发无法启动：只读排查

2026-10-20，手机已恢复开机，COM10。此次未刷写、未修改运行配置、未请求挂起/重启/关机、未提高充电参数。仅上传只读采样脚本并保存电脑诊断输出。

## 已确认

- 当前连续 12 次 PM8941 VBAT ADC 校准换算约 3.2541–3.3299 V，期间 BMS capacity 固定 99%。使用 625/1250 mV 参考及 VBAT 1:3 分压换算，属软件 ADC 估算，不是万用表实测。
- USB online=1、smbb-bif status=Charging；这些状态不能证明净充入电池的电流。USB charge_control_limit=1500000 是设定上限，不是实际电流。
- OCV 表 145 点范围 3000000–4305000 µV，先前除 10 修正仍在；FCC 范围 3230000–3410000 µAh。不能用“OCV 表丢失”解释此次 99%。BMS SOC 算法/状态仍需排查，不能据电压直接给出精确剩余百分比或电池健康度。
- 前一 boot fb2f2ce04ab14851b7c23bbc34a94033 日志止于 16:25:35，无正常关机尾段；当前 boot 起于 16:41:19，EXT4 recovery complete、journal unclean shutdown，支持上次非正常结束。无法区分欠压、强制重启、内核卡死。再前一 boot 在 15:51:09 有完整 poweroff 记录。
- 前一 boot obd-power 日志只有在线/idle，无倒计时关机证据。未找到可用 pstore；不能排除未落盘的 panic。

## 用户提供的 s2idle 线索核对

当前实际 /usr/local/lib/obd-power/gauge_power_service.py 调用 systemctl --no-block poweroff，不是 suspend。修改时间 2026-10-20 13:25:29 +0800，SHA256：

05543f3ffe769a219b4f5993a59efbcfba7ba50fd2a0e8f7fe71d7f112756533

文件注释自述 s2idle 曾尝试、因耗电已回退。这只是修改者的说明，不是本轮测得的待机电流。当前只支持 [s2idle]，本次 boot suspend success/fail 为 0/0。因此不能说当前仍在执行那份挂起方案。

短时挂起恢复、remoteproc running、QRTR 节点一致不证明长期待机功耗合格，也不直接证明 GNSS 星历缓存内容或 5–15 秒定位保证。若旧方案长期耗电且 SOC 假高，可能造成亏电和启动时进一步掉压，但尚无故障当时电压/电流曲线来定案。

另见 15:46:14–28 外部电源 online true/false 密集变化，可能是线缆/接口/电源抖动或测试注入；需询问操作背景，不能直接判定充电口损坏。

## 当前判断与下一步

优先怀疑实际低电压 + 电量显示假高；旧挂起策略可能是耗电诱因，但当前已回退，不能作为全部原因。电池老化内阻、线材/电源能力、USB 接口、充电驱动需进一步区分。

先用可靠兼容 5V 充电器及完好线材充电 15–30 分钟，避免反复启动和高负载压测；再比较校准 VBAT 是否持续升高。故障复发时记录是否能进 Fastboot、所用电源、灯闪节奏及 PC USB 枚举。电压仍低或掉压明显需实测电池端电压/内阻；不要绕过欠压/温控保护。

参考小米官方：[URL REDACTED] 及 [URL REDACTED] ，低电量时可能无法启动并 LED 闪烁，建议先充电后再试。

证据文件：boot-red-led-initial/hardware/previous/adc/voltage/errors/final-check/power-policy/suspend-history-20261020.log（同目录）。电压有效输出为 diagnose_boot_power.py 采集版本。
