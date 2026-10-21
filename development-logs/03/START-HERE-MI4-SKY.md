# mi4-sky 小程序开发交接包

先阅读 `MI4-SKY-MINIPROGRAM-DEVELOPER-GUIDE-20261021.md`，这是本包的完整功能与接口说明；可以把这一个文件直接交给负责小程序制作的 AI。

## 内容

- 完整文档：产品边界、单二维码协议、热点、HTTP 接口、错误码、CSV 21 列、GPS/原始 LOG、行程关联、隐私与验收。
- `miniprogram/`：未发布的微信小程序草稿，没有正式 AppID，未真机验收。
- `log_hotspot.py`、`log_download.py`、`racechrono_export.py`、`gauge_log_transfer.py` 等：已部署接口的源码快照，作为客户端开发依据，不是让你重新刷写手机的安装包。
- `gauge_settings.py`：经过验证的设置页基线，供理解现有 UI；不要拿工程根目录同名待开发文件覆盖手机。
- `test_*.py`：已有后端/协议自动测试，Linux/WSL 下在本包根目录执行 `python3 -m unittest test_transfer_ui test_log_download test_pairing test_racechrono_export`，共 32 项。
- `mi4-sky-racechrono-validation.csv`：真实设备转换出的短样例，含台架模拟源标记，不是完整实车行程。
- `mi4-sky-transfer-preview.png`：原生分辨率页面预览，使用演示密码/token，其二维码不是当前真实共享入口。
- `MI4-SKY-LOG-HANDOFF-20261021.md`：之前的安装与回退参考，不需要为做小程序执行设备变更。

## 当前任务

用户要求小程序内一次扫码，连接 mi4-sky 热点并下载 LOG。手机端已部署；后续重点是正式 AppID 下的 Android/iOS 真机联调、保存/分享和异常恢复。

没有公网云端、设备控制、删除/上传接口，不要虚构。不要索要 AppSecret、Linux sudo 密码或微信登录密码，不要自动上传位置数据。涉及设备侧新增功能需另行向用户确认。

本包不含真实 Wi-Fi 密码或共享 token，不含固件/分区镜像，不是开机启动、GPS 开通或 ESP32 主表升级包。
