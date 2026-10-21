# Umeko基础组件边界

基础来源：https://github.com/umeiko/umeko-Linux-phones ，本地来源commit `f132936d733f998c6fdb38cfe7bf3d1e8e2a7ba7`。

本地快照根目录没有明确许可证。下列历史基础脚本因此不作为本项目GPL代码收录：

- `/usr/local/sbin/usb-gadget-ncm-serial.sh`
- `/usr/local/sbin/ncm-serial-setup.sh`
- `/usr/local/lib/umeko/auto_resize_script.sh`
- `/usr/local/lib/umeko/modem-firmware-extract.sh`

服务配置保留了接口/调用路径，便于识别依赖，不等于包含可授权再发布的实现。完整系统构建者需与来源作者确认许可后自行取得，或另行开发替代实现。

mi4-sky所需语义：USB ConfigFS NCM+ACM组合、每机唯一USB身份、目标用户串口维护；modem固件由设备拥有者依自身许可取得/提取，不随源树分发；根文件系统扩容由本项目firstboot按预期UUID保护。不要沿用历史固定MAC/序列号到所有设备，不需要恢复旧auto_resize服务。

这里只描述接口与集成需求，不提供未授权基础代码，不承诺当前overlay是独立可启动的完整发行版。
