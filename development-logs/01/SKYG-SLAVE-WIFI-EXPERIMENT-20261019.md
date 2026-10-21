# SkyGauge 从机：手机 Wi-Fi 接收实验

## 结论（未修复）

Vgate 直连已由用户实测可用。手机 SkyGauge 从机模式 UI / BLE配对读取流程已部署，但没有已验证的ESP-NOW接收，不能宣称从机功能完成。
用户确认 SkyGauge 主机通电在附近、未连接OBD。按本地源码，主机不依赖OBD连接而定期广播；实际v104二进制身份与该源码对应关系未验证。

## 找到的手机驱动限制

精确运行内核源码位于 WSL Mi4Build `/root/mi4-audio-work/linux`，构建输出 `/root/mi4-audio-work/build`，release `6.15.11-mi4-audio1`。
原 wcn36xx/main.c:
- configure_filter() 仅 `*total &= FIF_ALLMULTI`。
- add_interface() 只支持station/AP/adhoc/mesh，未实现monitor初始化。
- config() 无MONITOR专用处理。mac80211对外声明monitor不等于完整硬件监听。

## 隔离实验模块（已回退，勿开机安装）

复制原驱动目录至 PC `[LOCAL-PATH]`，未修改原内核源树。
修改main.c允许monitor vif、WANT_MONITOR_VIF、firmware INIT_SCAN HAL_SYS_MODE_PROMISC + START_SCAN、退出恢复scan状态、软件过滤允许OTHER_BSS/CONTROL/BEACON。
这些HAL调用是实验，不是已验证的完整monitor实现。不能将测试模块视为正式修复。

第一次卸载原驱动连带移除mac80211，直接insmod时报Unknown symbol；脚本改为先modprobe mac80211。
更重要：原DTS IRQ为GIC_SPI145/146 EDGE_RISING，但dxe request_irq改成LEVEL_HIGH，卸载后旧映射残留，重新probe报hwirq177 type mismatch / IRQ tx not found。原模块文件未改，已重启恢复。
实验dxe.c在free_irq后恢复IRQ_TYPE_EDGE_RISING，仅限这台Mi4测试，避免后续reprobe冲突。不得将硬编码IRQ类型推广到其他设备。

修正probe_sky_espnow.py动态读取phy index（模块重载后phy不再总是0）。
临时脚本 `test_sky_wifi_module.sh`：仅rmmod/insmod内存加载实验模块；EXIT清理监听接口并modprobe原模块；从不覆盖/lib/modules、不写boot。
实验模块 SHA256 `906d3e6d91ec452c0ddb9d242e968cef4a627d7b2366271a11817fafce37e693`。
原模块文件 `/lib/modules/6.15.11-mi4-audio1/kernel/drivers/net/wireless/ath/wcn36xx/wcn36xx.ko` SHA256 `2ba8d09ab949a7f93c49f6ebfa1497200e1b51256d012fabbd0784bf1279a6d6`。

## 实测结果

首次实验模块成功监听channel1，10秒收到494帧，全部subtype0x80(beacon)，0个Action/ESP-NOW。单元合成V5帧解析测试通过。
之后channel1..13各监听2秒，按顺序1,6,11,2,3,4,5,7,8,9,10,12,13。每信道分别收到76,36,136,88,65,49,35,24,16,106,66,80,81个帧，全部beacon；没有Action或SkyGauge魔数包。
这只能证明接收信标路径有效，不能证明固件已放行Action，也不能证明主机实际上广播了数据。缺少独立正向对照，不能断言全部根因在手机或主机。

## 当前安全状态

实验模块已卸载、原模块已加载，wlan0 DOWN、无skymon0；仪表和Bluetooth服务active。/lib/modules原文件未变，不含开机实验服务。电量/背光/音频/boot保持不变。
独立phone文件 `/home/umeko/desktop-offline/wcn36xx-sky-test.ko`、`test_sky_wifi_module.sh` 仅供手动实验；不要无意识再次执行或设为开机任务。

## 下一步需要对照

用已知能接收的SkyGauge原版从机，或获得用户授权后用ESP32接收器，确认主机的实际Wi-Fi MAC、信道、广播payload版本及长度。不要假定COM8就是可刷的空闲ESP32，不得擅自覆盖其他项目固件。
如对照能收而Mi4不能收，再查高通firmware Action RX过滤/接收初始化；不要仅修改UUID、PID或宣称配对成功等于数据成功。原Prima源码可参考Android官方源码站，需核对相同硬件/firmware API，不可照搬更新的qcacld/WMI命令。

## 无额外设备继续诊断：驱动内部计数

用户没有原版从机/闲置ESP32，要求继续纯手机方案。
在隔离实验txrx.c增加只读模块参数 rx_total/rx_action/rx_beacon/rx_drop，在BD进入Linux、帧头解析后及drop路径计数，不记录任何无关设备地址/内容。
实验10秒：驱动层 rx_total=385、rx_beacon=385、rx_action=0、rx_drop=0；用户态监听377帧均beacon（差额为监听socket建立前收帧）。说明本轮Action帧没有进入该Linux RX解析路径，不是Python V5解码器误丢；仍不能区分主机未广播与无线固件过滤。
最新实验模块SHA256 `f3c5ecc067fc1854ae83e7d7c7d56c38f18cb488aae57b3fb0e6e459a5f685ee`。试验后已回退原模块、wlan0 DOWN、无临时监听；仪表/蓝牙active，未设开机加载。
另清理未配对目标SkyGauge `[BT-ADDRESS]` 的BlueZ缓存（未清理Vgate），只读重新发现15秒仍TimeoutError，尚未读到Wi-Fi配对MAC。`probe_sky_pair_once.py` 已放PC/手机运行目录，严格只读1FF9/0003。
已请用户给SkyGauge断电重上，保留MASTER设置，下一轮核验BLE服务和Action接收。不得将缓存清理/添加计数描述为已修复。

## SkyGauge重启后：绑定成功，核验实际固件

用户已给主机断电重上。手机自动读到并保存主机Wi-Fi MAC `[BT-ADDRESS]`，BLE地址 `[BT-ADDRESS]`。蓝牙配对读取已实测成功。
只读1FFA identity成功：board Waveshare ESP32-S3-Touch-LCD-1.85、ST77916、360x360、flash16MB、PSRAM8MB；firmware build_tag `main-104-9c3fa1b27e9d`、branch main、count104。
Git提交完整SHA `9c3fa1b27e9ddd3114ca29386615dd7406aa470e`。本地commit/tree存在，espnow_link.c和app_main.c是缺失promisor blob（禁lazy fetch时bad object），故通过GitHub网页只读核验固定提交；没有下载GitHub文件，也没有修改本地仓库ref。
准确版本源码：https://github.com/steveEcode/obd_brz_gauge/blob/9c3fa1b27e9ddd3114ca29386615dd7406aa470e/main/bsp_obd_dsp/espnow_link.c 。确认channel1、V5、未连接OBD也无条件每100ms广播，故此前V5格式假设无误。

重启后首次驱动计数 total448/beacon448/action0/drop0，用户态443beacon。
随后在隔离实验模块中补标准HAL CONFIGURE_RXP_FILTER_REQ(83)清零setting/enable，处理响应103，并在monitor INIT_SCAN后调用，firmware返回result0。结果total559/beacon559/action0/drop0。
又补 `wcn36xx_smd_update_cfg(MCAST_BCAST_FILTER_SETTING,0)`（CFG70），该接口和RX filter reset均返回0。结果total570/beacon570/action0/drop0，用户态561beacon。仍无ESP-NOW。
原厂INI `McastBcastFilter=3` 有过滤广播的注释，但主线驱动不读此INI，**不能将INI值3直接认定为根因或只改INI冒充修复**。本轮通过HAL临时配置验证，无持久INI修改。
最新实验模块SHA256 `88641e0530681f537a575291b3418576542f6a26494a02238f9d1935a672799d`。所有测试结束已卸载、原module hash仍2ba8d09...，wlan0 DOWN、无skymon0、Bluetooth/kiosk active。
wcnss.mdt ELF头确认32位小端ARM（e_machine40）；未修改、未替换任何wcnss.b*固件或NV校准文件。
当前不能证明高通闭源固件一定过滤Action（也不能排除实际主机广播行为差异）；不要将HAL成功ACK当作ESP-NOW成功。若下一步涉及修改/装载无线协处理器固件，风险与普通Python/模块实验不同，须明确说明Wi-Fi和蓝牙共用协处理器，先备份并另行取得用户同意，不擅自替换。
