# 北斗检查 / 2026-10-20（上海时区）

## 最新进展（优先读）

已经打通 **真正的 modem EFS 只读访问**，不再受libqmi未封装接口限制。读取
`/nv/item_files/gps/cgps/me/gnss_config`得到4字节 **`07 00 00 00`（LE32=7）**。

**尚未找到与这版modem匹配的NV位定义，不能仅凭7断言GPS/GLO/BDS全开。** 不得把QMI测量报告掩码或Quectel AT枚举直接套用到NV值。没有执行任何NV/EFS写入，尚未宣称开通。

### 访问方式与实测

`diag_gnss_config_read.py`：按remoteproc name=`fc880000.remoteproc`定位modem（当前remoteproc2），仅临时绑定它的 `DIAG` RPMSG到已存在的rpmsg_chrdev，自动出现/dev/rpmsg0。

向该设备发送原始DIAG `4b 13` 子系统的 EFS OPEN(2，O_RDONLY=0)、READ(4，64字节/offset0)、CLOSE(3)。响应带HDLC CRC和7e结尾，需要解转义并验证CRC。不是USB DIAG，不改USB gadget、不重启modem。

首次读取在OPEN已成功时因未处理HDLC尾部而中止，未发送READ；未取得可解析fd，故未发CLOSE，随后关闭channel/unbind。第二次补好HDLC解析，OPEN/READ/CLOSE都收到有效响应，临时绑定和driver_override均恢复。

成功记录 `diag-gnss-config-read2-20261020.log`（本目录）：

```
OPEN 4b1302000000000000000000
READ 4b1304000000000000000000040000000000000007000000
GNSS_CONFIG_BYTES 07000000 length 4
CLOSE 4b13030000000000
RPMSG_BINDING_RESTORED
```

代码只允许读相关EFS命令，没有写函数。继续工作前保持这个只读工具不变；真正修改必须有匹配位定义、原值备份和回读校验，不能为了响应用户催促乱写。

### QMI检查的更正与结果

旧`qmi_raw.py`不可用：它用6字节头/8位transaction、硬编码LOC端口16、GET_NMEA_TYPES=0x000a、到CTL发supported，这些不可靠。新`qmi_loc_readonly.py`用7字节`<BHHH`服务QMI头，通过Qrtr动态发现LOC在node0 port19。

GET_SUPPORTED_MESSAGES=0x001e成功，返回支持001e/001f/0020..0088。支持列表不等于所有功能实际可用。

GET_ENGINE_LOCK=003b：运动服务运行时LOC ENGINE_BUSY；停mi4-motion后成功，lockType=1（NONE，未锁），不是MI锁。GET_NMEA_TYPES=003f停服务后读到0x3f。GET_LOW_POWER_MODE=0041只有ACK，未获完整indication，不能判定低功耗状态。

有界`gnss_constellation_trial.py`临时定位会话：baseline15秒仅NMEA60/position15，无GSV/SV信息；停止该会话后SET_GNSS_CONSTELL_REPORT_CONFIG=0088，TLV10 uint64=7，返回LOC GENERAL_FAILURE=1。随后的空闲对照mask=1(GPS)、4(BDS)、7也全部GENERAL_FAILURE。因此不能把失败归因为只有北斗被禁止。

以上是测量报告配置，不是NV星座开关。无成功配置，无永久更改。systemd ExecStopPost和shell trap均已恢复mi4-motion。相关日志：qmi-loc-readonly-20261020.log、qmi-loc-idle-readonly-20261020.log、gnss-constellation-trial-20261020.log、gnss-constellation-controls-20261020.log。

目前剩余关键问题：匹配modem固件的NV `gnss_config`位定义/运行时BDS允许状态，而不是继续改0x88。

## 结论

尚未证明北斗已启用，也未证明北斗被关闭。本轮没有写基带NV、没有修改星座配置、没有刷boot或modem。

小米官方参数 [URL REDACTED] 明确列出北斗定位，属于硬件产品支持证据，不代表当前Linux/基带配置已启用。

00:14检查时定位服务正常运行，GPS只有1颗弱信号，NMEA GP SNR约19–21，未定位。用户同意移到窗边；后续约48秒观察为0卫星，没有北斗证据。弱信号/未见卫星不能判定星座关闭。

## 修复了星座统计错误（不是北斗开关）

实机GI结构 `Qmi.IndicationLocGnssSvInfoOutputListElement` 暴露字段system、signal_to_noise_ratio_bhz等，没有get_system()方法。旧mi4_gnss.py调用get_system()并吞异常，导致systems始终缺失。

仅修改mi4_gnss.py：使用item.system.value_nick、空报告清空systems、读取报告失败显示satellite_report_error。新增test_mi4_gnss.py三项通过。本地/实机修改前hash一致，核对未在录制轨迹后备份并部署，restart mi4-motion成功。没有改仪表/IMU代码或历史轨迹文件。

- 实机备份 `/root/mi4-gnss-before-stats-20261020-XFTPf2/mi4_gnss.py`
- 原SHA256 `fafe19a1f284aeeba5d39e95329eb39e59b69a7435363ca588d93f917aa6f3d0`
- 部署SHA256 `00887162b18ccc577da0efeb799195622690e6495f047ccf710ebe6b2cbaa014`
- 实机运行文件 `/usr/local/lib/obd-motion/mi4_gnss.py`
- 上传副本 `/home/umeko/desktop-offline/mi4_gnss_beidou_stats.py`

gnss_probe.py旧独立诊断也使用错误get_system()，未部署/未修。其BEIDOU_OFF=未见北斗的判定不可靠，勿引用为关闭证据。gnss_beidou_check.sh同理，不要盲跑或信其OFF标签。

## 用户既往轨迹检查

用户说“今天使用过轨迹记录”，检查覆盖10月19日至20日（对话已过午夜）。手机`/var/lib/obd-motion/tracks`有三组CSV/GPX，均为10月19日文件：

| UTC文件前缀 | CSV/GPX点数 |
|---|---|
| 20261019T080645Z | 0 |
| 20261019T095509Z | 348 |
| 20261019T100242Z | 2 |

[LOCATION-BEARING LINE REMOVED]

系统journal筛选GNSS/compass/beidou/bds/satellite仅发现会话启动信息，无历史卫星明细。

证据日志PC：`beidou-track-schema-check-20261020.log`、`beidou-window-observation-20261020.log`，都在本目录。

## 后续

先在开阔环境观察修正后的systems和原始QMI报告；compass或BDS卫星证据与实际used-in-fix应区分。没搜到北斗不等于关闭；仅有报文输出也不等于已参与定位。

当前libqmi1.35.2的ClientLoc无现成星座配置接口。AOSP公开的SET_GNSS_CONSTELL_REPORT_CONFIG是测量报告配置，不能当作启用北斗接收的开关。不要盲写NV或套用Quectel AT命令（小米不是该模块）。若继续实现设置接口，先找到匹配这代modem的协议和可回读原配置，再最小变更及验证。
