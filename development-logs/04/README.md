# 原厂 Fastboot 兔子画面恢复：已写入，Fastboot与正常启动均已验收

## 最新实机状态（优先于下方早期离线记录）

用户明确回复“开始吧”，随后在告知18%电量后进一步明确要求“不用，直接刷”。本次按该新授权保留USB在线、VBAT≥3.65V、SOC≥15%硬下限，不复用历史低电量授权。写入前处于充电模式，kiosk/motion inactive、charge-mode active；18%、约3.756V、USB online=1。

`flash_fastboot_screen.py` 的7项写入/拒绝/回退测试通过；6项ARM绘图测试再次通过。部署脚本SHA `641bd6ba3360a242e393c75f484a116f59766799cb66da08a473f62ca32d2355`。只写 **0x24600 处512字节扇区**，全aboot读回完全符合 `d9ed7759fd8ed89cdd4351d582e45428316ab7ac6788bca4a45444c8b3dd5d49`；只有上述4字节发生变化。Linux boot与logo SHA均保持原值。

新鲜root备份：`/home/umeko/desktop-offline/backups/fastboot-rabbit-before-3t6hc569/`，含aboot.img、预期新aboot、before.json、success.json，均0600/fsync并读回。电脑上旧有效aboot的SHA与新鲜原备份相同，文件`mi4-aboot-sky-CANDIDATE-NOT-FLASHED.img`是历史文件名，不代表本轮修复未刷。

随后 `systemctl --no-block reboot --reboot-argument=bootloader` 进入原厂Fastboot。用户明确确认 **“FASTBOOT 兔子”**。Windows识别Android Bootloader Interface，驱动oem158.inf/Xiaomi16.0.0.0/problem0；fastboot33列出设备，getvar product响应MSM8974、userdata大小0x32b3fbe00。证明USB Fastboot命令响应，不只是图片。没有借测试执行任何fastboot flash/erase。

**发现独立安装器兼容问题**：原厂 `getvar version-bootloader` 和 `getvar partition-size:boot` 返回空，`partition-size:userdata`正常。当前Windows候选安装器会因此拒绝安装。不能宣称自动安装器已在此原厂引导上通过，也不能直接删掉安全检查强制放行；正式发布前需要单独设计并验证保守的兼容流程。

已执行 `fastboot -s <已核对设备> reboot`，返回OKAY。用户随后明确确认 **“Sky Gauge、仪表和触摸都正常”**，正常启动视觉/触摸验收通过。此前COM10暂未枚举不等于启动失败；本次验收以用户实际观察为依据，没有把尚未取得的串口复查写成已通过。尚未做拔线冷启动按键入口实测，也未通过Fastboot执行实际重刷测试。

证据：本目录 `flash-write-readback.log`、`reboot-to-fastboot.log`、`factory-fastboot-getvars.log`、`fastboot-reboot-normal.log`。以下“未写入”等为本轮正式写入前的历史准备记录。

2026-10-21，用户请求恢复可见的 Fastboot 页面以便故障重刷。

## 实机只读确认

- 系统 COM10 正常，仪表 active，GPS recording=false。
- aboot SHA `362986d35fe58e55508615fc806483a4533e55f83fa9ab631ed1d7d9cb7c3f40`。
- logo SHA `47dbe469e9fcb84280f741161e1e76a67abe4b008d17f3f91bcea86fa7b173c5`。
- boot SHA `724783b32b5b09dd53245ec42277df4ef3b85cd1da7560ced1c0caaa92da8d2b`。
- 检查时 USB online=1，VBAT约3.719V，capacity约18%。没有请求重启，没有写分区。
- 证据日志在 `[LOCAL-PATH]`。

## 原因及边界

原 aboot 的 Fastboot 绘图函数也优先加载外部 splash。此前将分区名 splash 改为 logo 后，Fastboot 优先显示 Sky Gauge；不能根据“不再出现兔子”推断 USB Fastboot 功能已删除。

此前隐藏 lk2nd 底部版本文字只改正常启动的绘图函数，Fastboot 菜单独立存在。当前未用 USB getvar 实测进入原厂 Fastboot，因此此处仅是可见画面的根因定位，不宣称 USB 救援已经通过。

公开候选 `.mi4sky` 包只写 userdata/boot，不包含这台手机的 aboot/logo 改动。不能因为当前开发机换过原厂图片，就宣称其他原厂手机安装后也失去 Fastboot。

## 离线最小修复

正常绘图：ARM `0x0f0245b4`，继续加载 logo 保留 Sky Gauge。

Fastboot 绘图：ARM `0x0f024634`。完整镜像反汇编中只找到该函数的一个直接调用：`0x0f01110c`，调用前将 r0 设为1，选择内置兔子素材。

只把 Fastboot 函数内地址 `0x0f024654`（aboot文件偏移 **0x2467c**）的一条4字节指令从 `0xebfff329`（BL外部图片加载器）改为 `0xe3a00000`（MOV r0,#0），让现有原厂分支使用内置649x843兔子。正常开机绘图函数、Linux boot、电量保护、内核修复和用户数据均不在候选修改范围内。

- 候选完整 aboot SHA `d9ed7759fd8ed89cdd4351d582e45428316ab7ac6788bca4a45444c8b3dd5d49`。
- `build_candidate.py` 完全离线，不打开USB或块设备。
- 6项Unicorn真实ARM代码测试通过：精确4字节差异；正常Sky图片逐字节一致；Fastboot画面与原aboot的兔子逐字节一致；不依赖logo存在或有效；正常坏图仍回退mi；未知源镜像拒绝。
- `fastboot-rabbit-offline-preview.png` 来自执行候选真实ARM绘图函数得到的framebuffer，已视觉确认兔子及FASTBOOT文字。不是实机照片，不代表实际重启/USB已验证。

## 下一步安全要求

**候选尚未写入，不能直接 flash 整个 aboot。** aboot 是原厂USB救援入口；失败可能失去Fastboot，EDL仍未实测。

需要用户明确同意此最小 aboot 修改，并先充足电、复查供电与实时电压。建议电量≥50%，不能沿用2026-10-20另一次低SOC写入的历史授权跳过检查。

若获准，应新鲜读取并备份当前aboot，核对源完整SHA、型号、分区major/minor与4MiB尺寸；只写包含偏移0x2467c的同一512字节扇区（0x24600），fsync、完整读回对比；失败应恢复同一原扇区并核对源SHA。全程不写logo或Linuxboot，不复用会同时恢复整个logo的旧rollback脚本。

写入后需分别验证正常启动Sky图/仪表，以及真正进入原厂Fastboot时兔子画面与USB getvar。原厂和lk2nd写boot语义不同，识别不明时禁止刷入完整32MiB boot。

本候选不要放入通用发布文件夹：它只适用于当前精确原厂aboot版本，通用安装器目前有意不触碰aboot。
