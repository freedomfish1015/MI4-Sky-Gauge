# WCNSS 运行时接收过滤取证

> 后续：三机同场后手机已通过主机1FF8持续收到BLE遥测，参见 `SKYGAUGE-BLE-TELEMETRY-CONFIRMED-20261019.md`。ESP-NOW未接通与BLE已接通是不同结论；优先验证现有BLE实车数据，不要把旧服务发现结果当成主机不支持BLE遥测的永久证据。

## 本轮结论

尚未接通 SkyGauge。新增只读 HAL 寄存器诊断后，实测证明上一轮候选不仅文件已加载，而且 Action 屏蔽位及独立 subtype 配置确实应用到了运行时寄存器。不能继续把失败归因于补丁没生效；仍需区分其它硬件/固件接收处理与主机实际广播。

无持久固件/驱动替换；测试结束恢复原 firmware、原 module，启动仪表。未动 boot、NV、SkyGauge、OCV、WLED、音频。

## 只读命令的依据

原固件 b06 内三元组调试表：

- `0x0d5341ac`: id 7，字符串 `HAL:Read Register <address>`，处理函数 Thumb `0x0d2d78fb`。
- 紧邻 id 8 是 Write Register，**本轮没有调用**。
- 读取处理函数 `0x0d2d78fa` 调 `0x0d2ba4fc` 读取给定地址，将结果按小端 4 字节写入响应缓冲区，未发现写寄存器调用。

本轮复用主线 wcn36xx 现有 `wcn36xx_smd_dump_cmd_req`（HAL 请求 121 / 响应 122），只发 id7 给下列六个已定位的配置寄存器。隔离实验驱动在响应长度检查后打印这 4 字节；不采集无关设备包内容。

`inspect_wireless_dump_table.py` 为纯离线只读表定位脚本。

## 原固件运行时基线

测试 `mi4-wcn-readonly-regs`，20:32:40–20:32:55，信道 1，15 秒。

| 地址 | 原固件值（小端解释） | 定位用途 |
|---|---|---|
| fb080800 | 0900030f | RXP 配置 |
| fb0808f0 | ffffffff | 系统过滤字 0 |
| fb0808f4 | c77ffedf | 系统过滤字 1（包含管理帧 subtype 位） |
| fb080914 | 0008f200 | subtype5 Probe Response 配置 |
| fb080920 | 0008f200 | subtype8 Beacon 配置 |
| fb080934 | 00023600 | subtype13 Action 配置 |

用户态 702 帧全部 Beacon，驱动 707 total/beacon，Action=0、drop=0。20:32:56 恢复完成。

## Action 路由候选运行时核验

用相同只读诊断驱动，临时加载此前的 `candidate-action-route-rx`；没有生成新一版代码补丁。

测试 `mi4-wcn-route-regs`，20:33:29–20:33:49，信道 1，20 秒。

| 地址 | 候选值 | 与基线差异 |
|---|---|---|
| fb080800 | 0900030f | 无 |
| fb0808f0 | ffffffff | 无 |
| fb0808f4 | c77fdedf | Action subtype13 屏蔽位已清除 |
| fb080914 | 00000e00 | Probe Response 未再执行原扫描配置 |
| fb080920 | 0008f200 | Beacon 保持 |
| fb080934 | 0008f200 | Action 已应用与 Beacon 相同的扫描接收值 |

用户态 920 帧全部 Beacon，驱动 total/beacon=931，Action=0、drop=0，SkyGauge=0。

20:33:51 自动恢复 `wcnss.mdt running`，bluetooth 与 obd-gauge-kiosk active。

这证明两个候选修改点已经实际执行，而不是因子目录加载失败/指令未走到而无效。也再次表明不能把上述配置成功当作完整 ESP-NOW 接收成功。

## 工具和回退

只读实验 module SHA256：`501cc055417c48965e63fefb2000692cafba097bf1ef3bc3cc5c4730d86ba060`。

- PC 编译输出：`wcn36xx-monitor-test/wcn36xx.ko`，这是新增诊断版，不再等于早期实验 ko。
- 手机新增隔离文件 `/home/umeko/desktop-offline/wcn36xx-sky-readonly-regs.ko`。
- 手机旧隔离实验 `/home/umeko/desktop-offline/wcn36xx-sky-test.ko` 保留未覆盖。
- 磁盘内 stock `/lib/modules/6.15.11-mi4-audio1/kernel/drivers/net/wireless/ath/wcn36xx/wcn36xx.ko` 不变。
- `test_sky_wifi_readonly_regs.sh` 用于原固件下临时加载诊断模块；只应由有 ExecStopPost 的临时服务运行。
- `trial_wireless_action_fw.sh` 新增 `WCN_TRIAL_DIAGNOSTIC=1` 才选择只读诊断 module；默认仍选择旧实验 module。
- 临时服务设 RuntimeMaxSec（90 或 100 秒）、TimeoutStopSec=30，独立 ExecStopPost 调 restore；不设开机启动。

不应未经确认调用调试表中的其它命令，表里包含写寄存器、清内存、强制崩溃等危险项。当前只核验了命令7的只读行为；不要把所有名含“dump”的命令都当作只读。

## 下一步的证据要求

重点查 Action 的后续地址/BSS 关联、硬件接收条件和固件 MAC 分发/上送；不能凭“有 Beacon”就证明主机广播一定已被物理接收。实机主机广播仍缺少独立正向对照。不要猜测写入未知寄存器位，也不要绕开 source-MAC 和版本验证向仪表填假数据。
