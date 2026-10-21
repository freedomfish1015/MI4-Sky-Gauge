# Mi4 仪表安静启动（2026-10-18）

## 重要：本方案实机失败，禁止重用

用户明确反馈本轮重启黑屏，USB也完全未恢复。
虽镜像字节范围及哈希均符合预期，但不代表这些启动参数在该机型上可用。
目前只能确认故障紧接本轮启动参数修改，不能武断断言某一个参数是唯一根因。
`quiet_boot.py --write` 已在电脑和手机两端禁用（在读取/打开块设备前直接拒绝）。

用户手动进入厂家FASTBOOT兔子，确认设备序列5b628616/product MSM8974，
已通过厂家fastboot恢复修改前32MiB原boot分区，上传/写入均OKAY，随后reboot。
没有清除userdata、system、仪表配置，未刷入别的内核。
原备份SHA256再次核对为5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653。
日志 quietboot-fastboot-rollback.log / quietboot-fastboot-rollback-reboot.log。
回退后COM10已恢复；原/proc/cmdline（含console=tty0）已恢复。
仪表ActiveState=active/SubState=running/NRestarts=0，运行样本49.8–59.2FPS。
重启后触摸event1仍为root:video0660，brightness仍为root:video0664，权限规则持久生效。
用户已明确确认“仪表和触摸都恢复正常”。
证据 quietboot-rollback-running.log。正常运行已恢复；安静启动目标未实现。
回退后已root读取完整/dev/mmcblk0p19，SHA256与修改前原分区完全一致，
不是仅凭fastboot返回OKAY推断恢复；见quietboot-rollback-verified.log。
后续若继续处理安静启动，应使用可恢复的单项实验先临时启动验证，
不能把字节范围正确当作功能验证，也不要直接重复取消console=tty0的组合参数。

下文是失败实验的历史记录，不是可执行的推荐方案。

用户要求：开机 Logo/UI 后直接进入仪表，不要滚动代码/启动服务文字/登录提示。

## 定位与改动

原启动参数含 `console=ttyMSM0,115200 console=tty0`；tty0 是显示器内核控制台。
未安装 Plymouth，仪表原本由 `obd-gauge-kiosk.service` 直接启动，日志写 journal。
只取消 Linux 启动参数里的 `console=tty0`，保留调试串口、原根分区UUID及全部硬件参数。
添加：

```
quiet loglevel=3 systemd.show_status=false rd.systemd.show_status=false
vt.global_cursor_default=0 logo.nologo
```

不改开机 Logo、lk2nd 引导程序，不新增开机视频或重装系统。
不清空/禁止 journal 或 dmesg 环形缓冲；只控制控制台可见输出。

## 分区格式与严格验证

手机 boot 分区 `/dev/disk/by-partlabel/boot` -> `/dev/mmcblk0p19`，33554432字节。
前524288字节是lk2nd；Linux Android header在524288字节处。
本轮实际只写 Linux header 的 cmdline 字段：绝对偏移524352，长度512字节。
写入后逐字节核对整个32MiB分区与预期完整镜像一致，范围外所有字节保持不变。
原内核/DTB（含用户/其他AI的电量SOC、WLED、触控、声卡修复）、initramfs、lk2nd、尾部都未修改。

脚本：`[LOCAL-PATH]`，同文件已传手机desktop-offline。
`--prepare` 只备份和生成候选；`--write` 检查机型/分区/大小/当前哈希，写512字节并全分区读回。
写入异常时尝试只恢复原cmdline字段并再次核对完整原分区。
任何发现当前启动分区已变化都会停止，不能拿旧镜像覆盖新修复。

## 备份、产物、哈希

手机 `/home/umeko/desktop-offline/`：

- `boot-before-quiet-20261018.img`：完整32MiB原分区。
- `boot-quiet-20261018.img`：只改cmdline的32MiB完整候选。
- `boot-quiet-20261018.json`：新旧参数和哈希清单。

电脑备份 `[LOCAL-PATH]`。
使用二进制串口传输并SHA256核对，并非被截断的长文本复制。

- 原分区：`5715032761b50157ea495d5dfb3d71b2b6de300f00ce7681f48f154dd9f67653`
- 修改后：`cea1bb654293a228d1df3729a6971c26e64bc5d69f6a07632d61f296e2fb4271`
- lk2nd：`45a16cdeda912e255695b5491207b4fbb4740e28da3f11eb1d0d856e3d435767`
- Linux首header页之后的全部分区内容：`22cbb31c6e8915ef1849cc2452be48f5ef619feb2e031cfb202dd1bd80d47deb`

电脑3项测试通过：范围外字节不变、保留串口/移除屏幕控制台、错误格式/扩展cmdline拒绝。
电脑从真实备份生成候选的哈希与手机完全一致。
证据 quietboot-inspect.log / quietboot-prepare.log / quietboot-written.log。
历史上已写入并重启，后续用户反馈黑屏，见顶部回退记录。

## 恢复注意

不要对仍有新改动的分区使用旧整镜像覆盖，先核对当前哈希。
若仍能进Linux，可从原备份恢复同一512字节字段，fsync并比较全分区原哈希后重启。
若需fastboot救援，先明确“厂家FASTBOOT兔子”还是“lk2nd Fastboot Mode”。
**不能把本轮32MiB整分区备份直接在lk2nd里 `fastboot flash boot`**：
lk2nd给boot写入自动增加512KiB偏移，整分区文件不适用于该入口。
lk2nd需从备份中提取正确的Linux-only Android boot image；厂家fastboot的分区语义不同。
恢复前请核对阶段、分区大小、镜像结构，不能盲目套用旧内核镜像。

参考原始资料：

- https://github.com/msm8916-mainline/lk2nd/blob/main/Documentation/boot.md
- [URL REDACTED]
- [URL REDACTED]
