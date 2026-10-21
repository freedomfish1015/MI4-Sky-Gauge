# Mi4 电量上报修复（已部署，无 boot 刷写）

## 直接证据与根因

2026-10-20 20:20 后原驱动仍报 99%，电压约 3.82–3.87 V。当前内核 6.15.11-mi4-audio1 的内置 qcom-bms 来自 pm8941_bms.c，不是旧文档里的 qcom_bms.c 路径。

代码 bms_read_ocv 把 REG_BMS_OCV_FOR_SOC_DATA0 的 u16 ADC 原始编码直接乘 1000，当作微伏。实测原始编码 **37899**，旧结果 **37,899,000 µV**，高于已修正 LUT 的 4,305,000 µV 表顶，因此容量基准被钉为 100%，再受库仑计影响显示 99%。先前 OCV 表除 10 修复仍在，但暴露了驱动的原始值换算缺陷；只改设备树不足以完成修复。

修正版经同一 VADC 提供器标准 IIO 通道读取 REF_625MV/REF_1250MV，按照 VBAT 1:3 分压校准。原始 37899 校准为约 **3,881,196 µV**。仍使用硬件 OCV + 库仑计算法，不是充电端电压直接映射百分比。

## 修复项

- BMS OCV 原始 ADC → 校准微伏；新增标准 voltage_now、voltage_ocv。
- 库仑计零初始化、LE 字节序、36 位符号扩展、回绕扩展；精确化简转换因子 253183/982920000，分段运算避免长时间累计乘法溢出。
- 温度/LUT 两端边界防越界、每列独立限幅，capacity 限幅 0–100。
- BAT_THERM raw 不是毫摄氏度：暂用名义 25°C LUT，**不伪报温度**。充电芯片硬件温控不修改。
- status 从实际 smbb-bif 查询，不依赖缺失的 supply 拓扑。Charging 表示充电器驱动状态，不保证净电流充入电池。
- mutex 在首次使用前初始化；容量与 OCV IRQ 状态串行化。
- 不再调用旧驱动未验证的 CC 清零寄存器偏移；收到新 OCV IRQ 时做软件 CC 基准归零，不清硬件计数。
- 没有修改充电电流、电压上限、温控、欠压保护或任何 PMIC 充电配置。

## 部署

外部模块 **mi4_bms_fixed.ko**，驱动名 mi4-bms-fixed；仅将 battery@4000 从内置 qcom-bms 可回退地重新绑定。运行中与下次开机均由 root-owned oneshot 服务处理；不替换整内核，不改设备树或 boot 分区。

- /usr/local/lib/mi4-bms-fixed/{mi4_bms_fixed.ko,mi4_bms_fixed.c,bms_fixed_init.py}
- /etc/systemd/system/mi4-bms-fixed.service（enabled，active/exited）
- PC 源码：[LOCAL-PATH]
- 模块 SHA256：b0739e78c4450cf753df805d93aee7dc320a591699bc4c140548363bf8a1632a
- 安装快照 /home/umeko/desktop-offline/backups/bms-report-before-95ocqqk_（临时修复已运行时的状态，不是原始内核二进制备份）；原驱动始终保留在当前内核。
- boot SHA 应保持 1852dd1bda97b9bee008ccf46165db11c17e9b35dd40d18255a0c665157e8a1a。

首轮运行：capacity **56%**，voltage_now 约 3.82 V，voltage_ocv 约 3.88 V，status Charging。不是电池健康检测结果，不代表百分比已完成出厂级校准。

仅适配当前确切 kernel release；其他版本自动跳过，不强行加载 ABI 不兼容模块。服务启动失败尝试恢复原驱动。根服务不执行用户目录内的脚本/模块，不创建自动模块别名加载路径。

## 验证与限制

- 实际 C 算术函数提取编译并通过 UBSAN：校准值/无效参考、-50..99°C 边界、OCV 上下限、正负/扩展库仑计。test_bms_math.py 可重跑。
- 模块由匹配 ARM 内核树和 Module.symvers 编译；最终使用原内核对应 arm-linux-gnueabi 工具链，未强制忽略版本检查。
- 手机临时加载成功、连续读数稳定、原驱动回退成功后最终模块再次加载成功；服务重启幂等验证。**未主动重启手机做冷启动验收**。
- 容量仍是估算：电池老化后的实际 FCC、NTC 曲线、10mΩ sense 电阻假设、ADC 温度补偿未完成实测标定。尚未完成整次充放电周期，不应宣称精确容量/健康度。计数连续扩展依赖系统仍轮询，休眠后可能有更长间隔需额外验证。
- 读取 charge_counter 为正向放电积分；台架测试即便 Charging，计数仍正向增长，可能负载大于实际供电。状态字不能证明充电能力已修好。
- 启动早期 initramfs 仍运行内置旧驱动；修正在 rootfs systemd 阶段加载。插线自动开机未取消、调试熄屏待机尚未部署。

## 回退

手机执行：

    sudo systemctl disable --now mi4-bms-fixed.service
    sudo python3 /usr/local/lib/mi4-bms-fixed/bms_fixed_init.py --rollback

恢复 qcom-bms，模块卸载、driver_override 清空。无须重刷 boot。仅 stop 服务本身不会切换正在使用的驱动，因此必须执行 --rollback。

证据：bms-fix-precheck-20261020.log、bms-fixed-live-test-20261020.log、bms-fixed-samples-20261020.log、bms-fixed-persistent-install-20261020.log、bms-fixed-final-verify-20261020.log。

算法参考：Qualcomm 下游 qpnp-bms.c：[URL REDACTED] 。OCV ADC 校准和 CC 36位范围/换算与该一手代码核对，未以二手教程的电压百分比表替代库仑计。
