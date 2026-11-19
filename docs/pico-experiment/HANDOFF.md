# 小纸 Pico 翻页提速实验 — 交接文档

> 最后整理：2026-11-19。读完本文即可接手：当前状态、怎么编译刷机和看日志、做过什么及实测结果、下一步按优先级做什么。
> 同目录 `EDCBook分析报告.md` 是用户提供的原始对标报告（其他工具生成，有若干错误，见 §9）。
> `serial_log.py` 是串口抓日志脚本（见 §2.4）。

---

## 0. 现状速览

- **目标**：让小纸 Pico 上的 kiikoread 翻页更快，手感接近 M5 Paper Mono 上的 EDCBook。
- **实验分支** `exp/p0-gray8`，提交 `74a3fb3`（已合并上游 `0d2411d`，含 #98）。设备上刷的就是这个提交的固件（sha256 `0bcb195e…`，剩余 640 B）。
- **已完成并实测**：
  - 快速灰阶翻页：434 ms，普通翻页是 666 ms。
  - 翻页路径上不再写进度：去掉了约 0.5 s 的周期停顿。
  - 连续快翻用短 DU：每页约 140 ms。
  - 快翻时推迟清理和页码刷新，往回翻复用上一页。
- **上游 PR**：
  - [#97](https://github.com/wegooo-cell/read-pico-reader/pull/97)：快速灰阶。
  - [#99](https://github.com/wegooo-cell/read-pico-reader/pull/99)：延后保存与快翻。
  - [#100](https://github.com/wegooo-cell/read-pico-reader/pull/100)：进度文件原地覆盖（分支 `fix/progress-inplace-write`，工作树 `../read-pico-reader-progress`，Pico 剩 96 B，S31 剩 54,832 B）。
  - 都在等维护者批准 CI，还没有审阅意见。
- **暂停中（2026-11-19）**：用户决定等三个 PR 合入后再继续。接手时先 `git fetch upstream`，看 PR 状态，再把上游合进实验分支。
- **还没在设备上验证**：PR #99 分支本身的固件（实验分支已含同样逻辑，并已实测）。

---

## 1. 用户与约束（必须遵守）

- 对话用中文。结论要可追溯：给出文件:行号、日志文件或链接。
- 只自用，不商用、不发布。用户没明确要求时不 commit、不 push。
- 提交和 PR 的署名用 `zhubeilife <7824663+zhubeilife@users.noreply.github.com>`。本机 git 配的是工作邮箱，不能进公开仓库。
- 给上游的 PR 用 Apache-2.0，只放功能本身；计时日志和实验文档不进 PR。
- Python 用 3.14。
- 设备上不要用在线升级（会被上游固件覆盖）。
- 不写 SY7636A 的 VCOM、TPS OTP、eFuse，不改供电、VCOM 和分区表。
- 设备：MindReset 小纸 Pico（RDP-G01-W），ESP32-S3，16 MB Flash，E0470A01 4.7" 684×1216、16 级灰。

---

## 2. 环境、编译、刷机、日志

### 2.1 仓库与工作树

| 项 | 值 |
|---|---|
| 主工作树 | `/Users/midea/Workspace/personal/read-pico-reader`，分支 `exp/p0-gray8` |
| origin / upstream | `zhubeilife/read-pico-reader` / `wegooo-cell/read-pico-reader` |
| PR #97 工作树 | `../read-pico-reader-fastgray`，分支 `feat/pico-fast-gray-turn`（`80b72ac`） |
| PR #99 工作树 | `../read-pico-reader-rapid`，分支 `feat/pico-rapid-turn`（`643d3bd`，基于上游 `0d2411d`，含 #98） |
| 对照工作树 | `../read-pico-reader-base`（上游 `fe62ecf`，已无用，可删） |
| 备份 | `backups/pico-full-20261119-1526.bin`（整片 16 MB，原厂 rc109 状态，sha256 在同名 `.sha256`）；`backups/exp-p0-gray8-pre-merge-20261119-1457.patch` |

实验分支已合并上游 `0d2411d`（#98：水波纹、速读黑白每页后把状态栏和进度条再刷一次白；普通、快速灰阶、快翻和定稿跳过，与 PR #99 相同）。

### 2.2 编译

```
cd /Users/midea/Workspace/personal/read-pico-reader
export IDF_TOOLS_PATH=/Users/midea/opt/esp
python3 tools/build_firmware.py --board pico --idf-pico /Users/midea/esp/esp-idf-v6.1 \
  --python /Users/midea/opt/esp/python_env/idf6.1_py3.14_env/bin/python
```

- 产物在 `build/boards/packages/pico/`（`firmware.bin` 等），完整日志在 `build/boards/pico/build.log`。要看输出 JSON 里的 `free_app_bytes`。
- S31 用 `--board metalio47 --idf-metalio47 /Users/midea/esp/esp-idf-v6.1`。
- **新工作树第一次编译**会报找不到 `xtensa-esp32s3-elf-gcc`。原因：主工作树的 CMakeCache 里存了编译器全路径，新工作树没有。解决办法是把 15.2 工具链加进 PATH：
  `export PATH="$IDF_TOOLS_PATH/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin:$IDF_TOOLS_PATH/tools/riscv32-esp-elf/esp-15.2.0_20251204/riscv32-esp-elf/bin:$PATH"`
- 不要用 `--tools`：它会按通配符先找到 14.2 工具链，版本校验失败。
- 4 MiB 应用分区几乎满了，加代码前先看余量。不在阅读路径上的源文件已按 `-Os` 编译（`main/CMakeLists.txt` 里 Pico 的 `-Os` 列表）。`book_ticket` 不能加 `-Os`，会触发 `-Werror=format-truncation`。

### 2.3 刷机

- **设备正常开机时**，只写应用分区，约 25 s，不需要 BOOT 模式，设置、进度和 TF 卡都不受影响：
  ```
  cd build/boards/packages/pico
  /Users/midea/opt/esp/python_env/idf6.1_py3.14_env/bin/python -m esptool --chip esp32s3 \
    --port /dev/cu.usbmodem1101 --before usb-reset --after hard-reset write-flash \
    --flash-mode dio --flash-size 16MB --flash-freq 80m 0x10000 firmware.bin
  ```
- 刷机前要先停掉占着串口的日志脚本。
- 设备必须直插，不要经过 Hub 或扩展坞。
- `flash-pico.command`（本地脚本，已加入 `.git/info/exclude`）会写全部四个分区。
- 如果用了设备上的「BOOT 刷机」，刷完设备会停在下载模式（PMU 拉住了 BOOT 脚）。解决：长按电源键 10 s 强制断电，再按 1 s 开机。

### 2.4 抓日志

`esp_idf_monitor` 需要 TTY，在 Claude Code 里用 `serial_log.py`（会自动重连）：

```
/Users/midea/opt/esp/python_env/idf6.1_py3.14_env/bin/python -I docs/pico-experiment/serial_log.py \
  build/pico-serial-$(date +%Y%m%d-%H%M)-<标签>.log 3600
```

- 放后台跑，测完再分析。锁屏或浅睡会让串口断开，所以测试时不要锁屏。
- 常用过滤：`sed 's/\x1b\[[0-9;]*m//g' <log> | grep -a -E "turn chapter=|turn summary|reader push|reader rapid|rapid settle|progress|paint cached"`

日志行的含义（实验分支专有）：

| 日志 | 含义 |
|---|---|
| `reader push mode= phases= skip= area= full= push=ms` | 一次阅读区推屏：模式、波形总相数、跳过的前导相、区域、耗时 |
| `reader rapid push area= push=ms` | 快翻 DU 推屏 |
| `turn summary effect= turn= rapid= cleanup= save= load= glyphs= ... raster= paint= display=` | 每页汇总。`paint` 是整个 `turn_page` 的耗时（含保存、读章和排版），`display` 是推屏耗时 |
| `paint cached=0/1 ms=` | 本页是否直接用了现成点阵 |
| `rapid settle page= cleanup=` | 停手后的定稿；`cleanup=1` 表示定稿走 GC16 清理 |
| `progress save prep= flush= ticket=` / `progress flush record=` | 进度写入的耗时拆分 |
| `deferred progress save Nms` | 停手后执行的延后保存 |

---

## 3. 关键技术结论（带出处）

- **帧时间是硬限制**：
  - 小纸全屏扫描 89.15 Hz，即 11.22 ms/帧；快扫描 142.65 Hz。帧周期由面板规定，见官方 `components/e0470_epaper_waveform/README.md` 和 `boards/pico/src/components/read_pico/read_pico_epd_timing.c`。
  - EDCBook 的屏按推算约 5.5 ms/帧（报告 §20），所以同样相数，小纸慢约一倍。
  - 每次推屏还有约 60–80 ms 固定开销（§10.1 的实测）。
- **EDCBook 快在有损截断**（文字只跑 14–17 步），小纸不能照搬：
  - e0470 波形的灰阶档都在尾段，只取前 N 相会丢抗锯齿。
  - 要么用厂家的 GRAY8 表，要么用裁剪器保尾裁头（官方 README 的 Trimmer 一节）。
  - 无损跳相（`epd_set_leading_skip`）在文字页上几乎跳不了相。
- **普通翻页的组成**：
  - GL16 37 相 + 12 相整屏擦白 + 4 相重推黑，共 53 相，实测 661–668 ms。
  - 顺序按上游 PR96：驱动 → 厂商定稿保持 → 擦白 → 推黑。
  - 代码在 `boards/pico/src/main/display_reader_waveform.c` 的 `build_turn_phases()`。
- **进度写在内部 flash 的 FAT 文件里，不在 NVS，也不在 TF 卡**：
  - `main/book/book_progress_files.inc`：每本书两个文件 `/flash/progress/<哈希>.0/.1`，交替写不在用的那个，写完 fsync 再回读校验。NVS 只存序号 `seq` 和最后一本书 `last`。
  - 存储分区是 `storage`（5 MiB），FAT 挂在磨损均衡上，扇区 4 KB（`CONFIG_WL_SECTOR_SIZE=4096`、`CONFIG_FATFS_SECTOR_4096`），改一点也要擦写整块 4 KB。
  - 原写法 `fopen("wb")` 先截断再重新分配空间：打开 206–278 ms，fsync 273–345 ms，一次 488–561 ms；NVS 提交只要 1 ms（§10.7）。
  - 实验分支改为同长度时 `r+b` 原地覆盖：打开 2 ms，fsync 136–137 ms，一次 152–154 ms。
  - 之前日志里的 `free=0 MB` 说的是 TF 卡，和进度写入无关。
- **温度没用上**：阅读刷新时温度写死为 25（`boards/pico/src/main/display.c` 多处 `epd_hl_update_area*(…, 25, …)`），波形本来也只有一档温度。
- **字形缓存**：
  - 默认光栅缓存上限 320 KB。实验分支在“关闭书内图片”时允许长到 1 MiB（`ttf_font.c` 的 `TTF_CACHE_LIMIT_TEXT_ONLY`）。
  - 目前测试用的都是内建字体（日志 `using builtin`，`sd_read` 全为 0），这项还没评估。

---

## 4. 已完成的改动与实测

所有改动都在实验分支 `exp/p0-gray8`（`74a3fb3`）。

| # | 改动 | 位置 | 设备实测 | 进上游 |
|---|---|---|---|---|
| 1 | **快速灰阶**（翻页效果 3）：GRAY8 GL16 30 相 + 4 相擦白，共 34 相 | `display_reader_waveform.c` 的 `display_reader_gray8_turn_waveform()`；`e0470_gray8_gl16_phases_only()`；设置和界面在 `settings.c`、`kiiko_board_config.h`、`book_reader_controls_{ui,runtime}.inc` | 432–438 ms（普通 666 ms）。30 相不擦白时残影明显，30+4 用户认可 | #97 |
| 2 | **延后保存进度**：第 8 页和跨章时的保存改到停手 1.5 s 后（`READER_DEFER_TURN_SAVE`） | `app_book.c` 的 `turn_page()`、`on_tick()` | 翻页 `save=0ms`，保存 493–574 ms 都发生在空闲时 | #99 |
| 3 | **连续快翻用短 DU**：距上一页推完不足 500 ms 时，正文推 8 帧 FOLLOW DU；停手 700 ms 后用当前效果定稿（`READER_RAPID_TURN`） | `display.c` 的 `update_display_rapid_turn()`；`app_book.c` | 推屏 118–134 ms，定稿 638 ms | #99（只对普通效果） |
| 4 | **快翻时推迟清理和页码刷新**：周期清理留到定稿时做（GC16）；页码不单独 DU；做过清理的页会取消欠下的清理和定稿 | `app_book.c` | 快翻中不再有清理和页码刷新；定稿 577–587 ms + 页码 59–63 ms。取消修复已实测（§10.6） | #99 |
| 5 | **保留本页和上一页的点阵**：与 `s_next_fb` 三块缓冲轮换，往回翻和同页定稿直接复用（`READER_KEEP_PAGES`，最多多占约 0.8 MB PSRAM） | `app_book.c` 的 `paint_reading()` | 来回翻 paint 从 74–81 ms 降到 16–19 ms | #99 |
| 6 | 字形缓存在“关闭书内图片”时放大到 1 MiB | `ttf_font.c`、`app_book.c` | 没评估（用的内建字体） | 否 |
| 7 | 计时日志（§2.4 的表） | `display.c`、`app_book.c` | — | 否 |
| 8 | 主机测试：普通翻页与 PR96 逐相一致，快速灰阶 = 30 + 4 | `tools/pico_reader_turn_host_test.c`（编译命令在文件头） | 通过 | 否 |

### 4.1 实验分支和 PR #99 的差别

- PR #99 基于上游 `0d2411d`。快翻时也跳过 #98 的状态栏和进度条刷白，留给定稿。
- PR #99 只对普通效果启用快翻，因为上游没有快速灰阶。
- PR #99 没有日志。`-Os` 列表和 #97 完全相同，两个 PR 都合并时不冲突，但合并后的 Pico 镜像可能超出分区。
- 编译余量：
  - PR #99：Pico 剩 1,440 B，S31 剩 54,928 B。
  - PR #97：Pico 剩 2,320 B。
- 主机测试在 macOS 上，有无改动都是 34 项失败（环境原因），没有新增失败。

---

## 5. 关键数字速查（实测，Pico，2026-11-19）

| 场景 | 耗时 |
|---|---|
| 普通翻页推屏（53 相） | 661–668 ms（亮屏后前两次约 730 ms） |
| 快速灰阶推屏（34 相） | 432–438 ms |
| 速读黑白推屏（DU 20 相） | 304–310 ms + 页码 59 ms |
| 快翻 DU 推屏 | 118–134 ms |
| 周期清理 GC16（48 相，正文） | 577–609 ms |
| 页码单独 DU | 59–67 ms |
| 预排命中的排版 | 15–19 ms |
| 未命中的排版（同章） | 50–185 ms，取决于字数 |
| 一次进度写入（FAT 文件） | 原写法 488–574 ms；原地覆盖后 152–154 ms |
| `load_chapter` | 58–137 ms（短章），567 ms（52 页的章） |

日志都在 `build/`：`pico-serial-20261119-{1531,1541,1622-retest,1645-keep,1651-chsave}.log`。

---

## 6. 下一步（按优先级）

1. **往回连续翻页时也预排**（中）：
   - 现在只预排下一页，再留一份上一页。往回连续翻时，每页都要现排 65–159 ms（§10.6）。
   - 做法：按上一次翻页方向决定预排的目标页（往回就排上一页），预排结果放进空出的缓冲。
2. ~~进度文件原地覆盖~~：已提 PR #100（§10.7）。剩下的 137 ms 是 fsync 时重写数据块和目录块，再省要动 FatFs 或换存储方式，不建议。
3. **插图页提速**（中到大）：
   - 带插图的页不预排，也不走普通翻页和快翻：排版加解码 290–410 ms，推屏走正文区 GL16（§10.6）。
   - 可以先试着在空闲时预解码下一页的插图，要注意 PSRAM（插图解码会先回收缓存）。
4. **预读下一章**（大）：
   - 跨进大章还要约 0.75 s（读章 567 ms + 首页排版 180 ms）。短章节多的书收益最大。
   - 难点：要第二份章节文本和排版缓冲，增加内存，还要处理插图页和跨章往回翻。
5. **跟进 PR #97、#99**（被动）：维护者批准 CI 或提意见后处理；两个都合并时检查 Pico 镜像大小。
6. **评估 1 MiB 字形缓存**（中）：
   - 用 TF 卡上的外置字体测冷页的 `sd_read` 和 `raster`。
   - 没收益就删掉这项，省出代码空间。
   - 只有用外置字体的人会受益。
7. **普通翻页的擦白档位**（小，用户已暂缓）：把普通翻页额外的 12+4 相做成可选档位，用残影换速度。
8. **温度分档**（低）：先把写死的 25 换成实测温度。等冬天出现冷天发灰再做。

**明确不建议**：
- 照搬 EDCBook 的预烘焙字库分区：要改分区表，还失去字号和字体的灵活性。
- 缩短帧周期或改像素时钟：面板规定的参数，有硬件风险。
- 引入完整 FreeType。
- CrossLink 的 DC 平衡：只有字符串证据。

---

## 7. 已知问题与风险

- 选了“快速灰阶”后做的配置备份，刷回上游固件后恢复会失败（上游校验 `BK_TURN <= 2`）。备份前先切回“普通”。
- 延后保存：停手 1.5 s 内突然断电，会丢掉最近几页或这一章的进度。锁屏和退出时仍会当场保存。
- 快翻 DU 期间正文是阈值后的黑白，状态栏不更新，要等定稿。
- `-Os` 不宜继续扩大到阅读路径上的文件，会拖慢渲染。
- “快速灰阶”文案只进了中文和 `en.json`。

---

## 8. 参考

- 同类固件：
  - `MindReset/read_pico_firmware`：官方基线，Apache-2.0。
  - `chinoryunqin/RickyOS`：用非活动 OTA 槽缓存字体，见 `docs/engineering/sd-card-font-cache.md`。
  - 其他：`XHFO/XH-View-OS-For-Pico`、`Yana-Hangabina/cpyos`、`yiifanrecyclable/if-ink-OS`、`0x1abin/freeink-sdk`。
- 借鉴关系：
  - EDCBook 的 `TEXT_RAPID_BEGIN/CONTINUE/SETTLE`，对应 §4 第 3 项。
  - EDCBook 的分阶段汇总日志，对应 §4 第 7 项。
  - Pico Page、VanOS、AuraReader 文字页用 GRAY8，对应 §4 第 1 项。

---

## 9. 原始报告（`EDCBook分析报告.md`）里的错误

1. §34 说“无损跳相”比 EDCBook 截断更强：这只对画质成立，对速度几乎没帮助。
2. §41.4 用小纸相数乘 EDCBook 的 5.5 ms/相，时间低估了一半。
3. §38 说温度分档改动很干净：代码好改，难在没有厂家多温度 LUT。
4. 标题写 17 个系统，表里列了 18 个；§32.1 仍称 CrossLink 为 B 族（§39 才更正）。
5. 说 if-ink OS 独有 `e0470_page_turn`：kiikoread 也有（水波纹引擎）。
6. 说 B 族在小纸上是 16 级灰：RickyOS 正文是 4 级灰。
7. 说 CPYOS 的 `absolute_grayscale` 是 16 灰实验：实际是抖动算法的单元测试。
8. 把 CrossLink 排在第二不适合文字阅读：它强在图片处理，而且闭源。

---

## 10. 实验记录（按时间）

### 10.1 快速灰阶首测（15:31，`pico-serial-20261119-1531.log`）
- 普通 53 相：10 次，651–669 ms。GRAY8 30 相（跳过 1 相）：9 次，374–391 ms。
- 按帧时间推算，每次推屏有 60–70 ms 固定开销。
- 第 10 页左右触发周期清理：GC16 608 ms，加页码 DU 59 ms。

### 10.2 快速灰阶 30+4（15:41，`…-1541.log`）
- 34 相：11 次，432–438 ms。速读黑白：10 次，304–310 ms。
- 用户实屏判断：30 相不擦白时残影明显，30+4 可以接受。
- 当时两次 `paint` 514/532 ms 而 `glyphs=0`：后来查明是第 8 页的进度保存（`paint` 含保存时间）。

### 10.3 延后保存 + 快翻 DU（16:22，`…-1622-retest.log`）
- 慢翻 12 次 `save=0ms`，停顿消失。快翻 DU 19 次，129–134 ms，每次另有页码 DU 59 ms。
- 周期清理在快翻中插进来 2 次，每次约 600 ms。
- 往回翻没命中缓存，排版 74–81 ms。

### 10.4 推迟清理/页码 + 保留上一页（16:45，`…-1645-keep.log`）
- 5↔6 来回快翻 30 多次：全部命中缓存，排版 16–19 ms，DU 118–120 ms。
- 定稿带清理：577 / 587 ms。
- 跨章那一页仍有 `save=495/574ms`：跨章时的保存当时还在翻页路径上。

### 10.5 跨章保存延后（16:51，`…-1651-chsave.log`）
- 跨章 `save=0ms`。跨进 52 页的第 4 章：`load_chapter` 567 ms + 排版 180 ms。
- 第 4 章第 2 页：`turn=0`、没有预排，382 ms，原因见 §10.6（该页带插图）。
- 发现快翻中欠下的清理没被后面的普通清理页取消，停手后多做了一次 GC16（510 ms）。已修复，§10.6 实测通过。

### 10.6 合并上游 #98 后补测（17:18，`…-1718-merge98.log`，fw `0bcb195e…`）
- **取消修复生效**：快翻后的定稿带清理时只做一次 GC16（578 ms）加页码 59 ms；第 3 章第 1 页慢翻本身触发清理（601 ms）后，之前待做的定稿被取消，没有重复刷新。
- **#98 刷白**：速读黑白每页 363–374 ms，合并前是 304–310 ms，多出约 60 ms，是状态栏和进度条两次 4 相刷白。普通、快翻和定稿都没有额外刷白。
- **跨章后几页慢的原因已查明**（§6 原第 2 项）：第 4 章第 2、4、5、7 页带插图。
  - 这几页 `full=1` 的推屏走正文区 GL16，排版加解码 290–410 ms。
  - 紧跟其后的纯文字页因上一页不是纯文字页，也是 `turn=0`、不预排（105–138 ms），推屏改走正文区差分 GL16，另有页码 DU 59 ms。
  - 这是现有插图处理的设计，不是故障。
- **往回连续翻**（第 3 章 9→4 页）：每页 `cached=0`，排版 65–159 ms，因为只预排下一页，上一页只在刚往前翻过时才有。
- 快翻 DU 107–134 ms；非全屏时正文区较小（684×872），推屏 107–119 ms。延后保存 493–583 ms，都在空闲时。

### 10.7 进度保存耗时拆分与原地覆盖（17:27 `…-1727-savetiming.log`、17:32 `…-1732-inplace.log`）
- 拆分（8 次，每次 80 字节）：NVS 序号提交 1 ms，读旧记录 4 ms，`fopen("wb")` 206–278 ms，写入 0 ms，fsync 273–345 ms，关闭和回读 2 ms。
- 推测：`wb` 先截断（改 FAT 表和目录），fsync 再分配簇、写数据、再改 FAT 表和目录，每次都整块重写 4 KB 扇区。
- 改为长度相同时 `fopen("r+b")` 原地覆盖（`main/book/book_progress_files.inc`），长度不同或文件不存在时仍用 `wb`：
  - 5 次实测：打开 2 ms，fsync 136–137 ms，一次保存 152–154 ms，约快 3.3 倍。
  - 断电安全性不变：仍只写不在用的那个文件，回读校验失败会删掉它，另一个文件仍是上一次的有效记录。
- 为腾代码空间，删掉了 `progress save prep/flush/ticket` 日志；`dw` 那行计时日志还在（剩余 352 B）。
