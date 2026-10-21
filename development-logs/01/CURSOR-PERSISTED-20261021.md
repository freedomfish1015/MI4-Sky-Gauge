# 2026-10-21：早期闪烁光标修复已永久保存

## 授权和已完成状态

用户先确认第三轮内存测试中“光标没再出现，仪表正常”，随后明确回复 **“保存”**。已持久保存唯一参数`vt.global_cursor_default=0`。不是把整个RAM测试镜像刷入boot。

写前复查：USB online=1、约85%、4.059V、充电模式normal、内核6.15.11-mi4-audio1，当前RAM运行参数中有测试项；真实旧boot完整SHA仍edf91d38...e4b035d，原aboot/logo SHA亦完全一致。

## 写入范围与校验

`persist_cursor_parameter.py`默认只读；用户授权后使用`--write-approved-cursor`。精确校验机型、boot设备179:19/32MiB、未挂载、供电电量、已测试cmdline、整个原分区SHA以及lk2nd/硬件payload/aboot/logo哈希。任何其他AI并发修复会导致拒绝写入。

在当前真实boot上只向原Linux cmdline末尾加`vt.global_cursor_default=0`，保留所有console/earlycon/quiet/root和其他选项。新Linux有效镜像SHA与用户通过测试的RAM镜像完全一致。参数放得下，因此实际只写 **一个对齐512字节扇区，偏移524288（0x80000）**；前64字节header字段原样保留，变化均在该扇区cmdline内。

- 原boot完整SHA：`edf91d38f7cd87b5a59480ac5b0f00acb79a71aaa5f16577047959e47e4b035d`（历史值）。
- **当前boot完整SHA：`724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b`**。
- 当前有效Linux镜像SHA：`3eea09bc54d4a6851ea16368d5dc9919d84f38bfa0c947a5f01d3cc69b070dfa`（与已验收RAM镜像一致）。
- lk2nd前512KiB完全不变：`c575f86910f82bc2cd87097fd777cbe0bed6d46bae087e7d2f39ee64bc04d36d`。
- kernel+DTB+ramdisk有效payload完全不变：`60909ec6155c25bfa7c30f579147a37c8136d69af91580cdb92459a4c083372f`。
- aboot仍`362986d35fe58e55508615fc806483a4533e55f83fa9ab631ed1d7d9cb7c3f40`；logo仍`47dbe469e9fcb84280f741161e1e76a67abe4b008d17f3f91bcea86fa7b173c5`。

写入后fsync，**整个32MiB逐字节读回等于目标**；aboot/logo再读SHA确认未改。源/短写/读回错误会恢复原512字节并再次验证整个分区，若回退验证失败则明确禁止重启。本轮没有触发失败或回退。

注意：旧文档所说“从524288起Linux完整尾部SHA167f...”含header，现因合法cmdline改动已不再是当前值；不能以其变化误判内核被替换。真实kernel/DTB/ramdisk payload仍为上述60909e...。

## 备份和日志

新鲜原boot：**`/home/umeko/desktop-offline/backups/cursor-persist-before-57giu9yt/boot.img`**，目录root0700、文件0600，fsync文件/目录并读回源SHA通过。另含before.json/success.json。

电脑工程：`[LOCAL-PATH]`。

- `cursor-parameter-persist-20261021.log`含只读验证、备份路径、最终`CURSOR_PARAMETER_PERSISTED_FULL_READBACK_OK`。
- `cursor-persist-precheck-20261021.log`。
- `persist_cursor_parameter.py`部署手机同名路径，上传SHA`231263e0a8375b0e7858015642fb326929f3a19a80cf2bc1ff32d2ce2e4fd3a1`。
- `test_persist_cursor_parameter.py`8项通过（使用重建后与真实原boot SHA完全一致的镜像验证），覆盖一扇区改动、与RAM镜像逐字节一致、并发拒绝、短写/读回失败回退。

## 普通重启验证

保存后确认recording=False，发送普通systemctl reboot，**没有使用fastboot boot**。USB串口恢复后核实（`cursor-persist-normal-reboot-20261021.log`）：

- 新boot_id：`b6f34a7f-23e3-4f2a-a3be-6efe18c45eb9`，读取时uptime60.85秒，证明是新启动。
- /proc/cmdline仍有`vt.global_cursor_default=0`，rootfs cursor default=0，说明持久参数经正常引导已生效。
- 首帧19.53秒，elapsed6.581秒；kiosk、BMS、motion、charge-mode全部active/success、NRestarts=0；背光901。
- `cursor-persist-final-hashes-20261021.log`再次读取真实boot完整SHA为724783...，aboot/logo仍为上述原值。
- 手机屏幕的本次普通重启视觉反馈尚未单独询问/取得；此前RAM测试用户明确确认光标消失、仪表正常。不能把软件核对等同于用户再次视觉验收。

当前日志部分窗口约43–50FPS，原因未调查（页面/输入/负载等不明）。本轮没有更改绘制/传感器代码，也没有依据这些数据宣称目前恒定59FPS；如后续用户反馈卡顿应独立检查。之前约59FPS为历史稳定样本。

用户RAM视觉验收有效，但它不等同于保存后重启验收，也不等同于插线冷启动计时。隐藏光标不代表启动提速，本轮仍约19秒Linux首帧；后续若继续提速应单独测量，不删减必要驱动。

## 只回退这个参数

`restore_cursor_parameter_20261021.py`只在明确要求回退时使用：先传到手机，与persist_cursor_parameter.py放在同目录，然后以sudo加`--restore-original-cursor`。校验root保护备份、当前整个boot精确为724783...、安全供电，再只恢复同一个512字节扇区，全读回验证edf91...。有任何其他后续boot修改就拒绝，不能整分区覆盖其他修复。脚本不自动重启。

旧RAM测试工具/旧安装器以edf91...为源，今后会拒绝当前724783...，这是正确的防并发保护；不要仅为绕过保护而改旧脚本常量。需要新实验时重新读取当前真实boot。
