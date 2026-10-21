# 构建与验证

## 1. 选择开发目标

| 目标 | 主机 | 输入/输出 |
|---|---|---|
| 应用逻辑和离线UI测试 | Ubuntu 24.04 / WSL，Python3.12 | 源码 → 测试；不需要手机 |
| PID/事件库 | Linux gcc / arm-linux-gnueabihf-gcc | vendor + native → libmi4compat.so |
| Windows安装器 | Windows .NET Framework 4.x C#编译器 | Installer.cs → EXE；没有设备也能测试 |
| Linux硬件内核 | Linux ARM交叉工具链 | Release源码快照 + kernel.config → zImage/DTB/modules |
| 整机包容器 | 任意Python3.12主机 | 已准备且审核的boot/rootfs sparse → .mi4sky |

不要在NTFS上展开整个Linux内核源码后编译：符号链接、大小写、保留文件名和行结束符都可能有问题。将硬件源码归档解压到WSL自己的ext4目录。

## 2. 主机逻辑测试

```sh
sudo apt-get install build-essential python3-cairo python3-gi python3-gi-cairo gir1.2-pango-1.0 python3-pygame python3-bleak python3-dbus-fast python3-qrcode
python3 tools/build_native.py --target host
python3 tools/run_tests.py --full
```

原版PID/事件核心已随源树提供，不用临时克隆GitHub；cJSON v1.7.19也已校验并提供源码。Linux FFI自动在64位主机使用 `app/compat/build-host/libmi4compat.so`；32位设备使用build-armhf目录。不要把x86库装上ARM设备。

`python3-gi-cairo` 是 PangoCairo 与 pycairo Context 之间的桥接，不能只安装 `python3-gi` 和 `python3-cairo`。首次 GitHub Actions 干净环境测试曾因漏装它而出现 `KeyError: could not find foreign type Context`；依赖清单与 CI 现已补齐，不跳过相应渲染回归测试。

本次推荐完整入口运行188项测试，其中2项按条件跳过：真实SDL触摸选择测试、未再分发的原厂aboot私有样本测试。内存中的写入/回滚测试照常运行，不实际打开设备。

`tests/`还保留旧阶段测试供查阅，默认不等于所有历史测试都适用于当前布局。推荐入口明确列出当前回归；不要用删除失败断言的方法宣称通过。旧Sky订阅常量名中仍有100ms字样，实际捕获构建为250ms，测试依据实际字节，不因名称猜测。

## 3. ARMhf库和界面预览

```sh
sudo apt-get install gcc-arm-linux-gnueabihf
python3 tools/build_native.py --target armhf
```

当前程序不是标准argparse程序，不要用未知的`--help`假设它一定只打印帮助。主机静态导出用法：

```sh
mkdir -p build
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 app/gauge_sdl.py --export build/preview.png --flat
```

以实际导出文件位置/代码为准；预览与运行增量帧必须分别验收。开启设备采集/真实蓝牙前先读源码入口，不要在电脑上直接启动systemd服务。

## 4. Windows安装器

```powershell
.\installer\test.ps1
.\installer\build.ps1
# 确有需要时，另行提供可信platform-tools 33.0.3目录：
.\installer\build.ps1 -ToolsDirectory C:\tools\platform-tools
```

输出在 `build/`，不提交Git。工具EXE/DLL由Installer.cs固定SHA检查，不允许把任意同名EXE当作fastboot。Google工具和驱动不包含在源仓库；获取时保留原NOTICE，GitHub来源的文件如经镜像下载还要从可信官方元数据校验。

`MI4-Sky-Installer.exe --verify <包>`只解压/验证，不刷机；`--diagnose`只读Fastboot查询。GUI安装才会在确认后写分区。当前原厂不报告boot大小时仍拒绝，见KNOWN-ISSUES。

## 5. 硬件源码

Release附件：`mi4-sky-kernel-source-20261022.tar.gz` 与 `mi4-sky-lk2nd-source-20261022.tar.gz`，SHA见metadata/hardware-sources.json。归档顶层就是源码目录内容，解压到各自新目录。先列出归档检查路径，不要覆盖现有工作区。

Linux快照已含本地音频/WLED/设备树改动；**用快照时不要再次应用mi4-changes.patch**。补丁与additions用于从所标上游commit另行重建时比较/移植。示例：

```sh
mkdir -p ~/mi4-sources/linux ~/mi4-build/kernel
tar -xzf /path/to/mi4-sky-kernel-source-20261022.tar.gz -C ~/mi4-sources/linux
cp hardware/kernel/kernel.config ~/mi4-build/kernel/.config
make -C ~/mi4-sources/linux O=~/mi4-build/kernel ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- olddefconfig
make -C ~/mi4-sources/linux O=~/mi4-build/kernel ARCH=arm CROSS_COMPILE=arm-linux-gnueabi- -j4 zImage dtbs modules
```

工具链选择以原构建配置/Makefile为准；安装对应gcc-arm-linux-gnueabi。当前设备树最终文本另在current-device-tree-1.dts，含当时二进制补丁结果；不能仅重编旧DTS就认为OCV/WLED等仍一致。

lk2nd快照提供Makefile、原LICENSE与修改过的低电量UI/策略。使用上游Documentation/building.md和当前target/project配置，重新生成glyph需Noto CJK + Cairo/Pango。此阶段未重新编译/实测引导，**不提供一条默认刷写boot/aboot的命令**。

## 6. 根文件系统与容器打包

本仓库提供模块/服务/overlay及 `tools/stage_rootfs.py`，供已有干净Ubuntu ARMhf staging使用；不包含开发手机整份rootfs快照、Ubuntu包二进制或高通固件。必要系统包、内核模块、用户权限、initramfs、设备固件和首启流程需按具体设备准备。依赖清单在metadata/rootfs-packages.json。

`stage_rootfs.py`只在显式的离线树内复制源码和配置，不自动安装系统包、不写真实分区、不保证从Ubuntu base一步得到原机全部能力。整机容器可用 `tools/package_image.py --help`；输入boot与sparse必须已经准备、校验和做隐私审核，打包通过不代表能启动。

完整链路尚未达到逐字节可复现；不能把历史手机导出包叫作“完整源码”。详见REPRODUCIBILITY。
