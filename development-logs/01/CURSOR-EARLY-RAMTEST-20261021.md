# 早期光标：单内核参数RAM版（第二次已确认参数生效，用户要求再重试）

> 最新：第三次内存测试参数确认生效，用户明确确认“光标没再出现，仪表正常”，随后授权“保存”。已仅写入Linux header一个512字节扇区，完整读回和普通重启验证通过；当前完整boot SHA改为724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b。详见`CURSOR-PERSISTED-20261021.md`。下文edf91...为此前RAM测试源，不是现在的完整boot SHA。

## 第二次有效内存启动（当前最新）

用户保持音量下，电脑从正常Linux发起reboot，进入原厂Fastboot，再临时boot逐字节等同现有lk2nd的512KiB镜像，确认lk2nd版本查询成功。停在lk2nd等待用户松开按键并回复“准备好了”之后，才发送Linux测试镜像。

Sending/Booting均OKAY；电脑等待USB恢复后立刻读取，日志`cursor-ram-second-immediate-20261021.log`：

- boot_id：`f47c7e7f-462f-4fc2-9388-2f00b5c75042`。
- `/proc/cmdline`明确保留全部旧项并含`vt.global_cursor_default=0`，证明这次测试镜像确实生效。
- 读取时uptime49.05秒；`DIRECT_GAUGE_FIRST_FRAME`为19.13秒、elapsed6.354秒。
- kiosk和BMS均active/success、NRestarts=0；kernel runtime cursor默认0。
- 尚未持久写入任何分区。首帧19.13秒属于约19秒范围，不能把细小单次差异夸大为新参数显著提速。

询问视觉结果后，用户回答“再重试一次”，不是确认光标消失。下一轮仍需先进入Fastboot、停住等用户准备观察/录像，然后再次RAM启动；不要擅自持久化。

## 第一次RAM启动及当前重测计划

用户按住音量下后，电脑fastboot reboot仍回到原厂Fastboot。随后构建`lk2nd-CURRENT-EXACT-RAMONLY-20261021.img`：从PC旧备份提取前512KiB，按已验证的footer补丁重建，再与新鲜手机元数据的lk2nd前缀SHA比对，完全一致`c575f86910f82bc2cd87097fd777cbe0bed6d46bae087e7d2f39ee64bc04d36d`。不是重编低电量测试源码。`make_current_lk2nd_ram.py`仅操作普通文件。

从原厂Fastboot临时boot该512KiB**当前已安装lk2nd的逐字节副本**，用户保持音量下，成功进入lk2nd；getvar lk2nd:version实际返回`22.0-next-4a1e26e4-20260419-dirty`。向用户提示松开所有按键后，`test_cursor_ramboot.ps1 -BootTrial`校验非空lk2nd版本及镜像SHA，发送16338944字节候选，Sending/Booting均OKAY。**没有flash/erase命令。**

用户回复“我没注意到，请重新来一遍”，因此没有视觉验收。之后读取时当前boot_id为bc2e9aec-bc99-482f-b9d0-7224600ab534、uptime约1分钟，/proc/cmdline和chosen/bootargs均**无**新参数，首帧19.68秒。journal中此前还有持续约30分钟的一轮启动；历史kernel日志为空，无法仅凭这次普通启动断言第一次RAM候选被忽略，也可能中间已重启回原系统。不要将本轮算作参数已生效/已失败或光标已隐藏。

真实boot分区重新sha256验证仍`edf91d38f7cd87b5a59480ac5b0f00acb79a71aaa5f16577047959e47e4b035d`，证明持久引导未改变。BMS约88%、4.157V，系统正常。

重测时应在发送RAM镜像后直接等待USB恢复并立刻读/proc/cmdline，不能在期间让用户另行手动重启。提前等用户确认正在观察；先完成参数生效核对，再解释光标观察结果。进入Fastboot仍需要用户保持音量下配合，当前已验证的stock->RAM exact-lk2nd流程可避免原先抢时机。

## 当前停靠状态

手机已切换到原厂Fastboot：序列号5b628616，product=MSM8974，lk2nd:version/lk2nd:model查询均为空。**未发送fastboot boot，更未flash任何分区。** 需要用户按住音量下，再由电脑配合一次reboot，进入下一层lk2nd文字Fastboot。原厂aboot改过logo，不能根据是否见到兔子判断。

最初只读预检的版本正则使用了\\s，误跨空行将Finished识别为版本；发现空getvar输出后立即改为只允许行内空格和非空版本，空值拒绝/有效值接受回归通过。之后设备再次从Fastboot枚举中消失，重新预检因设备数为0而拒绝执行，不能宣称该次已实际完成原厂版本拒绝查询。误识别阶段只运行了默认只读预检，没有执行启动或写入命令。

用户切入Fastboot时COM10消失，故本轮新文档及回退脚本上传未能开始，仍仅在电脑；已安装的rootfs改动和新鲜boot备份均在手机。待Linux返回后再同步，不要在Fastboot时尝试串口传文件。

用户上传视频后，已确认rootfs之后的cursor默认0不足以证明整个启动期间没有光标。用户重新USB连接后，读取到仪表首帧19.53秒，rootfs抑制脚本在uptime5.69–7.28秒运行。因此本轮先准备更早参数的RAM测试，没有直接持久刷写。

## 来源和保护

- `inspect_cursor_ram_source.py`只以rb打开真实`/dev/disk/by-partlabel/boot`，验证机型分区尺寸/布局和当前完整SHA，备份到手机普通文件，再导出2048字节Linux头和各段SHA元数据。
- 真实全boot SHA仍`edf91d38f7cd87b5a59480ac5b0f00acb79a71aaa5f16577047959e47e4b035d`。
- 新备份：`/home/umeko/desktop-offline/backups/cursor-ram-source-d_mp46gi/boot.img`，root目录0700、文件0600、fsync/读回通过。
- 导出`cursor-ram-source-20261021.json`（不含用户文件），下载整文件SHA验证`f32873fc23b866e61aed1a0d3f324ffa10a994ecc36a601c1c405592ac30a262`。
- 当前Linux完整镜像SHA`4bc26538a38e4d3e5014e95205286b48282a85173e27583e0af1523e6e2fd58c`。
- 当前kernel+DTB+ramdisk完整payload SHA`60909ec6155c25bfa7c30f579147a37c8136d69af91580cdb92459a4c083372f`。

PC旧`boot-before-quiet-20261018.img`只作为二进制payload来源；与上述当前payload逐字节等价SHA通过后，使用**当前手机新鲜头部**重建Linux镜像，整Linux SHA再次一致。不采用旧boot头，不采用旧lk2nd前缀，不覆盖既有Sky/WLED/OCV/音频修复。

## 唯一测试项

原命令行全部保留（包含两个原console、earlycon、root UUID、ignore_unused、quiet/loglevel=0等），只在末尾加：

`vt.global_cursor_default=0`

候选与当前Linux镜像只允许64…575的512字节cmdline字段变化，所有其余header和payload字节一致。Android镜像ID不覆盖cmdline，此次没有更改kernel/ramdisk，所以不重算或擅改它。

- 候选`boot-mi4-cursor-hidden-RAMTEST-20261021.img`，**16338944字节**，Linux-only。
- SHA`3eea09bc54d4a6851ea16368d5dc9919d84f38bfa0c947a5f01d3cc69b070dfa`。
- `make_cursor_ramtest.py`仅接受普通备份文件，不访问块设备；本轮5项测试通过，覆盖payload拒绝、头部一致、两console保留、单参数、扩展cmdline拒绝。

**它是RAM-only镜像，不得flash到boot。必须从lk2nd Fastboot临时boot；不能从原厂Fastboot直接启动这个Linux-only镜像。**

## 下一步

已请用户重启并在出现Sky Gauge标志/震动之后按音量下，进入lk2nd/Fastboot文字界面。原厂Fastboot现在可能因自定义logo只显示Sky Gauge，不应只靠兔子判断。

`test_cursor_ramboot.ps1`先校验候选SHA，要求且仅一个Fastboot设备，并查询`getvar lk2nd:version`确认是lk2nd；无法确认就拒绝执行。无参数仅只读检查。用户准备好后加`-BootTrial`，唯一启动命令为fastboot boot，不包含flash/erase/unlock/format。

临时测试后核实/proc/cmdline包含唯一新参数，记录首帧及硬件状态，请用户观察光标。即便光标消失，也不得把暂时镜像当已持久化；还需明确说明并经用户确认后才能讨论512字节持久参数修改。

历史quiet_boot.py曾组合删除console等修改导致黑屏，写功能已禁用。本候选没有删除任何原有console/选项，不能用旧脚本替代本流程。

## 启动提速当前状态

上一轮无动画已显著缩短约13秒。本轮BMS提前的收益仅0.3–0.6秒（约19.5秒首帧），尚未进一步达到明显改善。CPU0–3在线，但cpufreq/policy0节点不存在；没有擅自切换调频、超频或砍掉驱动。先完成光标单项测试，再据真实冷启动日志优化。
