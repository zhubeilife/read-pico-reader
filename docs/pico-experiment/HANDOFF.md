# 小纸 Pico 固件优化 — 交接文档（给 task / Claude Code 会话）

> 生成时间：2026-11-18（UTC+8）。来源：与用户在 claude.ai 对话中的完整过程。
> 读完本文即可接手：目标、结论、已做改动、构建/刷机方法、下一步计划、注意事项都在这里。
> 同目录 `EDCBook分析报告.md` 是用户提供的原始分析报告（另一个工具生成，含若干错误，见 §8）。

> **2026-11-19 更新**：已快进合并 upstream 到 `fe62ecf`（Pico rc109，含 PR96：普通翻页改为"驱动→厂商定稿保持→12 擦白→4 重推黑"，且整屏含状态栏/页脚）。
> `build_turn_phases()` 已改为同样顺序，主机测试新增"普通翻页与 PR96 逐相一致"断言并通过；快速灰阶分支沿用整屏区域。
> 合并后分区溢出 0x7e0，已对 `ui_keyboard|ui_ime|datamatrix|app_onboarding` 追加 `-Os`（`book_ticket` 在 -Os 下触发 -Werror=format-truncation，未加入）。
> 新编译：版本 `0.3.3-rc109`，size 4,193,088，`free_app_bytes: 1216`，firmware sha256 `f5331649…`。
> **产物目录现为 `build/boards/packages/pico/`**（`flash-pico.command` 已同步）。合并前的实验 diff 备份在 `backups/exp-p0-gray8-pre-merge-*.patch`，另有 `git stash` 一份。
> 刷机仍未完成：设备在本 Firmware 下 esptool 无法自动进下载模式；设备上「BOOT 刷机」后串口节点未重新枚举（疑似经扩展坞/Hub），需直插重试。

---

## 0. 一句话现状

用户在自己 fork 的 kiikoread 固件上做"让小纸 Pico 翻页更快、接近 EDCBook 手感"的实验。
**实验分支 `exp/p0-gray8` 已改完并在 Mac 上编译成功（应用分区仅剩 352 字节），尚未刷机、尚未实测。**
下一步：用户双击 `flash-pico.command` 备份并刷机 → 对比"普通 / 快速灰阶"翻页 → 读串口日志决定后续。

---

## 1. 用户与约束（必须遵守）

- 用户：机器人软件工程师，**对话用中文**。
- 每条建议都要**可追溯到来源**（文件路径+行号、链接）；"据说"必须变成"据哪里说"。
- 偏好"搜索 → 核实 → 成文"三步分开；约束通常给得很具体。
- **只自用，不商用、不发布**（kiikoread 新版代码是 Personal Study License，个人学习/研究/测试允许）。
- **Python 用 3.14**（用户明确要求记住）。
- 没有用户明确要求时**不要 git commit / push**；当前改动均未提交。
- 设备：MindReset 小纸 Pico（型号 RDP-G01-W），ESP32-S3，16 MB Flash，屏 E0470A01 4.7" 684×1216、16 级灰。
- 用户另有一台 M5 Paper Mono 刷的 EDCBook 固件，喜欢它的速度与显示效果，这是对标对象。

---

## 2. 仓库与环境

| 项 | 值 |
|---|---|
| 本地 fork 路径 | `/Users/midea/Workspace/personal/read-pico-reader` |
| origin | `git@github.com:zhubeilife/read-pico-reader.git` |
| upstream | `https://github.com/wegooo-cell/read-pico-reader.git`（已 `remote add`，需用户本机 `git fetch upstream`） |
| 基线 commit | `a0cb3ac`（kiikoread `v0.3.3-rc108`，2026-11-17） |
| 实验分支 | `exp/p0-gray8`（**未提交**） |
| ESP-IDF | **v6.1**，源码 `/Users/midea/esp/esp-idf-v6.1`（仓库要求见 `boards/pico/dependencies.lock` `idf: 6.1.0`、CI `espressif/idf:v6.1`、`AGENTS.md` 第 144 行） |
| IDF_TOOLS_PATH | `/Users/midea/opt/esp`（工具链 xtensa-esp-elf 15.2.0_20251204 等；旧的 IDF 5.5 工具也在，互不影响） |
| Python | Homebrew `python@3.14`（3.14.10），IDF 环境 `/Users/midea/opt/esp/python_env/idf6.1_py3.14_env` |
| 板型选择 | `boards/pico`（**不是** `boards/metalio47`，那是另一款 4.7" 设备） |

### 环境坑（已踩过）
1. 用户 shell 里残留 `IDF_PATH=/Users/midea/opt/esp-idf-v5.4.4`（目录已不存在）→ `idf_tools.py` 报找不到 `esp_idf_version.h`。检查 `~/.zshrc`/`~/.zprofile`。
2. `export.sh` 只找不带版本号的 `python3`，macOS 自带的是 3.9.6 → 失败。解决：
   `export PATH="/opt/homebrew/opt/python@3.14/libexec/bin:/opt/homebrew/opt/python@3.14/bin:$PATH"`
3. 编译脚本：`python3 tools/build_firmware.py --board pico --python "$(which python)"`（需先 `. $IDF_PATH/export.sh`）。
   产物：`build/boards/pico/packages/pico/`（bootloader.bin、partitions.bin、firmware.bin、ota_data_initial.bin、flash-command.txt、SHA256SUMS.txt）；完整日志 `build/boards/pico/build.log`；ELF `build/boards/pico/build/Read_Pico.elf`；map `.../Read_Pico.map`。

### 两个一键脚本（在 fork 根目录，已加入 `.git/info/exclude`，不会提交）
- `build-pico.command`：设好上述环境变量 → `export.sh` → 编译；日志写 `build/build-pico-last.log`。
- `flash-pico.command`：自动找 `/dev/cu.usbmodem*` → **首次先整片备份 16 MB** 到 `backups/pico-full-*.bin`（备份失败不刷）→ 回车确认 → 按 flash-command 写 0x0/0x8000/0x10000/0xd10000（不全片擦除）→ 打开 `esp_idf_monitor`，并用 `script -q` 存档到 `build/pico-serial-*.log`（退出 Ctrl+]）。
- 在 Claude Code 里可以直接执行这些命令（终端可用）；在 claude.ai 聊天里只能让用户双击。

---

## 3. 关键技术结论（带出处）

### 3.1 为什么小纸 Pico 很难达到 EDCBook 的速度
- **每帧时间**：小纸帧周期固定 **11,090 µs**（官方 `components/e0470_epaper_waveform/README.md`："面板算法文档的设计点"；时序代码 `boards/pico/src/components/read_pico/read_pico_epd_timing.c` 会把每帧补齐到该目标）。EDCBook（960×540 屏）按总线推算约 5.5 ms/帧（报告 §20，推算未实测）。**同样相数，小纸慢约 2 倍。**
- **EDCBook 的"快"主要来自有损截断**：文字刷新只跑 14/17 步（报告 §12、§20，推算 77–94 ms）；报告 §27 自己承认"步=帧"尚未定论。
- **小纸生态的"无损跳相"**（`epd_set_leading_skip`，`boards/pico/src/components/read_pico/read_pico_init.c:50` 已开启）只跳开头全屏都不动的相，翻文字页时几乎跳不了，所以**保画质但不明显提速**。报告 §34 把它说成"比 EDCBook 更强"是混淆了画质与速度。
- e0470 波形的灰阶档全部在尾段（官方 README Trimmer 一节），所以**不能照搬 EDCBook 的"取前 N 相"**，否则文字抗锯齿会丢；小纸上应走裁剪器（保尾裁头）或厂家 GRAY8 表。

### 3.2 kiikoread 现状（`a0cb3ac`，Pico 板）
| 项 | 现状 | 位置 |
|---|---|---|
| 普通翻页波形 | GL16 37 相 + 12 相全屏擦白 + 4 相重推黑 = **53 相 ≈ 588 ms**（作者有意以速度换残影） | `boards/pico/src/main/display_reader_waveform.c` 宏 `READER_SOFT_TURN_SETTLE_EXTRA 12`（第 70 行）/`BLACK_EXTRA 4`；作者注释第 86–104 行 |
| 翻页分发 | `present()` 中 `s_reader_turn_pending && s_mode==MODE_GL16` 分支调用 `update_display_reader_area(...)` | `boards/pico/src/main/apps/app_book.c` 约 4700 行 |
| 翻页效果设置 | 0 普通 / 1 水波纹 / 2 速读黑白（实验分支新增 3 快速灰阶） | `boards/pico/src/main/settings.c`、`main/apps/book_reader_controls_{ui,runtime}.inc` |
| 裁剪参数 | `E0470_TRIM_ERASE_MAX 11 / SAT_CUT 5 / WHITE_SAT_CUT 0 / HOLD 3` → GC16 36 / GL16 37；上限 erase≤19、sat_cut≤13；`e0470_waveform_init()` 用 assert 校验帧数常量 | `components/e0470_epaper_waveform/include/e0470_epaper_waveform.h` 第 80–95 行（含"完整48相实测未改善残影"注释）；`.../e0470_waveform_trim.h`；`boards/pico/src/components/e0470_epaper_waveform/e0470_epaper_waveform.c` 约 294–333 行 |
| GRAY8 表 | 官方 8 级灰 GC16/GL16 各 30 相（官方称整屏约 360 ms vs 默认约 430 ms）；**基线里 Pico 阅读路径未使用** | 同上 .c；官方 README |
| 温度 | SY7636A 能读温度并接到 epdiy（`read_pico_board.c` `board_temperature`），但阅读刷新调用里**温度写死 25**；波形只有 0–50 °C 一档 → 温度目前不起作用 | `boards/pico/src/main/display.c`（`epd_hl_update_area*(..., 25, ...)` 多处） |
| 字形缓存 | 光栅 LRU 上限 320 KB（为插图解码让内存，见注释）；TTF glyf 只有 128 KB 进 PSRAM，其余按 4 KB 扇区从 TF 随机读（1-bit SD 每次"好几毫秒"）；只预排**下一页** | `boards/pico/src/main/font/ttf_font.c` 第 64–93、140–150 行；`app_book.c` 第 606、4382 行附近 |
| 已有计时 | `present draw=… display=… join=… ms` 常开；`METALIO_LOCAL_LATENCY` 编译开关默认关；`ttf_bench_begin/end`（glyphs/hits/misses/read_us/raster_us） | `app_book.c`、`components/epdiy/CMakeLists.txt:53`、`main/font/ttf_font.h` |
| 像素时钟 | 默认 18 MHz，欠载回退；帧周期是面板规定，不建议动 | `main/display.h:34`、`read_pico_epd_timing.c` |
| 分区 | ota_0/ota_1 各 4 MiB，storage(FAT) 5 MiB，末尾约 3 MB 空闲 | `boards/pico/partitions.csv` |
| 许可 | rc93 及以前 Apache-2.0；之后新增原创内容 Personal Study License | 仓库 `LICENSE` |

---

## 4. 实验分支 `exp/p0-gray8` 的改动（全部未提交）

| 改动 | 文件:行 | 说明 |
|---|---|---|
| **快速灰阶翻页**（P1-3） | `display_reader_waveform.c`：`build_turn_phases()`（原 soft-turn 构造抽成通用函数，**已验证与原版逐字节一致**），`display_reader_gray8_turn_waveform()` 第 167 行，宏 `READER_GRAY8_TURN_SETTLE_EXTRA/BLACK_EXTRA` 默认 0（第 152 行起，可 `-D` 覆盖） | 纯文字翻页改用 GRAY8 GL16 30 相 ≈ 333 ms（推算）；插图页/周期清理/封面不变 |
| 只链接 GRAY8 的 GL16 半张 | `boards/pico/src/components/e0470_epaper_waveform/e0470_epaper_waveform.c:223` `e0470_gray8_gl16_phases_only()`；声明在 `components/e0470_epaper_waveform/include/e0470_epaper_waveform.h` | 引用整张 `E0470_GRAY8_WAVEFORM` 会多链接 1.9 KB 的 GC16 表导致分区溢出 |
| 设置项 3 = 快速灰阶 | `boards/pico/src/main/settings.c:27` `READER_TURN_EFFECT_MAX 3`；`boards/pico/kiiko_board_config.h` `KIIKO_BOARD_READER_TURN_EFFECT_MAX 3`；`main/apps/book_reader_controls_ui.inc`（`RC_EFFECT_COUNT`、按钮宽度按数量计算，3 个时与原布局一致）；`..._runtime.inc`（循环与提示文案） | 阅读设置 → 翻页效果 出现第 4 个按钮"快速灰阶" |
| 翻页分发 | `app_book.c:4703` effect==3 时用 gray8 波形 | |
| **字形缓存放大**（P0-2） | `ttf_font.c:80` `TTF_CACHE_LIMIT_TEXT_ONLY 1 MiB`、`TTF_CACHE_PSRAM_RESERVE 1 MiB`；`cache_over_budget()` 第 1852 行；`ttf_font_cache_fit_default()` 第 1868 行；`app_book.c:4627` 显示插图前收回 320 KB | 仅在"关闭书内图片"时允许长到 1 MiB，且 PSRAM 最大连续块需 ≥ 1 MiB |
| **计时日志**（P0-1） | `display.c:994` `reader push mode= phases= skip= area= full= push=ms`；`app_book.c:4737` `turn summary effect= turn= cleanup= glyphs= hit= miss= sd_read= raster= paint= display=`（`turn_page()` 里用 `ttf_bench_begin/end` 采集，第 6400 行附近） | |
| 腾分区空间 | `main/CMakeLists.txt:388` 对 `ota_online / book_xteink_sync / app_cloud_sync / online_font / online_font_store / pmu_selftest` 加 `-Os` | 都不在渲染路径；沿用原作者对 settings/files 用 `-Os` 的做法 |
| 主机测试 | `tools/pico_reader_turn_host_test.c`（编译命令写在文件头） | 断言：普通 = 37+12+4=53 相；快速灰阶 = 30 相且与厂家表只差"黑→黑擦白" |

### 验证状态
- 主机测试：通过（容器与用户 Mac 上都跑过）：`ordinary turn 53 phases (~588 ms), fast gray 30 phases (~333 ms)`。
- 完整固件：ESP-IDF v6.1 编译成功，`free_app_bytes: 352`，size 4,193,952，firmware.bin sha256 `3a7763ab…`。
- **未做**：刷机、真机灰阶/残影/耗时测量。
- 已踩坑：①声明顺序（`s_turn_glyphs` 需在 `present()` 之前声明，已修）；②分区溢出 0x930（已用上面两招解决）。
- 原仓库 `tools/run_display_navigation_tests.sh`、`tools/pico_fast_text_host_test.py` 等在基线上也跑不通（路径假设问题），与本改动无关。

### 已知风险/注意
- 选"快速灰阶"时做的配置备份，刷回上游固件后恢复会失败（上游校验 `BK_TURN <= 2`）；备份前切回"普通"。
- GRAY8 表没有 kiikoread 对默认 GL16 做的 `e0470_gl16_white_tick` 白色微调，注意白底是否干净。
- 新文案"快速灰阶 / 快速灰阶翻页"未进英文 locale 目录（中文界面不影响）。
- **不要用在线升级**，会被上游固件覆盖。
- 应用分区只剩 352 B：以后加功能先腾空间（例如对更多非渲染文件 `-Os`，或精简日志）。

---

## 5. 测试方案（刷机后）

1. 打开纯文字书，"普通"翻 10 页左右；阅读设置 → 翻页效果 → "快速灰阶"，再翻 10 页左右。
2. 读 `build/pico-serial-*.log`：
   - `reader push ... phases=53 ...` vs `phases=30 ...`：确认切换生效、比较 `push=`；
   - `turn summary ... sd_read= raster= paint= display=`：时间花在哪（读卡 / 光栅 / 排版 / 推屏）。
3. 肉眼：字边缘是否发糙（8 级灰）、白底残影。
4. 若残影明显：缩短"全刷间隔"，或编译时加 `-DREADER_GRAY8_TURN_SETTLE_EXTRA=4`（多约 44 ms）。

---

## 6. 优化路线图（按优先级；✅=已在实验分支，⏳=待做）

**P0 几乎零成本**
1. ✅ 翻页计时日志（借鉴 EDCBook 分阶段汇总日志，报告 §5.2）。
2. ✅ 关书内图片 + 字形缓存放大（借鉴 EDCBook 纯文本模型 §41；RickyOS 阅读字体 1 MiB PSRAM 字形缓存 `docs/engineering/sd-card-font-cache.md`）。kiikoread 已有"关闭书内图片"开关（README 第 136 行）。

**P1 核心提速（不碰厂家 LUT 数据）**
3. ✅ 文字翻页用 GRAY8（借鉴 Pico Page / VanOS / AuraReader，报告 §32.2、§32.5）。
4. ⏳ 翻页档位：把额外 12+4 相做成"极速 0 / 均衡 / 洁净 12+4"（借鉴 EDCBook `TEXT_FAST/BALANCED/CRISP` profile，报告 §5、§12）。最小实验：把两个宏改 0 编译对比。
5. ⏳ 自适应清残影：按"快档翻页数"或累计变化面积触发 GC16（借鉴 EDCBook `HISTORY_REBASE`、CrossLink"差分链上限" §32.6、Just Read/Pico Page"局刷 N 次后全刷"）。现状只有固定 5/10/15/30 页。与 3/4 一起做。

**P2 看日志决定**
6. ⏳ 阅读字体放进空闲 OTA 分区做 flash 缓存（借鉴 RickyOS：非活动 OTA 槽作为一份阅读字体缓存，`sd-card-font-cache.md`）。条件：日志显示冷页卡在 `sd_read`。代价：每次 OTA 后要重建；字体需 < 4 MB（如 GB2312 子集）。不需改分区表。
7. ⏳ 连续快翻用 8 帧 DU（`E0470_FOLLOW_WAVEFORM`，约 90 ms），停下后 GL16 收尾（借鉴 EDCBook `TEXT_RAPID_BEGIN/CONTINUE/SETTLE`）。只对快速连翻有用。
8. ⏳ 预排上一页（非借鉴，自提；多占约 416 KB PSRAM）。

**P3 收益不确定/风险高**
9. ⏳ 更狠的自定义裁剪（EDCBook 截断思路；注意 CrossLink 反而更保守用了 39 相，§32.5）。只在 P1 后仍嫌慢时做，需真机反复调残影。
10. ⏳ 温度分档：先把写死的 25 换成 `epd_ambient_temperature()`（注意 SY7636A 需电源轨上电后读数才有效），冷时用完整 48 相/洁净档。**冬天观察到冷天发灰再做**。
11. ⏳ 色调曲线 + 误差扩散（CrossLink §32.7）：只对封面/壁纸有用，kiikoread 已有 16 级 + 有序抖动（README 第 180 行）。

**明确不建议**
- 照搬 EDCBook 整套预烘焙字库分区（改分区表、失去字号/字体灵活性；第 6 项代价更小）。
- CrossLink 的 DC 平衡（只有字符串证据）。
- 缩短帧周期 / 改像素时钟（面板规定，硬件风险）。
- 引入完整 FreeType（300 PPI 下汉字 hinting 收益小；RickyOS 在小纸上正文其实只有 4 级灰，见其 `docs/engineering/read-pico.md`）。

**参考的同类固件仓库**：`MindReset/read_pico_firmware`（官方基线，Apache-2.0）、`chinoryunqin/RickyOS`、`XHFO/XH-View-OS-For-Pico`、`Yana-Hangabina/cpyos`、`yiifanrecyclable/if-ink-OS`、`0x1abin/freeink-sdk`。

---

## 7. 推荐的工作方式

- 每做一项：改代码 → `tools/pico_reader_turn_host_test.c` 之类主机测试 → `build-pico.command` → 看 `free_app_bytes` → `flash-pico.command` → 读串口日志 → 用户肉眼确认。
- 改动尽量集中在 `boards/pico/src/main/display_reader_waveform.c` 和新文件里，便于定期合并 upstream（作者更新很勤：35 个 release）。
- 用 `git fetch upstream && git merge upstream/main` 同步（只能在用户 Mac 上执行）。

---

## 8. 原始分析报告（`EDCBook分析报告.md`）里已发现的错误

1. §34 把"无损跳相"说成比 EDCBook 截断"更强"——只对画质成立，对速度几乎无帮助（§3.1）。
2. §41.4 用小纸相数（37/48）乘 EDCBook 的 5.5 ms/相，时间低估一半；且"剔除图片"对纯文字页无提速，kiikoread 已有关图开关。
3. §38 说温度分档"改动面很干净"——代码容易，难的是没有厂家多温度 LUT 数据。
4. 标题写 17 个系统，表里 18 个；§32.1 第 4 条仍称 CrossLink 为 B 族（§39 才更正）。
5. 称 if-ink OS 独有 `e0470_page_turn`——kiikoread 也有（水波纹引擎）。
6. 称 B 族在小纸上 16 级灰——RickyOS 正文是 4 级灰。
7. 称 CPYOS `absolute_grayscale` 是 16 灰实验——实为抖动算法单元测试。
8. CrossLink 排第二（S2）不适合文字阅读：其优势在图片（色调曲线/误差扩散），且闭源不可改。

---

## 9. 关键数字速查

| 项 | 数值 | 来源 |
|---|---|---|
| 小纸帧周期 | 11,090 µs | 官方 e0470 README |
| 普通翻页 | 53 相 ≈ 588 ms（推算） | `display_reader_waveform.c` + 主机测试 |
| 默认 GL16 | 37 相 ≈ 410 ms（推算）；官方称整屏约 430 ms | 同上 / 官方 README |
| GRAY8 GL16 | 30 相 ≈ 333 ms（推算）；官方称整屏约 360 ms | 同上 |
| FOLLOW DU | 8 帧 ≈ 90 ms | `E0470_FOLLOW_WAVEFORM` |
| EDCBook 文字 | 14–17 步 ≈ 77–94 ms（推算，未定论） | 报告 §20、§27 |
| 应用分区余量 | 352 B（实验分支） | 编译输出 `free_app_bytes` |

---

## 10. 首次真机结果（2026-11-19，rc109 实验固件，日志 `build/pico-serial-20261119-1531.log`）

| 翻页效果 | 相数（跳过） | 刷新区域 | 推屏 push（次数 / 最小 / 中位 / 最大） |
|---|---|---|---|
| 普通（effect=0） | 53（0） | 整屏 684×1216 | 10 / 651 / 666.5 / 669 ms |
| 快速灰阶（effect=3） | 30（1） | 整屏 684×1216 | 9 / 374 / 386 / 391 ms |

- 推屏少约 280 ms（−42%）。按 89.15 Hz（11.22 ms/帧）算：53×11.22≈595、29×11.22≈325，实测多出约 60–70 ms，是每次推屏的固定开销。
- 预排命中的翻页：`paint` 24–40 ms，`glyphs=0`。少数翻页出现 `paint` 634–1542 ms、`raster` 90–451 ms（`glyphs` 80–3206），疑为跨章或切换效果后预排失效导致的重排。`sd_read` 全为 0，因为当前用的是内建字体（日志 `using builtin`），**瓶颈不在读卡**。
- 普通模式约第 10 页触发一次周期清理：正文 GC16 48 相 608 ms，页脚另走 8 相 DU 59 ms。
- 其他：TF 卡 `free=0 MB`；开机后「BOOT 刷机」会让设备卡在下载模式，需长按电源键 10 s 断电再开机。

### 10.1 第二轮（2026-11-19 15:42，GRAY8 30+4 擦白，fw `8858b1c1…`，日志 `build/pico-serial-20261119-1541.log`）

| 翻页效果 | 相数（跳过） | 刷新区域 | 推屏耗时 |
|---|---|---|---|
| 快速灰阶 30+4 | 34（1） | 整屏 | 11 次 432–438 ms（中位约 433） |
| 速读黑白（effect=2） | DU 20 相（日志未单独打 push 行） | 正文；页码约 67 ms 后另走 8 相 DU 59 ms | 10 次 304–310 ms |

- 加 4 相擦白多花约 47 ms（386→433）。固定开销仍约 60–80 ms/次。
- 快速灰阶第 10 页触发周期清理（GC16 48 相 603 ms + 页脚 59 ms）。
- 两种模式各有一次 `paint` 514/532 ms 但 `glyphs=0`，不是光栅化，原因待查（排版/存进度？）。
- **用户实屏验收（2026-11-19）**：30 相无额外擦白时残影明显；30+4 擦白后残影可以接受。默认值定为 `READER_GRAY8_TURN_SETTLE_EXTRA 4 / BLACK_EXTRA 0`。

## 11. 上游 PR（2026-11-19）

- https://github.com/wegooo-cell/read-pico-reader/pull/97 ，分支 `zhubeilife:feat/pico-fast-gray-turn`（commit `80b72ac`，基于 upstream `fe62ecf`），只含快速灰阶 30+4，Apache-2.0。作者用 GitHub noreply 邮箱提交。
- 工作树：`../read-pico-reader-fastgray`（PR 分支）、`../read-pico-reader-base`（upstream main 对照，可删）。
- 与实验分支差异：PR 不含计时日志、字形缓存放大；`-Os` 列表为 `online_font|online_font_store|ota_online|pmu_selftest|ui_keyboard|ui_ime|datamatrix`（Pico 余 2,320 B）。
- macOS 上按 build.yml 跑主机测试：上游 main 本地即有 16 项失败，PR 无新增；`reading_settings_host_test.py` 已改为按板型按钮数。

## 12. 停顿排查 + 连续快翻短波形（2026-11-19 16:22，日志 `build/pico-serial-20261119-1622-retest.log`，fw `bea1ca32…`）

改动（仅实验分支，`app_book.c` / `display.c`）：
- `READER_DEFER_TURN_SAVE`：第 8 页的 `save_progress` 不再在翻页路径上执行，改为空闲 1.5 s 后写。
- `READER_RAPID_TURN`：距上次翻页完成 <500 ms 且无清理、效果为普通/快速灰阶时，正文改推 8 帧 FOLLOW DU（`update_display_rapid_turn`）；停手 700 ms 后用原效果补一次定稿。

实测（普通效果）：

| 场景 | 次数 | 推屏 | 备注 |
|---|---|---|---|
| 慢翻（普通 53 相） | 12 | 661–668 ms（刚上电前两次约 730） | `save=0ms`，停顿消失 |
| 快翻 DU | 19 | 129–134 ms | 每次另有页脚 8 相 DU 59 ms |
| 快翻定稿 | 1 | 638 ms（53 相） | 停手约 770 ms 后触发 |
| 周期清理 GC16 | 3 | 603–609 ms | 第 81、87、95 页；后两次打断了快翻 |
| 延后存进度 | 2 | 493 / 574 ms | 都在空闲时，`record` 写入占 488 / 568 ms |

- **停顿根因确认**：`book_progress_save` 写记录约 0.5 s（TF 卡 `free=0 MB`）。延后后翻页路径不再受影响。
- 往回翻时上一页没有预排：`paint cached=0` 74–81 ms（`glyphs` 约 230）。
- 待改：快翻期间推迟周期清理，留到定稿时做；页脚 DU 可在快翻时省掉、定稿统一刷；可预排上一页。
- 待用户实屏判断：快翻 DU 的残影、定稿后是否干净。

## 13. 快翻三项优化（2026-11-19 16:45，日志 `build/pico-serial-20261119-1645-keep.log`，剩余 832 B）

改动（`app_book.c`）：
- 快翻中轮到周期清理时记 `s_rapid_cleanup_due`，停手定稿改走 GC16 48 相；定稿前就慢翻则在该页补做。
- 快翻时页脚不单独 DU，留给定稿；定稿被打断时元数据节拍约 1 s 后兜底。
- `READER_KEEP_PAGES`：本页 / 上一页正文点阵与 `s_next_fb` 三缓冲轮换（多约 0.8 MB PSRAM），往回翻和同页定稿直接复用。

实测：
- 5↔6 来回快翻 30+ 次：全部 `cached=1`，paint 16–19 ms，DU 推屏 118–120 ms，没有页脚 DU，也没有中途清理。
- 两次定稿都带清理：GC16 577 / 587 ms + 页脚 63 ms。
- 新发现：跨章时 `save_progress` 仍在翻页路径上（`save=495/574ms`），再加 `load_chapter` 58–137 ms 和新章首页排版 134–185 ms，跨章那一页共 0.77–0.81 s。短章节的书很明显。

## 14. 跨章保存延后（2026-11-19 16:51，日志 `build/pico-serial-20261119-1651-chsave.log`）

- 跨章的 `save_progress` 也改为置 `s_progress_save_due`，停手后写（498 ms，空闲时）。跨章那页 `save=0ms`。
- 跨进 52 页的第 4 章：`load_chapter` 567 ms + 首页排版 180 ms（848 字），这一页约 0.75 s。现在跨章的主要开销是读入并排版新章，要再快需预读下一章。
- 发现并修复：快翻中欠下的清理没在随后的普通清理页作废，停手后又做了一次 GC16（510 ms）。现在任何一页做了清理，就同时取消欠下的清理和待定稿（fw 剩余 928 B）。
- 第 4 章首页之后那一页 `turn=0` 且没有预排（`paint cached=0` 382 ms），疑为首页带插图或题头，导致不走预排，未细查。
