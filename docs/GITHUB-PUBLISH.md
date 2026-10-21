# GitHub上传与发版

## 1. 哪些放仓库，哪些放Release

`repository/`内容就是Git仓库根目录，不要把外层工作目录、reports、旧整机导出或build一起上传。

- Git：源码、配置、许可证、开发文档、脱敏日志、测试、依赖和来源清单。
- Releases：源码ZIP、内核/引导源码tar.gz、校验文件；经过独立审核的二进制才另行附加。
- 不上传：个人设备原始快照、未脱敏日志、.obd-sudo-pass、实际轨迹/Wi-Fi/配对、账号/订阅、整个.git工作历史、未授权图片视频。

GitHub网页上传单文件限制25MiB，普通Git仓库单文件不能超过100MiB。源码归档/大镜像应放Releases，附件单文件需小于2GiB。官方说明：[添加文件](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)、[大文件](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[关于Release](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。本次内核源码归档约244MiB，不能直接拖到仓库文件列表。

## 2. 本项目仓库与后续更新

本项目使用 [freedomfish1015/MI4-Sky-Gauge](https://github.com/freedomfish1015/MI4-Sky-Gauge)，默认分支 `main`。仓库整理保留原提交历史；不要对这个已有仓库使用孤立根提交或强制推送覆盖历史。整理范围见 [REPOSITORY-MIGRATION.md](REPOSITORY-MIGRATION.md)。后续开发应先克隆该仓库，再在其基础上提交更新。

以下只适用于另建空仓库，不用于覆盖已有的 `main`：

在GitHub手动创建空仓库，例如mi4-sky，先不要让网页生成README/LICENSE以免初次历史冲突。在`repository`目录操作：

```sh
git init -b main
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "chore: publish mi4-sky source and sanitized development history"
git remote add origin https://github.com/YOUR-NAME/mi4-sky.git
git push -u origin main
```

如本地目录已由整理工具初始化，跳过init。设置Git作者身份并完成GitHub正常登录，不把token写入脚本/remote URL。是否成功上传以远端提交及附件实际校验结果为准。

`.gitignore`排除镜像/EXE/私钥/缓存，`development-logs`是明确保留的脱敏记录。上传前运行 `python3 tools/audit_public_tree.py`，检查暂存文件确实是源码。没有Git命令行时可分批网页上传源码文件；不要只把一个ZIP放进Git仓库当成源码树。

## 3. 创建Release

先完成CI，检查当前问题和许可边界，再创建标签（例如source-2026.10.22）。上传外层release-assets内的源码附件与校验文件，说明引用commit、硬件profile和测试结果。Release说明可使用本目录中的RELEASE-NOTES.md。

**本次不附原整机镜像**：旧stable二进制含厂商固件/外部素材且Windows安装阻断未解决，不能因为源仓库有GPL许可证就把它宣传为完全开源通用系统。若以后要发镜像，先做无未授权素材的构建、核对厂商固件再分发条件、对应源码、第二台手机清空安装及首启验收。

## 4. 国内网络与更新

本次PID核心和cJSON已经vendor，可离线构建，不依赖临时GitHub克隆。硬件源码归档也已准备，接收方可离线获取。未来下载GitHub文件可配置可信国内镜像，但必须对官方锁定commit/哈希校验，不关闭TLS校验、不把镜像站自己的哈希当成唯一依据。

不在源码里硬编码私人代理、账户、订阅或一次性镜像token。更改依赖时更新metadata/dependencies.lock.json并重新编译/测试，不静默跟随main。
