# BLE转发低延迟优化（2026-10-20）

> 随后新增GPS离线轨迹页面，gauge_sdl.py/gauge_settings.py的最新哈希见同目录GPS-ROUTE-PAGE-20261020.md。下述低延迟逻辑保留，其余转发文件不变。

已部署，手机两服务active、NRestarts=0，真实双BLE台架继续出数。未修改Sky固件，未重刷AI Passport，未改boot/电池/GPS/音频等驱动。

## 同机同台架12秒HCI抓包比较

| 指标 | 原版 | 手动调参验证 | 最终部署后重连 |
|---|---:|---:|---:|
| Sky链路主机侧请求到通知输出平均耗时 | 88.80ms | 34.11ms | 35.28ms |
| 上游ESP链路平均请求回复耗时 | 76.50ms | 22.12ms | 21.82ms |
| 转速查询平均间隔 | 393.11ms | 130.67ms | 140.71ms |
| 转速查询中位间隔 | 400.00ms | 120.00ms | 134.99ms |
| 转速查询最大间隔 | 1000ms | 300ms | 315ms |

最终约60%降低主机观察的请求回复耗时，转速查询刷新约2.8倍。
这些是**主机HCI边界**测量，不等于屏幕到屏幕的完整物理端到端延迟；通知输出后的空口/主表渲染未计入。
不保证实车Vgate有同样绝对数值；ECU、适配器和主表调度仍有自己的耗时。

证据：elm-latency-baseline-20261020.log、elm-latency-radio-fast-20261020.log、elm-latency-deployed-20261020.log。
测量脚本measure_elm_latency.py，手机另存latency-*.json；只输出统计，不导出原始车况包。

## 修改

1. 新增elm_radio.py：只对当前上游和固定Sky主表的LE句柄请求7.5–15ms间隔、latency=0、监督超时4秒。
   - 由root外设服务每2秒检查连接；每个新连接申请一次，失败最多3次，不中断正常转发。
   - 通过真实hcitool con动态找句柄，不写死10/11。不会调整其他蓝牙设备。
   - 参数只是请求，对端可能不接受；日志accepted只表示命令成功，不代表测得具体协商值。
   - 最终重连句柄12/13再次自动申请成功，并重新抓包确认加速保留。证据elm-latency-auto-verify-20261020.log。
2. 去掉每个下行ATT分片固定2ms sleep，保留asyncio.sleep(0)调度机会、顺序、20字节分片和队列上限。
3. 收到完整ELM回复后，优先发往Sky，随后立即发布手机被动解析结果，不再等旧100ms显示刷新定时器；定时器仍负责失效检查。
4. 仅Sky转发模式且开机扫针结束后，RPM/车速大幅变化使用40ms时间常数的快速收敛，保留小变化原有最小步长直接更新。
   - 低FPS下也不会因固定每帧150rpm/3kmh产生长时间追赶。
   - 原有启动扫针、布局、纯手机直连动画保持不变。

短BLE间隔更频繁唤醒无线模块，可能略增功耗；本轮没有测量耗电变化。不做额外ECU轮询，不预测/伪造数据，也不改Sky原PID周期。

## 文件SHA256（部署版本）

- gauge_sdl.py：9e730535aa3e49f933c7ae4ad74fb1efeae568e77da397e10ad21298b0d6433b
- elm327_ble_bridge.py：32f8002c2b180adb40b4623fac6bad925a5da7c5fd97a29b401f8bc38353a087
- elm_bridge_ipc.py：f75b1b35371440c84433dfe99cbf1e5ee10821f9ad835d265cb4c7f5ce5581b6
- gauge_elm_forward.py：c28bb52a30bb1403404209374891646c9e776ced8cdaa90aefb3f34d1bc46d8e
- elm_radio.py：031c2e7ac455ac1aec713e40fd7d0337ffcc82264f858f65514db4cc7ec7b5e3

应用目录同ELM-GATEWAY-HANDOFF-20261020.md，其他文件未改。
桌面相关50项回归48通过/2跳过；额外新增radio白名单测试和转发组11项通过。并非全仓测试声明。

备份：`/home/umeko/desktop-offline/backups/elm-latency-before-20261020-014533`。
部署脚本install_elm_latency.py对旧版本逐一哈希校验，保留用户设置和原所有权。
回退需停obd-gauge-kiosk/mi4-elm-advertiser，恢复备份中的4个旧文件再启动；新的elm_radio.py不再由旧桥接脚本导入。
当前连接调参是运行时参数，回退后重新连接恢复对端默认协商；没有写控制器固件/NV。
