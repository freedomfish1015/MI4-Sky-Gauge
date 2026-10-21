# G 表透明区域：按方向峰值连接，不使用凸包

## 最新绘制更新：边缘圆润

`gauge_motion.py` 更新为局部二次贝塞尔圆角（转换成 Cairo 三次曲线），逻辑圆角最大 6 像素，并限于相邻边长的 42%。控制点局限在相邻顶点范围内，避免全局样条产生超调；保留径向凹陷，不平均或改写实际峰值数据。仅视觉轮廓在角点处圆滑化，原始顶点、G 数字不变。

最新绘图 SHA256：`86692cda53c065ea53cc8e27f4ed1d6f702a2f4e816edfa6b178af846f47ebb8`。
备份：`/home/umeko/desktop-offline/backups/rounded-envelope-before-6o7tp3d1`。
本次只重启 kiosk，motion PID 前后同为 3712，已累积区域不因本次部署重置。区域仍不自动过期，5 秒仍仅用于拖影。
40 项回归测试（包含圆角不改测量点、控制点边界、增量擦除）见 `rounded-envelope-device-tests-20261020.log`；合成视觉 QA 图 `directional-envelope-rounded-preview.png`。

## 最新更正：区域不自动消失

用户明确指出透明区域需要保留。已移除区域的 5 秒窗口，改用 `PersistentEnvelope`：本次进程运行期间持续积累 72 个方向峰值，圆点回中、零读数和时间经过都不会清除区域。设置中的“清除四向最大 G 值”同时清空该区域。**5 秒仅适用于圆点拖影**。此状态目前在内存中，重启运动服务/手机仍会重新开始，不宣称已实现跨重启保存。

最新手机 `mi4_motiond.py` SHA256：`d137b41dc41cf16b41596f793a30fe19dc4560c918c51bf5330da603bebe3054`。
备份：`/home/umeko/desktop-offline/backups/keep-envelope-before-pcm0fvl5`。
状态字段：`envelope_window_s=null`、`envelope_retention=until_peak_reset`。
绘图模块和自动回中算法没有改动；只重启 motion，未重启仪表。
新增“静止及零读数后区域仍保留、较小值不覆盖峰值、显式清除才移除”的测试；电脑 39 项通过，手机日志 `keep-envelope-device-tests-20261020.log`。

以下为前一版 5 秒区域的历史记录，已被上述更正替代。

用户参考图是带尖峰和凹陷的不规则径向轮廓。本轮保持现有白色主题、2.2 G 量程和加速度计自动回中，只改变透明区域的形成方式。

- 50 Hz 动态加速度采样进入有界滚动队列（最多 512 条）。
- 取最近 5 秒，按 72 个角度扇区（5°）分别取最大半径。
- 按角度连接实际测得的方向峰值，保留凹陷，不再取 convex hull。小的未采样角度间隙直接连接邻近顶点；整个半平面没有数据时经中心闭合，不凭空填满未测半平面。
- 22% 主题色不透明度填充、78% 轮廓线；圆角连接和原生抗锯齿。不是全主题模仿参考照片。
- 5 秒前的区域数据过期；四向 MAX 数字仍是原来的“清除峰值前的最大值”，两者有意区分。
- 原始采样、动态加速度自动回中算法、LOG、GPS、蓝牙、电量及 boot 均不改。

手机部署两个文件：

- `/usr/local/lib/obd-motion/mi4_motiond.py` SHA256 `84bd344517f69884a0ccf75e211135226bf31ad4471da1c7bcc916a89e1edb4d`
- `/home/umeko/desktop-offline/gauge_motion.py` SHA256 `d30b681509511e95f78736da079a873dd83601a1024e56eec82fa6304d05de9e`

备份：`/home/umeko/desktop-offline/backups/directional-envelope-before-gmm4d_tl`。
安装器 `install_directional_envelope_20261020.py` 有旧/新哈希检查及自动回退，仅重启 motion 与 kiosk。

电脑 38 项测试通过，包括径向凹陷保留、各方向峰值、5 秒过期并恢复较新较小值、有界内存，以及区域缩小时增量像素与整帧渲染一致（避免残影）。手机测试记录：`directional-envelope-device-tests-20261020.log`。

`directional-envelope-preview.png` 是合成数据预览，绝非真实车况；`preview_directional_envelope.py` 不写手机日志。
