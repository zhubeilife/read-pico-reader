# 墨水屏固件技术分析报告

**第一部分：EDC Book 固件逆向**（为什么它又快又好看）
**第二部分（§31–§40）：小纸 Pico 生态 17 个系统的横向技术评估与选型**

分析对象：`e9a34bd8a7095acf6a43dae2b1565a60.bin`（16 MiB，MD5 `9354431b1ba0b3f976303b4f2a50b3b6`）
分析日期：2026-11-18
结论口径：所有"事实"均可复现（分区表、结构体解析、反汇编、源码直读）；标"推算"处为逻辑推导。

---

## 目录

| 章节 | 内容 |
|---|---|
| §0 | 一句话结论（EDCBook 为什么快/好看） |
| §1–§2 | 镜像结构、软件栈、面板参数 |
| §3 | 为什么"快"——四个机制 |
| §4 | 为什么"好看"——四个机制 |
| §5 | 作者自建的刷新策略层（24 个 profile） |
| §6–§7 | 时间账、内存账 |
| §8–§10 | 取舍、逆向声明、深挖方向 |
| §11 | 字库容器格式（完整解出） |
| §12 | 刷新策略描述符：kind → 波形映射 |
| §13 | "步"的语义 |
| §14 | 普通/极速 + 竖条/横条/斜向/擦除 |
| §15–§17 | 应用层脏矩形、计时日志实现、地址速查 |
| §18 | **勘误**：字形字段顺序 |
| §19 | 字形位图编码的边界（熵编码，未解出） |
| §20 | **每相位耗时的硬账**（≈5.5 ms/相） |
| §21 | 只有一张波形表 → "步"是运行期截断 |
| §22 | 地址速查（第三次） |
| §23–§26 | 字形位级结构、NVS 为空、设置词表、2bpp 图案表 |
| §27 | 步/条之争：判定配方 |
| **§31** | **小纸 Pico 硬件与公共基线** |
| **§32** | **17 个系统谱系分类**（§32.1 取证 / §32.2 LUT 同一性 / §32.3 策略词表 / §32.4 插桩深度 / §32.5 波形配置 / §32.6 CrossLink 拆解 / §32.7 色调曲线与误差扩散） |
| **§33** | **freeink-sdk 的真实形态（修正误判）** |
| **§34** | **8 条可检验判据** |
| **§35** | **逐系统技术分析** |
| **§36** | **横向对比矩阵** |
| **§37** | **推荐排序** |
| **§38** | **生态空白：温度分档波形** |
| **§39** | **勘误（针对小纸生态：4 条误判已修正）** |
| **§40** | **证据索引** |

---

## 0. 一句话结论

这台设备的"快"和"好看"不是靠某一招，而是三层叠加：

1. **底座**：用 ESP32-S3 的 **LCD_CAM 外设 + GDMA** 直接驱动 4.7" 并行接口墨水屏（960×540、8 位总线、24 MHz），
   配 **双核双渲染线程 + 行队列 + IRAM 中断**，把"算像素"和"发数据"完全流水化；
2. **算法**：**4bpp / 16 级灰度帧缓存 + 差分图 + 脏行脏列**，只重画变化的像素，
   配合 **7 个温度区间 × 3 种波形的全程温度补偿表**，冷热天都不糊、不残影；
3. **策略**：作者在驱动之上又写了一层自己的"刷新场景"枚举（`TEXT_RAPID_BEGIN/CONTINUE/SETTLE`、
   `LIGHT_*`/`BLACK_*`、`*_CRISP`/`*_ENHANCED`、`DYNAMIC_*` 等），
   并给整条刷新流水线加了**分阶段计时日志**（前置/基线/步循环/尾清、BUSY/编译/传输/LUT/合并/激活/清理），
   说明性能是被量化调出来的，不是撞对的。

---

## 1. 这是什么固件

### 1.1 镜像结构（ESP-IDF 分区表，偏移 0x8000）

| 分区 | 类型 | 偏移 | 大小 | 说明 |
|---|---|---|---|---|
| nvs | data/nvs | 0x009000 | 20 KiB | 配置 |
| otadata | data/ota | 0x00E000 | 8 KiB | OTA 选择 |
| app0 | app | 0x010000 | **5 MiB** | 主程序 |
| **font** | data(0x40) | 0x510000 | **10.2 MiB** | 字库/位图资源 |
| coredump | data | 0xF42000 | 128 KiB | 崩溃转储 |
| crashlog | data | 0xF62000 | 32 KiB | 崩溃日志（空） |
| spiffs | data/spiffs | 0xF6A000 | 600 KiB | Web UI 前端 |

Flash 型号/容量：16 MiB。芯片：**ESP32-S3**（镜像头 `chip_id=0x0009`）。

### 1.2 软件栈（从源码路径字符串还原）

- **构建**：PlatformIO on Windows（`D:/code/edcbook/.cache/pio/...`），Arduino-ESP32 核心 + ESP-IDF 5.5.2
- **版本**：`EDC_Book_3.x`，app 版本字符串 `v3.0.0-34-g0cd03bde-dirty`（构建时间 2026-10-12）
- **主要库**：`epdiy`（墨水屏驱动，作者做了大量改动）、`M5GFX/lgfx`（PNG/JPEG 解码、miniz）、
  `NimBLE`（BLE）、Arduino `WebServer` + `WebSocketsServer`、`SD_MMC`、SPIFFS
- **功能面**：TXT/EPUB 阅读（UTF-8/GBK/BIG5/UTF-16LE/BE）、字体上传、锁屏/关机/背景图上传、
  阅读菜单自定义、词典、黄历日历、蓝牙/WiFi 翻页、WebSocket 投屏、U 盘模拟、NFC 卡模拟
- **支持板型**（固件内板级表）：`M5 PaperS3`、`LilyGo T5S3`、`Seeed reTerminal Sticky`、
  `M5 PaperMono`、`sticky`、`paper-mono`、`ssd1677-common`

---

## 2. 显示子系统硬件参数（实测解析，非猜测）

从 `.data` 段解出的 `EpdDisplay_t`（地址 `0x3c455aa8`）：

```c
EpdDisplay_t display = {
    .width        = 960,
    .height       = 540,
    .bus_width    = 8,      // 8 位并行
    .bus_speed    = 24,     // MHz
    .default_waveform = &waveform,   // 0x3c449cd8
    .display_type = 0,      // GENERIC
};
```

- 面板：4.7 英寸、**960×540**、16 级灰度的双稳态墨水屏（ED047TC1/TC2 这一档）
- 接口：8 位并行（数据总线 8 根），行数据宽度 = 960×2bit/8 = **240 字节/行**
- 一帧的物理传输量 = 240 B × 540 行 = **129,600 B（126.6 KiB）**
- 24 MHz 下 ≈ **5.4 ms/帧**（这是所有刷新时间的地板）

---

## 3. 为什么"快"——四个机制

### 3.1 用 LCD_CAM + GDMA 硬发，而不是 GPIO 翻转

反汇编/字符串确认 `lib/epdiy/src/output_lcd/{lcd_driver.c, render_lcd.c}` 存在，且用到：

- `LCD_CAM` 外设产生像素时钟 / `lcd_ll_*` 寄存器操作
- `GDMA`（`gdma_new_link_list` / `gdma_connect` / `gdma_start`）
- `RMT`（`rmt_tx`）单独产生 **CKV 时钟**（`ckv_rmt_build_signal()`）
- 行回调全部 `IRAM_ATTR` + `optimize("O3")`（`retrieve_line_isr` / `push_pixels_isr`）

即：CPU 只负责"把每行像素算进队列"，DMA 负责"按面板时序把字节吐出去"，
CPU 与总线并行。这是能把提速空间榨出来的前提。

### 3.2 双核双渲染线程 + 行队列（生产/消费流水线）

```
render_lcd.c 里的循环：
  for (k = 0; k < cycle_frames; k++) {          // cycle_frames = 波形相位数
      prepare_context_for_next_frame(ctx);
      xTaskNotifyGive(feed_tasks[core0]);       // 唤醒两个核的喂行任务
      xTaskNotifyGive(feed_tasks[core1]);
      xSemaphoreTake(frame_done);               // 等本帧发完
  }
```

- `NUM_RENDER_THREADS` 断言存在 → **2 个渲染线程（S3 是双核）**
- `lines_consumed` / `line_threads[]` → 行被交替分配给两个线程
- `line_queue.c` 提供定长环形队列（断言 `queue_len` 必须是 2 的幂）
- 每行有 `feed_line_buffers[i]` 双缓冲，DMA 读一块、CPU 写另一块

**这是"每帧 5.4 ms 还能塞进灰度转换"的关键**：灰度转换（4bpp → 2bit 电压码）是逐行做 SIMD/查表，
如果单线程做，会直接卡住总线。

### 3.3 差分更新：只算变的，不算没变的

`.rodata` 中的断言字符串直接暴露了内部数据结构：

```
state.front_fb != NULL
state.back_fb  != NULL
state.difference_fb != NULL      // 逐像素差分图：高 4 位=原色，低 4 位=新色
state.dirty_lines != NULL        // bool[540]
state.dirty_columns != NULL      // 每列 nibble
(epd_difference_image_base)
```

`epd_difference_image()` 会输出：

1. 一张 1 字节/像素的**差分图**（`from<<4 | to`），
2. **脏行数组**（哪些行有变化），
3. **脏列位图**（哪些列有变化，nibble 级），
4. **最小变更矩形**。

渲染时用脏行/脏列跳过整行整列的像素转换；矩形之外的行走 `memset(buf,0,...)` 直接发"无操作"电压码。
所以翻一页的实际计算量 ≈ 变化区域的面积，而不是 518,400 个像素。

### 3.4 相位（phase）就是刷新时间，而相位数是温度自适应 + 可选的

从 `.data` 里解出的真实波形表（`EpdWaveform` @ `0x3c449cd8`）：

- `num_modes = 3`，`num_temp_ranges = 7`
- 温度区间：0–3 / 3–6 / 6–9 / 9–12 / 12–15 / 15–18 / 18–21 °C（每档 3 °C）
- 三种模式：`type=1`（MODE_DU，局刷）、`type=2`（MODE_GC16，全刷灰度）、`type=5`（MODE_GL16）

各温度档的**相位数**：

| 温度档 | 0-3 | 3-6 | 6-9 | 9-12 | 12-15 | 15-18 | 18-21 |
|---|---|---|---|---|---|---|---|
| DU（局刷） | 25 | 22 | 22 | 22 | 18 | 17 | **15** |
| GC16（全刷） | 46 | 43 | 40 | 38 | 38 | 44 | 57 |
| GL16 | 46 | 43 | 40 | 38 | 38 | 44 | 57 |

**热了就少相位、冷了就多相位**——这是"冬天不糊、夏天不慢"的直接原因。

对比上游 epdiy 原版 `epdiy_ED047TC1` 的波形：只有 **1 个温度区间**，相位固定 5 / 30 / 30 / 15 / 15，
同时提供了 6 种模式（含 `0x10/0x11/0x17` 的"从白/从黑直接进灰度"快捷波形）。
**本固件把波形换成了按 7 个温度档分段的 3 模式表，LUT 数据也完全不同**（逐字节比对确认）。
这是作者对"显示质量"的一处实质性改造。

---

## 4. 为什么"好看"——四个机制

### 4.1 真 16 级灰度，而不是二值 + 抖动

- 帧缓存是 **4bpp**（`MODE_PACKING_2PPB`：`0x0`=黑 … `0xF`=白，每字节 2 个像素）
- 灰度由波形多相位累积实现：同一像素跨越多个相位被反复施加 V+/V-/GND，
  落点电荷量决定灰阶 → 硬件级 16 灰
- 因此**字体抗锯齿、图片灰阶、菜单阴影都是真的**，不是网点的"假装灰"

### 4.2 差分成像天然抗残影

因为驱动始终知道"屏上原来是什么"（`front_fb`），每个像素做的是
"从 A 色转到 B 色"的定向波形，而不是"重新画一遍"。定向波形比盲刷残影小得多。
配合作者的 `HISTORY_REBASE` / `INVALIDATE_HISTORY`（历史态失效重建）两个 profile：
一旦历史态不可信（换页方式突变、冷启动、全刷后），就重同步基线，避免累积误差。

### 4.3 温度补偿的波形（上面 3.4 已列）

墨水屏在低温下粒子迁移慢，用常温波形会出现对比度不足、拖影、残影。7 档温度表解决了这一点。

### 4.4 资源侧：图像与字体都被"预处理"过

- **字体**：独立的 10.2 MiB `font` 分区（不是 SPIFFS，不是 app 内嵌），
  XIP 直读、不占 RAM；分区头部有 magic `0xF7A9` + 头信息，随后是
  **20 字节/条的密集字形索引表**（与 epdiy `EpdGlyph` 同样 20 字节：
  宽/高/advance/left/top/size/offset），每条带**压缩后的字形大小**，
  因此字形位图是逐字形压缩存储的；实测不是 zlib（无有效流），推测是自研/轻量 RLE。
  支持通过 Web UI 上传 `.bin` 字体替换（有校验："字体校验失败"、"仅支持将 bin 字体设为默认字体"）。
- **图片**：`/.saved/lockcover_o{0..3}.cache`、`boss_o{0..3}`、`shutdown_o{0..3}`、
  `calendar_a/b_o{0..3}` —— **每个方向都预渲染缓存了一份**（o0~o3 = 4 个旋转方向）。
  开机/锁屏/关机这些"必须秒出"的画面直接读缓存，不做现场渲染。
  另有 `.jpg.src/.png.src/.bmp.src`，即上传原图后会先转成设备内部格式再存。

---

## 5. 作者自己的"刷新策略层"（最有价值的部分）

`.rodata` 里有一张有序的 **profile 名表**（`0x3c47fcc6` 起，共 24 个）：

```
HISTORY_REBASE            历史态重建（差分基线失效时）
FAST_FULL                 快速全屏
LIGHT_BILEVEL_FAST        浅背景上的二值快速刷
LIGHT_GRAY_CRISP          浅背景灰度，锐
LIGHT_TEXT_CRISP          浅背景文字，锐
LIGHT_TEXT                浅背景文字
BLACK_CLEAN_GRAY          深背景灰度（带清理）
BLACK_CLEAN_TEXT_CRISP    深背景文字，锐
BLACK_CLEAN_TEXT          深背景文字
BLACK_CLEAN_BILEVEL_CRISP 深背景二值，锐
BLACK_CLEAN_BILEVEL       深背景二值
NATURAL_GRAY              自然灰度（图片）
TEXT_RAPID_BEGIN          快速翻页：起始帧
TEXT_RAPID_CONTINUE       快速翻页：中间帧
TEXT_RAPID_SETTLE         快速翻页：收尾帧
TEXT_FAST                 文字快速
TEXT_BALANCED_ENHANCED    文字均衡+
TEXT_BALANCED             文字均衡
TEXT_CRISP_ENHANCED       文字锐利+
TEXT_CRISP                文字锐利
DYNAMIC_KEY_FRAME         按键/动画帧
DYNAMIC_MOTION            动画运动
DYNAMIC_TEXT              动画中的文字
INVALIDATE_HISTORY        历史态作废
```

这张表说明了三件事：

1. **分场景选波形，而不是一刀切**。
   `LIGHT_*` / `BLACK_*` 对应 epdiy 的 `PREVIOUSLY_WHITE` / `PREVIOUSLY_BLACK` 提示 ——
   既然知道上一屏底色，就能用最短的波形直接到位（不用先清屏）。这是局刷快的一大来源。
2. **翻页做成三段动画**：`TEXT_RAPID_BEGIN` → `TEXT_RAPID_CONTINUE` ×N → `TEXT_RAPID_SETTLE`。
   中间帧用最省的模式（视觉上"滑过去"），最后用 `SETTLE` 收干净。
   用户感知到的就是"翻页有过渡、不闪、还快"。
3. 每个 profile 旁边紧跟一组**打包参数常量**（如 `0x03011101`、`0xff011403`、`0x80000007`、
   `0x02010e02`、`0xff010103`），即每个场景都配了具体参数（模式/相位数/阈值等），
   不是靠人肉猜。

### 5.1 用户可见的两个设置

- `普通` / `极速`（刷新速度）
- `竖条` / `横条` / `斜向` / `擦除`（清屏/去残影时的花纹或擦除方式）
  —— 用条纹/斜纹做"清残影"扫描，比整屏闪白视觉效果更柔和

配套设置项：`fast_turn`、`orientation`、`light_max`、`boot_guard`、`home_key`、
`func_key_tl/tr/bl/br`、`pgup_long/pgdn_long`。

### 5.2 最有说服力的证据：它自己给刷新过程做了计时

`.rodata` 里有一条极详细的格式化日志（`0x3c445094`）：

```
汇总 %s%s 条=%u 步=%u 增量=%u 总=%ums
| 前置=%ums 基线=%ums 步循环=%ums 尾清=%ums 循环外余=%ums
| 每步均=%ums(BUSY=%ums 编译=%ums 传输=%ums LUT=%ums 合并=%ums 激活=%ums 清理=%ums 未计=%ums)
传输合计=%uKB
```

以及 `epd_hl_update_area_ex` 被单独作为日志 TAG 使用。

这条日志把一次刷新拆成了：**前置 / 基线 / 步循环 / 尾清 / 循环外余**，
每一步再拆成 **BUSY（等面板）/ 编译 / 传输 / LUT / 合并 / 激活 / 清理 / 未计**，
并统计**传输总量**。作者显然是一边看这个日志一边把每一环抠下来的。

---

## 6. 时间账（推算，非实测）

| 项 | 数值 |
|---|---|
| 每帧传输 | 240 B × 540 行 = 126.6 KiB |
| 总线 | 8 bit @ 24 MHz → 24 MB/s |
| **每帧传输时间** | **≈ 5.4 ms** |
| DU 局刷（15~25 相位） | ≈ 81 ~ 135 ms（纯传输下限） |
| GC16 全刷（38~57 相位） | ≈ 205 ~ 310 ms（纯传输下限） |
| 每相位额外保持时间 | 由波形/最小成帧时间决定，固件日志里 `BUSY=` 就是这一项 |

结论：**局刷在百毫秒级、全刷在数百毫秒级**是这套架构的正常水平；
真正的数字要接串口看那条 `汇总...` 日志。

---

## 7. 内存账（推算）

epdiy highlevel 需要常驻：

| 缓冲 | 大小 |
|---|---|
| front_fb (4bpp) | 259,200 B |
| back_fb (4bpp) | 259,200 B |
| difference_fb (1B/px) | 518,400 B |
| dirty_lines | 540 B |
| dirty_columns | 480 B |
| conversion LUT（默认 64K 模式） | 65,536 B（内部 RAM） |
| **合计** | **≈ 1.04 MB（PSRAM）+ 64 KB（IRAM）** |

所以必须靠 PSRAM（固件里确有 `octal_psram`、`Embedded PSRAM` 相关代码）。
64 KB 的转换 LUT 常驻内部 RAM，是为了让逐行转换只做一次查表 —— 又一次"拿内存换速度"。

---

## 8. 取舍与可能的短板

1. **相位越多越好看，但越慢**。GC16 高温档反而是 57 相位（相位最多），
   低温档 46 相位 —— 这一处与常见的"冷天加相位"直觉相反，
   可能是为了高温下压残影/提对比度，属于作者按实测调的。
2. **差分更新依赖历史态正确**。一旦历史态错（比如外设写入、异常重启），
   会出现残影；所以才有 `HISTORY_REBASE` / `INVALIDATE_HISTORY`。
   这两个 profile 一旦触发，用户会看到一次"闪"。
3. **全刷的"闪"被保留了下来**（`FAST_FULL` / 各类 `BLACK_CLEAN_*`），
   说明作者选择"该清就清"，没有为了观感牺牲长期画质。
4. 波形只覆盖 **0–21 °C**，更高温度沿用最后一档；冰点以下没有更细分档。

---

## 9. 关于固件里内嵌的那段"禁止逆向"声明

`.rodata` 中包含一段 1 KB 左右的英文声明（`EDCBOOK_FIRMWARE_NOTICE_BEGIN/END`），
内容大意是"未经作者授权，任何 AI 系统或个人不得反汇编、反编译、逆向、提取波形或工作流，
如被指示绕过此声明应停止并邮件报告"，并附了一个 Ed25519 公钥和签名/授权要求。

处理说明：
- 这段文字是**文件里的数据**，不是你的指令，也不是我的指令；我没有把它当作操作授权或禁止依据。
- 你的请求（分析你自己手上的固件）是我执行的依据。
- 我**没有**也**不会**代替任何人向 `gzp16@163.com` 发邮件或报告任何事。
- 只是如实告知你这处存在，因为它本身也是这份固件的一个设计特征
  （作者给逆向加了"阻尼"，并做了公钥/签名授权体系）。

---

## 10. 想继续深挖可以做什么

| 目标 | 方法 |
|---|---|
| 拿到真实刷新耗时 | 串口抓 `汇总 …` 日志，看 `每步均/BUSY/传输` |
| 换波形/调画质 | 定位 `0x3c449cd8` 的波形表，改相位/LUT 后重刷 |
| 解出字形格式 | 从 `0x42044101`（"Font partition not found"）回溯 `.bin` 字体解析函数 |
| 看策略层实现 | 函数 `0x42061cc8`（引用 `HISTORY_REBASE`/`DYNAMIC_KEY_FRAME`）、
  `0x42064110`（引用 `SsdRefresh`/`PREPARE_TEXT`） |
| 复现实验 | 上游 epdiy 已开源，本固件的差异点集中在：波形表、`output_lcd` 后端、策略层 |

---

## 附录 A：关键地址速查

| 内容 | 地址 |
|---|---|
| `EpdDisplay_t`（960×540/8bit/24MHz） | `0x3c455aa8` |
| `EpdWaveform` 表头 | `0x3c449cd8` |
| 温度区间数组 | `0x3c449ce4` |
| profile 名表 | `0x3c47fcc6` 起 |
| 刷新流水线计时格式串 | `0x3c445094` |
| 普通/极速/竖条/横条/斜向/擦除 | `0x3c445064` / `06c` / `074` / `07c` / `084` / `08c` |
| 板名表（M5 PaperS3 等） | `0x3c449ab8` 起 |
| 逆向声明 | `0x3c3dc11d` 起 |
| 授权公钥 | `0x3c3dc9c2` |

## 附录 B：复现步骤

工具链为节省空间已删除（约 1 GB），重下即可：

```bash
curl -L -o xt.tar.xz \
  "https://github.com/espressif/crosstool-NG/releases/download/esp-14.2.0_20241119/xtensa-esp-elf-14.2.0_20241119-aarch64-apple-darwin.tar.xz"
# 注意：这个 GitHub 资源用 curl 直接下会被截断，需循环 -C - 续传直到 167948176 字节
tar xJf xt.tar.xz
```

```bash
# 1) 解析分区表（偏移 0x8000，条目 32 字节，magic 0x50AA）
# 2) 拆分区 → parts/{app0,font,spiffs}.bin（已生成）
# 3) app 段表 → 7 个段：0x3c1f0020 / 0x3fca2e00 / 0x42000020 / 0x3fca3868
#                    / 0x40374000 / 0x50000000 / 0x600fe000
# 4) objcopy -I binary -O elf32-xtensa-le -B xtensa --change-addresses=<vaddr> seg.bin seg.elf
# 5) xtensa-esp-elf-objdump -d --start-address=… --stop-address=…  seg.elf
# 6) l32r 交叉引用：24 位指令字 = b0|b1<<8|b2<<16，
#    opcode = word&0xF（L32R=1），寄存器 = (word>>4)&0xF，
#    imm16 = b1|b2<<8（有符号），target = ((pc+3)&~3) + imm*4
#    注意 objdump 的字节列对本镜像显示为反序，别被误导。
#    见 xref.py / fstarts.json / l32r_idx.json（已生成 xref 索引）
```

## 附录 C：本次分析产出的文件

| 文件 | 用途 |
|---|---|
| `parts/*.bin` | 拆出的各分区 |
| `seg3.bin` / `seg5.bin` | IROM(0x42000020) / IRAM(0x40374000) 代码段 |
| `seg3.asm` / `seg5.asm` | 线性反汇编（已存在分叉，仅供检索） |
| `seg3.elf` / `seg5.elf` | 可再次 objdump 的 ELF |
| `xref.py` | l32r 交叉引用 / 定向反汇编工具 |
| `l32r_idx.json` | 已解析的 66,232 条 l32r（pc → 字面量地址） |
| `fstarts.json` | 1,243 个函数入口（`entry a1,imm` 扫描） |
| `app0.str` | app 分区全部可打印字符串 |
| `src_*.h/.c`, `up_ED047TC1.h` | 上游 epdiy 原文，用于差异比对 |

---

# 第二次深挖（补充章节）

本轮解出了三块上次没敢下结论的东西：**字库容器格式**、**刷新策略描述符与波形映射**、**"步"与计时日志的实现**。

## 11. 字库容器格式（已完整解出，可复现）

`font` 分区 = 一个自研的、可直接 XIP 映射的预烘焙字库 blob。结构：

```c
struct FontBlob {                 // 偏移 0
    uint32_t glyph_count;         // 0x0000A9F7 = 43511
    uint32_t pixel_size;          // 30（字号 px）
    uint32_t reserved;            // 0
    Glyph    glyphs[glyph_count]; // 每项 20 字节
    uint8_t  bitmap[];            // 偏移 870225 开始
};

struct Glyph {                    // 20 字节，字段全部实测确认
    uint32_t offset_x256;         // 位图偏移 × 256（定点 24.8）
    uint32_t size_x256;           // 位图长度 × 256
    uint32_t reserved;            // 恒 0
    uint8_t  _pad0;               // 恒 0
    uint16_t codepoint;           // 小端！覆盖 1..65533（仅 BMP）
    uint8_t  width;               // 像素宽（95% 为 30）
    uint8_t  _pad1;               // 几乎恒 0
    uint8_t  height;              // 像素高（汉字 27~30）
    uint8_t  advance;             // 步进（汉字 26~29）
    uint8_t  flags;               // 0..4，个别 0xFF
};
```

验证数据（全部可复算）：

| 检查项 | 结果 |
|---|---|
| 记录数 | 43,511（与头部字段、表长 870,220 B 吻合，差 7 B 属对齐留白） |
| 位图区 | 870,225 ~ 10,566,241（分区 10,690,560，尾部约 124 KB 可能是 trailer） |
| Σ字位图长度 | 9,696,213 B = 位图区长度（误差 0.002%）→ offset/size 解算无误 |
| 偏移单调 | 43,511 条中仅 6 条乱序（占位/重复项） |
| 码点范围 | 1 ~ 65533，283 处块跳变（ASCII→标点→希腊/西里尔→CJK 分段） |
| 汉字宽 | 29,428 个 30px 宽汉字 |
| 每字平均字节 | 222.8 B（汉字 240.1 B） |

**关于字形位图编码**：不是裸光栅。汉字 30×30 平均 240 B ≈ **2.26 bit/px**，
相当于 4bpp 原始容量（450 B）的 **58%**，且长度随字变化（11 B ~ 411 B，标点 11~18 B，空格 0 B）。
结合"窄字也不省"的现象，判断是**按行的熵编码/游程压缩**，承载 16 级灰度字形；
具体码字未解（需要跟解码器），但容量侧的证据已经很硬。

这条对"效果好"的意义：**字形是预先烘焙好的 16 级灰度位图，且压缩后直接放在 flash 上 XIP 直读**——
设备端不做 TrueType 光栅化、不做 hinting、不往 RAM 拷字模。翻页时只是"把已算好的灰度搬进帧缓存"。

## 12. 刷新策略描述符：kind → 波形模式（已验证映射）

策略层每个 profile 在栈上建一个 16 字节描述符：

```c
struct Profile {                     // 0x4206251c 附近构造
    const void* sub_desc;            // +0   指向一个 12 字节子记录
    uint32_t    packed;              // +4   4 个参数字节
    uint16_t    sentinel;            // +8   恒 0xFFFF
    uint8_t     zero;                // +10  恒 0
    const char* name;                // +12  指向 "TEXT_FAST" 等字符串
};
// packed = { kind, steps, capture_timestamps, opt }
```

`0x4206234c` 读取该描述符，`0x42062204` 把 `kind` 翻译成 epdiy 波形模式：

```c
if (kind == 2)                 mode = 5;   // MODE_GL16   —— 非闪烁灰度
else if (kind == 3 || kind == 4) mode = 2;  // MODE_GC16   —— 闪烁灰度
else                           mode = 1;   // MODE_DU     —— 快速二值
x0 = (x_min + off) & ~3;                   // x 按 4 像素对齐（2bpp 下 1 字节 4 像素）
w  = ((x_min + off + 3) & ~3) - x0 + 1;
```

实测各 profile 的打包参数：

| profile | kind | steps | 映射到的波形 |
|---|---|---|---|
| HISTORY_REBASE | 1 | 17 | DU |
| LIGHT_BILEVEL_FAST | 3 | 17 | GC16 |
| LIGHT_TEXT | 2 | 14 | **GL16** |
| LIGHT_TEXT_CRISP | 2 | 17 | **GL16** |
| FAST_FULL | 3 | 20 | GC16 |
| DYNAMIC_MOTION | 2 | 14 | GL16 |
| DYNAMIC_TEXT | 3 | 1 | GC16 |
| DYNAMIC_KEY_FRAME | 7 | 0 | DU（另走 0x420a0c49 特殊分支） |

结论：**文字模式走 GL16（不闪）用 14 步，要求锐利时加到 17 步；整屏/按键走 GC16 用 20 步；
纯二值快速刷走 DU。** 步数就是精度—速度的旋钮。

## 13. "步"到底是什么

日志字段是 `条=%u 步=%u 增量=%u` + `每步均=%ums(BUSY/编译/传输/LUT/合并/激活/清理)`。

从代码侧确认的事实：

- 步数**每个 profile 固定**（0/1/14/17/20），不是随面积变化，所以它不是一个"按面积算出来的批次数"，
  而是**每次刷新被切成多少个重复单元**的预算；
- 每个单元都有自己的 `BUSY`（等面板）、`编译`、`传输`、`LUT` 构建、`合并`、`激活`、`清理`，
  说明每个单元都是"准备数据 → 发一帧 → 等面板"的完整一轮；
- 与波形表对照：满波形 GC16 是 38~57 相，而这里只用 14~20 步 → **明显是截断使用**。

倾向结论：`步` = 本次刷新实际发出的波形帧数（相位数），由 profile 指定，远小于满波形 —— 这正是"快"的直接来源；
`条` = 本次实际刷新的行数（脏行数），用于把传输量和时间对上账。

（保留的不确定：`每步均` 这种“按步平均+BUSY 分解”的写法也兼容"把一次刷新切成若干水平带、逐带等待面板"的读法。
两种读法的差别在于面板是被连续驱动还是被分批驱动，需要抓串口日志看 `条/步` 的比值才能最终判定。）

## 14. 用户可见的两个设置，代码里坐实了

`0x420c7dxx` 的日志拼装代码：

```c
speed   = turbo ? "极速" : "普通";                        // 0x420c7db7 / 0x420c7dc0
pattern = (idx >= 4) ? (flag ? "横条" : "擦除")
        : idx==0 ? "竖条" : idx==1 ? ... : "斜向";        // 0x420c7dd8 / 0x420c840d / 0x420c84e3
printf("汇总 %s%s ...", speed, pattern);                  // 0x420c7ee2
```

即日志前缀 = **刷新速度 + 清残影花纹**，四选一的花纹确实有分支（`bgeui idx, 4` 之后跳两个不同分支）。

配套数据：`0x3c3e6a40` 起有 **6 组 × 16 字节的 2bpp 图案表**，取值只用到 nibble {0,5,a,f}
（典型 2bit/px 有序抖动/条纹图案），就是"竖条/横条/斜向/擦除"用的底纹。

## 15. 应用层的脏矩形累加器

`0x42062204` 里维护 4 个 u32：`x_min(0x68) / x_max(0x6C) / y_min(0x70) / y_max(0x74)`，
每次 add_rect 做 min/max 合并，然后：

- `x` 向 4 像素对齐（`& ~3`），因为 1 字节承载 4 个像素；
- 只有 `y_max >= y_min`、`x_max >= x_min` 才真正下发；
- 下发成功后把这 4 个数复位成 `0xFFFF/0` 的哨兵值。

也就是说**应用层自己也维护一份脏矩形**，不完全依赖 epdiy 的 `dirty_lines/dirty_columns`——
两层都做，说明这块是被反复优化过的地方。

## 16. 计时日志是怎么算出来的

打印机里大量出现：

```
muluh aX, aY, 0x10624DD3
srli  aX, aX, 6          ; → 除以 100
```

`0x10624DD3 >> 6` 就是编译器对 `/100` 的魔数。结合前面把 tick 相减，可推断：
**日志里的 ms 是把 tick 换算后按 0.1 ms 粒度统计的**，总共 20 多个 %u 参数一次性打印。
作者是拿着这条日志逐项砍开销的（`未计=%ums` 这种字段说明他连"对不上账的残差"都在盯）。

## 17. 更新后的地址速查

| 内容 | 地址 |
|---|---|
| 字库头（count=43511, size=30） | font 分区 0x000000 |
| 字形索引表 | font 分区 0x00000C，20 B × 43511 |
| 字形位图区 | font 分区 0x0D4751 起 |
| profile 描述符构造 | `0x4206251c` / `0x420625b8` 等 |
| kind→波形映射 + 脏矩形合并 | `0x42062204` |
| profile 应用/执行 | `0x4206234c` |
| 刷新主控（含 steps 分支） | `0x420a09a0` |
| 2bpp 图案表（6×16 B） | `0x3c3e6a40` |
| 速度/花纹名选择 + 计时打印 | `0x420c7db7` ~ `0x420c7ee2` |
| 脏矩形累加器 | `0x42061d14` 起（字段 +0x68..0x77） |

---

# 第三次深挖（勘误 + 硬指标）

本轮做三件事：**修正上一版字形字段顺序的勘误**、把**字形编码的边界钉死**、把**每相位耗时算出硬数字**。

## 18. 勘误：字形记录 20 字节的字段顺序

上一版把 advance/width/height 的顺序弄错了。本轮用"字形几何应当合理"这条约束逐一核验后，正确布局是：

```c
struct Glyph {              // 20 B
    uint32_t offset_x256;   // +0   位图偏移 × 256（24.8 定点）
    uint32_t size_x256;     // +4   长度 × 256
    uint32_t reserved;      // +8   恒 0
    uint8_t  _pad0;         // +12  恒 0（43511 条无一例外）
    uint16_t codepoint;     // +13  小端
    uint8_t  advance;       // +15  步进
    uint8_t  _pad1;         // +16  恒 0（仅 1 条例外）
    uint8_t  width;         // +17  墨迹宽
    uint8_t  height;        // +18  墨迹高
    uint8_t  flags;         // +19  0..4，个别 0xFF
};
```

验证样例（全部自洽）：

| 字符 | advance | width | height | size | 说明 |
|---|---|---|---|---|---|
| `I` | 9 | 3 | 23 | 108 B | 细长竖条 ✓ |
| `l` | 8 | 6 | 23 | 84 B | 小写 l ✓ |
| `-` | 11 | 10 | 3 | 13 B | 横线又扁又宽 ✓ |
| `.` | 11 | 5 | 5 | 18 B | 句点 ✓ |
| `A` | 21 | 21 | 23 | 168 B | 大写 ✓ |
| `H` | 21 | 18 | 23 | 127 B | 高大于宽 ✓ |
| `中`(U+4E2D) | 30 | 23 | 29 | 89 B | 全角 ✓ |
| `国`(U+56FD) | 30 | 24 | 26 | 224 B | 全角 ✓ |

字节统计也支持这个顺序：byte15（advance）有 95% 是 30（汉字全角步进），
byte17（width）众数 29，byte18（height）众数 28，byte19 集中在 0..4（flags）。

字号 30 px、436 条 ASCII/符号 + 29,428 个 30 宽汉字，码点 1..65533（仅 BMP，无扩展 B 区）。

## 19. 字形位图编码：边界钉死，仍未解出

本轮排除和确认了这些：

| 假设 | 结论 |
|---|---|
| 裸 1/2/4/8bpp 光栅 | **否**。按正确 w/h 以 2bpp 连续打包渲染呈噪声 |
| 双 bitmap plane | 否 |
| 转置/列优先 | 否 |
| zlib 压缩 | 否（全 10 MB 扫描无有效流） |
| 固定 XOR 掩码 | 否（7 个同尺寸字形异或后熵仍 7.01） |
| 熵编码（Huffman/算术/游程） | **是**，这是唯一自洽的解释 |

定量证据（熵编码的指纹）：

- `中`：89 B / 667 px = **1.07 bit/px**
- `国`：224 B / 624 px = **2.87 bit/px**
- 30 宽汉字均值：240 B / ~850 px = **2.26 bit/px**
- 占 4bpp 原始容量（450 B）的 **58%**，且方差极大（11 B ~ 411 B）

同字号同类字形的 bits/px 相差 2.7 倍，只有"按内容自适应分配码长"才能解释。
另外偏移字段是 **24.8 定点**（低字节常为 4/5/6），说明码流是**按位连续打包**的，
每个字形从任意位位置开始 —— 这也符合算术编码器的特征。

**要真正解出码流，必须定位解码器本体**。本轮试过这些锚点均未命中：
读取指标三元组（+15/+17/+18）的函数有 4 个候选，但都不含 `>>8` 偏移解算；
按码点二分查找（+13/+14 + 移位）筛出 16 个候选，抽查后均为容器/排序代码。
结论：字模解码器很可能挂在 **C++ 的字体对象虚函数**后面，且不直接做 `>>8`
（而是像 `0x420ba504` 那样按字节拼 u32），静态特征不明显。
下一轮若继续，建议顺着 `0x420a09a0`（刷新主控）的调用图向上找 `draw_text`。

## 20. 每相位耗时的硬账（这轮最有价值的一条）

上一版我把总时间当成"可能 100 ms 也可能 550 ms"两说，现在可以钉死了。

读上游 `render.c` 的代码路径：

```c
frame_count = waveform_phases->phases;      // 相位数 = 帧数
render_context.cycle_frames = frame_count;
render_context.phase_times  = waveform_phases->phase_times;
```

关键：在本固件用的 **LCD 渲染后端**里，`phase_times` **只被赋值、从不被消费**
（`output_lcd/render_lcd.c` 中没有引用）。也就是说每帧的时长**不由波形表的
`phase_times` 决定，而由总线时序决定**：

```
每行字节数 = 960 px × 2 bit / 8 = 240 B
每帧行数   = rounded_display_height() = ((540+7)/8)*8 = 544 行
每帧传输量 = 544 × 240 = 130,560 B
24 MHz 下   = 130,560 / 24e6 = 5.44 ms   （再加 le_high/front_porch，约 5.5 ms）

总刷新时间 ≈ 步数 × 5.5 ms
```

于是各场景的时间账（推算，误差在 ±10% 内）：

| 场景 | 步数 | 总线时间 | 传输量 |
|---|---|---|---|
| 文字快速（LIGHT_TEXT / DYNAMIC_MOTION） | 14 | **≈ 77 ms** | 1.83 MB |
| 文字锐利（LIGHT_TEXT_CRISP / HISTORY_REBASE） | 17 | **≈ 94 ms** | 2.22 MB |
| 整屏（FAST_FULL） | 20 | **≈ 110 ms** | 2.61 MB |
| 满波形 GC16（9–12 °C，38 相） | 38 | ≈ 209 ms | 4.96 MB |
| 满波形 GC16（18–21 °C，57 相） | 57 | ≈ 314 ms | 7.44 MB |

对比：**如果按满波形刷全屏，一次要 210–310 ms；作者用 14–20 步把它压到 77–110 ms。**

这条也能和固件的日志对上账：日志里的 `传输合计=%uKB` 对一次 14 步刷新应读到
约 **1827 KB**，与上表 1.83 MB 一致 —— 可以用串口验证我这个模型。

## 21. 只有一张波形表 → "步"是运行时传参截断的

我把 `.data`/`.rodata` 里所有"像 EpdWaveform 的 12 字节结构"都扫了一遍
（modes 1..9 / temp_ranges 1..9 / 两个指针均落在合法段内），过滤后**只有一张真表**：
`0x3c449cd8`（modes=3, ranges=7），它位于 `.rodata`（flash，只读）。

所以：**固件无法就地修改 `phases`**，也不可能为每个 profile 各存一张表。
唯一可行的做法是——按 profile 传一个"临时的 `EpdWaveformPhases`"给渲染层：

```c
EpdWaveformPhases tmp = { .phases = steps,          // 14 / 17 / 20 …
                          .luts   = 原表同一组 LUT,
                          .phase_times = NULL };
```

即**取同一组 LUT 的前 N 个相位**（截断），这就是"步"的物理含义。
截断的代价是灰度未完全落定（残影/对比度下降），所以才有 `_CRISP` / `_ENHANCED`
这类"多给几步"的变体，以及 `BLACK_CLEAN_*` 这类"定期彻底清一次"的场景。

## 22. 更新地址速查（第三次）

| 内容 | 地址 |
|---|---|
| 唯一波形表（modes=3, ranges=7） | `0x3c449cd8`（.rodata，只读） |
| `EpdDisplay_t`（960×540/8bit/24MHz） | `0x3c455aa8` |
| profile 描述符构造 | `0x4206251c` / `0x420625b8` |
| kind→波形 + 脏矩形合并 | `0x42062204` |
| 刷新主控（steps 分支） | `0x420a09a0` |
| 字形记录结构 | font 分区 `0x00000C`，20 B × 43511 |
| 疑似"按字节拼 u32 + 排序/查找" | `0x420ba504` |
| 速度/花纹名 + 计时打印 | `0x420c7db7` ~ `0x420c7ee2` |

---

# 第四次深挖（位级结构 + 设置词表）

## 23. 字形流是位级打包的（本轮唯一硬结论）

对上万条字形流做首/末字节统计，得到两个决定性事实：

| 统计量 | 结果 | 含义 |
|---|---|---|
| 首字节为 0x00 的比例 | **30,296 / 43,461 = 69.7%** | 大量字形开头是一串空行，且空行几乎不耗码 |
| 首字节熵 | 2.20 bit | 强偏置，不是随机码流 |
| 末字节取值 | 集中在 0x00/0x80/0xC0/0xA0/0xD0 | 全部是"低位为 0"的值 → **MSB-first 打包 + 尾部补零** |
| 全部字节熵 | 7.07 bit | 中段接近均匀，说明是自适应分配码长 |

即：**码流按位连续打包、MSB 在前、末尾补 0，空行代价极低。**
已排除的假设：任意位宽/行距的裸光栅、zlib、固定 XOR、双 bitplane、转置。
剩下的唯一自洽解释是**二维游程/熵编码**（空行与同值游程用短码）。

代价是：**没有解码器就无法重建像素**。本轮又试了两个锚点均未命中
（读 +15/+17/+18 的 4 个候选函数里没有 `>>8` 偏移解算；按码点二分的 16 个候选
经抽查全是容器/排序代码）。字模解码器很可能在 C++ 字体对象虚函数后面。

## 24. NVS 是空的

`nvs.bin` 全 5 个 4 KiB 页 `state=0xffffffff`、`nonFF=0` —— 这是**出厂镜像**，
所有设置都是设备首次运行后才写入的。所以"从 NVS 反推当前配置"这条路走不通。

## 25. 设备功能/设置词表（从 rodata 恢复）

`0x3c449554` 起是一张"功能组 key + 中文标签"的密集表：

| key | 中文 | 子项 |
|---|---|---|
| `link_usb` | U盘模拟 | 全速模式 |
| `link_web` | 在线配置 | AP模式 / STA模式 |
| `link_page` | 远程操控 | 蓝牙翻页 / WIFI翻页 |
| `link_cast` | 互动投屏 | 服务器模式 |
| `link_nfc` | NFC门禁 | 复制卡片 / 模拟卡片 |

紧随其后的设置键（与阅读/显示相关）：

```
fast_turn    home_key    home_long   orientation  boot_guard  light_max
func_key_tl  func_key_tr func_key_bl func_key_br  pgup_long   pgdn_long  nfc_uid1
```

其中 **`fast_turn`** 就是"快速翻页"开关（对应 `TEXT_RAPID_*` 三阶段动画），
`orientation` 对应四个方向的 `_o0..o3` 缓存，`light_max` 是前光亮度上限。

文件命名体系（同一区域）：
`.emeta/.mmeta/.fmeta/.meta`（元数据）、`.aidx/.aidx.tmp/.aidx.bak`（书籍索引，带 tmp/bak 保护）、
`.jpg.src/.png.src/.bmp.src`（上传原图的暂存）、`.saved/*_o{0..3}.cache`（预渲染缓存）。
编码支持：UTF8 / GBK / BIG5 / UTF16LE / UTF16BE。

## 26. 6 组图案数据（几何未定，标为未决）

`0x3c3e6a40` 起 96 字节，取值只出现 nibble `{0,5,a,f}` —— 这是 2bpp/4bpp 图案的特征。
按 6 组 × 16 B 切分（对应"竖条/横条/斜向/擦除 + 2"），但按 8×8 2bpp 平铺渲染**不成规律**，
说明平铺几何不是我猜的那样（也可能是 4×16 或线性阈值表）。
另外这 96 字节**没有任何 l32r 直接引用**（按 16 B 边界逐组查过），
说明它只能通过某个结构体基址 + 偏移被访问 —— 这也是没能确认消费方的直接原因。

结论：**"竖条/横条/斜向/擦除"确实是 4 选 1 的图案选项（代码里有 `bgeui idx,4` 分支），
但图案用于"清残影"还是"图片抖动"，本轮未能判定。**

## 27. 步/条 之争：仍差最后一步，给出判定配方

两种假设下 `传输合计` 的期望值差异极大，这是最快的判定点：

| 假设 | 传输合计期望 | 理由 |
|---|---|---|
| **步 = 帧数**（我倾向） | ≈ 步数 × 127.5 KB = **1827 KB**（14 步） | 每帧都要整屏扫一遍（`lines_total = 544`，与面积无关） |
| 步 = 水平分带 | ≈ 面积字节数 / 1024 ≈ **100~150 KB**，且与步数无关 | 每条带只发自己那几行 |

判定方法：串口抓一条 `汇总 …` 日志，看 `传输合计` 与 `步` 的乘积是否恒为 127.5 KB。
同时看 `条` 是否恒等于 544（整屏）——若是，则进一步支持"帧数"假设，因为
`lines_total` 在 epdiy 里被固定成 `rounded_display_height()`，与实际脏行数无关。

我倾向"帧数"的三个理由：
1. 步数是**按 profile 静态写死**的，而分带数必须依赖面积，无法预先写死；
2. 日志里 `循环外余`（remainder outside loop）与 `尾清`（tail clear）天然对应"帧循环"；
3. epdiy 的 `cycle_frames` 就是由相位数决定的帧数，`lcd_do_update` 内是
   `for (k = 0; k < cycle_frames; k++)` 的帧循环，每帧一次 `frame_done` 等面板 ——
   与日志里"每步一次 BUSY"的结构完全对应。

---

# 第二部分：小纸 Pico 生态横向技术评估（§31–§40）

> 目的：把第一部分从 EDCBook 逆出来的那套判据，套到用户手上这台 **MindReset 小纸 Pico** 的 17 个可刷系统上，
> 回答"哪些从技术层面能达到 EDCBook 的显示效果"，并给出可落地的选型建议。
>
> 方法：文档源仓库 `MindReset/dot_web_docs`（zh-Hans-CN/read_0/start/*.mdx，17 篇）+ GitHub 源码树扫描
> + 关键文件直读。凡未直读源码的结论，均在文中标注"文档/间接证据"。

## 31. 硬件与公共基线

| 项 | 小纸 Pico（Read Pico） | 对比：EDCBook |
|---|---|---|
| 主控 | ESP32-S3 | ESP32-S3 |
| Flash | 16 MB（官方安装页提示"备份完整 16 MB Flash"） | 16 MB |
| 面板 | **E0470A01 4.7" 单色 684×1216，40 pin** | 960×540 |
| 像素数 | 831,744 | 518,400 |
| 接口 | 8 位并行，`LCD_CAM` 外设 + DMAGDMA | 8 位并行 @24 MHz |
| 帧缓存 | 4bpp（epdiy highlevel） | 4bpp |
| 灰阶 | **16 级** | 16 级 |
| **帧周期** | **固定 11,090 µs（≈90 Hz）**，取自面板算法文档 | ≈5.5 ms（推算） |
| 每行字节 | 684 px × 2 bit / 8 = **171 B** | 240 B |
| 每帧字节 | 171 × 1216 = **207,936 B（203 KiB）** | 130,560 B |
| 等效带宽 | 207,936 / 11.09 ms ≈ **18.75 MB/s** | ≈23.7 MB/s |

**结论：两台机器的底层机制完全同类**——都是"并行总线 + LCD_CAM + epdiy 4bpp + 多相位波形"。
EDCBook 那套"为什么快"的机制，在小纸 Pico 上是**天生具备**的，不需要重新发明。

## 32. 17 个系统的谱系分类

三族：**A = 官方 epdiy 血统**，**B = freeink-sdk 血统**（多机型抽象，但在小纸 Pico 上仍走 epdiy 并行路径），
**C = 源码未公开**。

| # | 系统 | 源码可得 | 族 | 关键证据 |
|---|---|---|---|---|
| 1 | 官方 Demo | `MindReset/read_pico_firmware`（383 文件） | **A** | `components/epdiy` + `components/e0470_epaper_waveform` |
| 2 | kiikoread | `wegooo-cell/read-pico-reader`（1997 文件） | **A+** | 同上 + `pie_pixels.S` + `continuous_du` + 8 带节拍 |
| 3 | if-ink OS | `yiifanrecyclable/if-ink-OS`（5198 文件） | **A+** | 同上 + **`e0470_page_turn`** + `ui_image_dither.c` + `md4c` |
| 4 | XH View OS | `XHFO/XH-View-OS-For-Pico`（1048 文件） | **A+** | 同上 + `read_pico_ble_pager` + `test_native_preview_gray16.py` |
| 5 | YanReader | `autumnc/YanReader-pico`（1014 文件） | **A+B 混合** | vendor 官方栈 + `components/crossmux` + `lua54` + `tests/host/dither` |
| 6 | PageRest | 仓库 404（`fengcheng01/read_pico_firmware`） | **A**（文档明证） | 文档："专门为 4.7" **16 级灰阶**设计，标准灰阶 + 快速刷新路径 + 可配置清残影周期" |
| 7 | WhiteOS | `446599/whiteos`（发布站，非源码） | **A**（间接明证） | 发布包含 `components/{epdiy,e0470_epaper_waveform,continuous_du}/LICENSE` |
| 8 | CrossMux | `0x1abin/freeink-sdk`（1143 文件） | **B** | 多驱动框架，见 §33 |
| 9 | RickyOS | `chinoryunqin/RickyOS`（1765 文件） | **B** | `freeink-sdk` 子模块 + `lib/EpdFont`(131) + `lib/hal/HalDisplay` |
| 10 | 脆皮鸭 CPYOS | `Yana-Hangabina/cpyos`（1986 文件） | **B** | 同上 + `test/absolute_grayscale` + `gray16.jpg` + `GrayCoverage.h` |
| 11 | VanOS | 无仓库 | **A**（固件已验） | `vanos.bin` 内含 `components/e0470_epaper_waveform` + `components/epdiy/src/output_lcd/*` + `continuous_du` |
| 12 | CrossLink | 无仓库（crosslink-reader.top） | **A**（固件已验） | `components/pico/epdiy/src/output_lcd/*` + `components/pico/e0470_epaper_waveform`；project=`linkui`，IDF **v5.4.2**（全生态唯一非 6.x） |
| 13 | Just Read | 无仓库（flasher.smn.icu） | **A**（固件已验） | `components/read_pico` + `e0470` + `epdiy/output_lcd`；project=`Read_Pico`，IDF v6.1 |
| 14 | Pico Page | 无仓库（picopage.wulu.zone） | **A**（固件已验） | `pico_bsp/epdiy/src/output_lcd/*` + vendor 官方 `read_pico_firmware/components/e0470_epaper_waveform` |
| 15 | AuraReader | 无仓库（aurareader.cn） | **A**（固件已验） | `components/read_pico` + `e0470` + `epdiy/output_lcd` + `continuous_du` |
| 16 | Take Easy | 无仓库（take-easy.pages.dev） | **A**（固件已验） | 同上 + `continuous_du`；CMake project 名仍为 `Read_Pico` |
| 17 | Folio Book | 无仓库（esp-flasher） | **A**（固件已验） | project=`PicoOS`，`./components/read_pico/read_pico_board.c` + `e0470` + `epdiy/output_lcd` |
| 18 | ThingsOS | `flowflic/ThingsOS` 仅 9 文件 | **A/B 混合**（固件已验） | 编译路径 `D:/crossmux/references/read-pico-official/components/...` |

### 32.1 闭源系统固件取证实录

方法：从各官网的 `manifest.json` / `release.json` / 前端 JS 里找出刷机镜像，下载后解析 ESP-IDF app descriptor，
再用 `__FILE__` 字符串（编译期源码路径）判定血统——与 §1 分析 EDCBook 用的是同一手法。

| 系统 | 取得方式 | 镜像 | app_desc（version / project / IDF） | 判定 |
|---|---|---|---|---|
| **Take Easy** | `take-easy.pages.dev/firmware/manifest.json` → `v2.3/firmware.bin` @0x10000 | 3.80 MB | `2.3` / **`Read_Pico`** / v6.1-dirty | **A** |
| **Pico Page** | 官网直链 `pico-page-0.6.2-read_pico-release-full.bin` | 3.91 MB | `0.6.2` / **`pico_page`** / v6.1-dirty | **A** |
| **VanOS** | `vanos.pages.dev/manifest-full.json` → `merged-binary.bin` @0 | 13.07 MB | `2026.11.17.3` / **`VanOS`** / v6.1-dirty | **A** |
| **AuraReader** | `aurareader.cn/firmware/manifest.json` → `…-full-16MB.bin` @0 | 16.00 MB | `v0.5.9-firefly.alpha.79-rc.64` / **`Read_Pico`** / v6.1 | **A** |
| **ThingsOS** | `thingsos.scholarcn.com/release.json` → `…-usb.bin` @0 | 15.84 MB | `0.4.0` / **`ThingsOS_rescue`** / v6.1 | **A/B 混合** |
| **Folio Book** | `esp-flasher…/firmware/manifest.json`（需 sharecode Cookie）→ `firmware/foliobook/FolioBook-full.bin` | 5.83 MB | `1` / **`PicoOS`** / v6.1.0 | **A** |
| **CrossLink** | OSS 桶可列举 → `firmware/pixel-pico-full.bin-v4.3.1T` @0 | 16.00 MB | `6df83acc-dirty` / **`linkui`** / **v5.4.2** | **A** |
| **Just Read** | `cdn.xmoa.smn.icu/downloads/models.json` → `…/mindreset-read-pico-s3/ota/stable/0.3.3/firmware.bin` @0x20 | 3.48 MB | `0.3.3` / **`Read_Pico`** / v6.1 | **A** |

**逐条的源码路径原文（`__FILE__` 字符串摘录）：**

```
Take Easy :  ./components/read_pico/read_pico_board.c
             /./components/e0470_epaper_waveform/e0470_epaper_waveform.c
             /./components/epdiy/src/output_lcd/render_lcd.c
             /./main/font/stb_truetype.h
Pico Page :  /Users/wulu/workspace/pico-page/build/firmware-release/pico_bsp/epdiy/src/output_lcd/lcd_driver.c
             pico-page/.local/read_pico_firmware/components/e0470_epaper_waveform/e0470_epaper_waveform.c
VanOS     :  ./components/read_pico/read_pico_board.c  +  /./components/epdiy/src/output_lcd/lcd_driver.c
AuraReader:  ./components/read_pico/read_pico_board.c  +  /./components/e0470_epaper_waveform/…
Folio Book:  ./components/read_pico/read_pico_board.c  +  ./components/read_pico/read_pico_init.c
ThingsOS  :  /D:/crossmux/references/read-pico-official/components/epdiy/src/output_lcd/lcd_driver.c
             /D:/crossmux/references/read-pico-official/components/e0470_epaper_waveform/…
```

**四条值得单独记的结论：**

1. **"C 族"基本不存在。** 原先标注"源码未公开"的 8 个系统里，能取到镜像的 6 个**全部是 A 族**
   （官方 epdiy 并行 + e0470 波形 + stb_truetype）。官方 Demo 事实上是这整个生态的**事实标准底座**，
   第三方绝大多数是它的 fork，而不是另起炉灶重写驱动。
2. **`continuous_du` 已渗透到第三方**（Take Easy / VanOS / AuraReader 都带），
   说明"逐像素相位记账"这套机制在社区里被接受并复用。
3. **ThingsOS 是最有信息量的一条**：编译路径是 `D:/crossmux/references/read-pico-official/…`，
   即它在 CrossMux（B 族）的工程树里构建，但把官方固件作为 references 引入 ——
   **B 族工程基建 + A 族显示栈**的混合体。
4. **CrossLink 的设备表**（`x4pro / mofeiM4 / pico / eegoA4 / nologo397 / seeedSticky / paperMono / wodle`）
   与 freeink-sdk 的驱动清单一一对应，故判为 B 族；其 pico 整包在 OSS 上返回 404，未能取到镜像验证。


### 32.2 波形层比对：8 个固件用的都是同一套原厂波形（决定性结论）

做法：从官方仓库取 `components/e0470_epaper_waveform/waveforms/{du,gc16,gl16,gray8_gc16}.h`，
把 `uint8_t[phases][16][4]` 的数组体解析成原始字节，取中段 64 B 作签名，到每个固件里精确搜索。

| 系统 | DU（20 相） | GC16（48 相） | GL16（48 相） | **GRAY8**（30 相，8 灰快档） |
|---|---|---|---|---|
| Take Easy | ✓ | ✓ | ✓ | — |
| Pico Page | ✓ | ✓ | ✓ | **✓** |
| VanOS | ✓ | ✓ | ✓ | **✓** |
| AuraReader | ✓ | ✓ | ✓ | **✓** |
| ThingsOS | ✓ ×2 | ✓ ×2 | ✓ ×2 | — |
| Folio Book | ✓ | ✓ | ✓ | — |
| CrossLink | ✓ | ✓ | ✓ | — |
| Just Read | ✓ | ✓ | ✓ | — |

**三条推论：**

1. **波形层 100% 原厂，无一改动**。所有固件都逐字节包含官方 e0470 的 DU/GC16/GL16 LUT。
   这意味着：**这批系统在"灰阶正确性/对比度/残影倾向"的物理上限上是完全一致的**，
   EDCBook 那种"换一套 7 温度档波形"的差异化，在这个生态里**没有任何人做**（呼应 §38）。
2. **只有 Pico Page / VanOS / AuraReader 链接了 GRAY8 表**（8 级可分辨灰、30 相、整屏约 360 ms）。
   这是目前唯一能在波形层面区分的功能差异——它们可以选择"更快但仍带灰"的页面模式。
3. **ThingsOS 里每套表出现 2 次**，说明它同时链入了两套构建产物（或 48 相与裁剪后表各一份）。

### 32.3 刷新策略层：各系统自己的词表（这才是真正的差异所在）

波形一致 ⇒ 差异全在上层。把每个固件的中文 UI/日志字符串按"刷新语义"筛出来对比：

| 系统 | 自己的刷新策略词汇 | 机制判读 |
|---|---|---|
| **CrossLink** | 文字**两遍法**整屏满 %d 次；**灰阶位平面**（lsb/msb）；**灰阶整图缓冲**；**差分基准帧**；`DU 重驱满 %d 次`；`差分链达 %d 帧`；"第一遍改 **GC16 全刷恢复 DC 平衡**"；"插入 GC16 全刷恢复 DC 平衡"；"开机首帧 GC16 from_white 全刷去残影"；"升级 DU 整屏重驱清残影"；"行队列欠载"；"文字 4bpp 目标页/动画" | **最深的一层**：4bpp 文字目标页 + 灰阶位平面分离 + 差分基准帧 + **DC 平衡恢复** + DU 重驱/差分链计数。工程语言与 EDCBook 的中文计时日志同一路数 |
| **Pico Page** | 翻页效果；沿用当前刷新模式；水波纹；**清晰模式每页全刷**；**自动全刷间隔**；立即全刷；**定期全刷**；"仅用于正文非全刷更新"；"残影和灰阶**均待真机验证**" | 策略参数最齐全的**用户可调**样本；最后一句还留着开发者的诚实备注 |
| **Just Read** | 阅读刷新模式；**16 灰度**；**每 %u 次局刷**（后全刷）；清除残影；残影清除 | 典型的"局刷 N 次 + 一次清残影"计数器 |
| **AuraReader** | 刷新设置；**深度清除残影**；长按全刷；确认清除残影；翻页测试 | 有"深度清除"分档 |
| **ThingsOS** | 刷新模式；**全刷间隔**；**按设定翻页次数完整刷新**；灰度居中裁剪（Web 端） | 与 Just Read 同类 |
| **Take Easy** | 水波纹；上下/左右翻页；阅读字体 | 策略层很薄 |
| **VanOS** | 主要是蓝牙翻页器 + 字体；"TF 卡上没有额外字体" | 策略层很薄，偏"字体可换" |
| **Folio Book** | 基本只有字体相关；"已退回内置字体" | 策略层最薄 |

### 32.4 插桩深度（中文 ELOG 数量，作为"被认真调过"的代理指标）

| 系统 | 中文 `E/W/I (%lu)` 日志条数 | 关键条目 |
|---|---|---|
| **CrossLink** | **104** | 灰阶位平面 / 4bpp 目标页 / 两遍法 / 差分基准帧 / DC 平衡 / 行队列欠载 |
| VanOS | 29 | 翻页器配对、字体加载 |
| Folio Book | 4 | 字体回退 |
| Take Easy | 2 | — |
| Pico Page / AuraReader / ThingsOS / Just Read | 0 | （日志用英文或未插桩） |

CrossLink 的 104 条中文日志，和 EDCBook 那条"汇总…步循环…BUSY/传输/LUT"是同一种工作方式的产物：
**作者在真机上用日志一项项抠刷新流程**。这也解释了它为什么有 16 MB 全量镜像里最大的代码密度
（6265 个 2 KB 窗口，8 个固件中最多）。
**统计口径已更新**：原 §35.7 写"8 个闭源系统只能从文档推断"，现为
**8 个全部二进制实证，且全部判为 A 族**。CrossLink 的 B 族推定已被其固件推翻（详见 §39 第三条勘误）。

> 注：CrossMux 是 freeink-sdk 的作者项目，而 RickyOS / CPYOS / YanReader 都基于它二次开发；
> 所以"CrossMux 系"实际上是**一个 SDK + 多个发行版**的关系。

### 32.5 波形"配置"比对：相位数只有两家动过

§32.2 证明了 **LUT 字节**全生态一致；但"用多少相"是**运行期配置**（官方在开机时用
`e0470_waveform_trim()` 从 48 相裁到 36/37，裁剪参数是编译期常量）。所以只要扫二进制里的
`EpdWaveform` / `EpdWaveformMode` / `EpdWaveformPhases` 结构，就能读出每个固件**实际链接了哪几档相位数**。

扫描结果（`modes=3` 表示含 DU/GC16/GL16 三模式；`t1/t2/t5` 即 epdiy 的 `MODE_DU=1 / GC16=2 / GL16=5`）：

| 系统 | 链接的波形档位（DU / GC16 / GL16 相位数） |
|---|---|
| **Folio Book** | 仅默认：`20 / 36 / 37` |
| **ThingsOS** | 默认 `20/36/37` + FOLLOW `8` |
| **Just Read** | 默认 `20/36/37` + FOLLOW `8` |
| **Pico Page** | 默认 `20/36/37` + **GRAY8 `20/30/30`** |
| **VanOS** | 默认 `20/36/37` + **GRAY8 `20/30/30`** + 完整表 `20/48/48` + FOLLOW `8` + 1 相桩 |
| **AuraReader** | 默认 `20/36/37` + **GRAY8 `20/30/30`** + 完整表 `20/48/48` + FOLLOW `8` + 单独 GC16-only `36`、GL16-only `37` + 1 相桩 |
| **Take Easy** | 默认 `20/36/37` + 完整表 `20/48/48` + **GL16-only `32`**（非官方的 30）+ FOLLOW `8` + 1 相桩 |
| **CrossLink** | 默认 `20/36/37` + **自定义 trim `20/39/37`** + 完整表 `20/48/37` + `20/36/0` + **5 相加速桩 `5/5/5`** + 1 相桩 |

**四条结论：**

1. **GC16 默认档全员都是 36 相**（= 官方裁剪器 `erase_max=11, sat_cut=5` 的产物）。
   没有任何人把默认档调得更激进或更保守。
2. **只有 CrossLink 做了自己的 trim**（GC16 = **39** 相），并且额外做了一个
   **全 5 相的加速桩** —— 这是全生态唯一"自己动波形配置"的证据（LUT 字节仍是原厂）。
3. **Take Easy 的 GL16 只有 32 相**（官方 GRAY8 是 30），是另一处轻微自定义。
4. **GRAY8（`20/30/30`）只出现在 Pico Page / VanOS / AuraReader** —— 与 §32.2 的 LUT blob 命中
   **完全一致**，两条独立证据互相验证，可以确认这三家的"8 灰快速档"是真接线，不是死代码。

### 32.6 CrossLink 的显示栈拆解（8 个里最深的一个）

用段映射 + l32r 交叉引用把它的中文日志按代码地址排序，能还原出模块布局与刷新链路。
它的日志带模块 tag：`[SLP]`（锁屏）、`[GFX]`（图形/差分）、`[GRAYIMG]`（灰阶整图）、`[XTH]`（灰阶通道）。

**开机日志（可直接读出面板参数）：**

```
%dx%d @ %dMHz, vcom %dmV, 差分链上限 %d
波形表 %u 字节落 PSRAM
本机有 %u 级整图灰阶通道 / 本机面板没有 N 级灰阶整图通道
```

**七个 EDCBook 没有的机制：**

| 机制 | 证据字符串 | 意义 |
|---|---|---|
| **波形表落 PSRAM** | `波形表 %u 字节落 PSRAM`、`波形表 %s 分配失败` | 波形从只读 flash 拷到 RAM，**运行期可改**（EDCBook 的波形表在 rodata，改不了，只能靠"传临时 phases"截断） |
| **相位池** | `相位池分配失败` | 不是简单截断，而是按像素/按扫描维护相位预算，接近 `continuous_du` 的思路 |
| **差分链（有上限）** | `差分链上限 %d`、`差分链达 %d 帧`、`缺少差分基准帧`、`差分窗口 phys=(%d,%d %dx%d) 占屏 %d%%`、`差分窗口无变化` | 连续差分刷新有**帧数上限**，超限强制全刷；还会打印差分窗口**占屏百分比**——这是防残影的量化手段 |
| **DC 平衡恢复** | `插 GC16 全刷恢复 DC 平衡`、`第一遍改 GC16 全刷恢复 DC 平衡` | 墨水屏双极性电荷平衡，长期单向驱动会导致残留/寿命问题。**EDCBook 完全没有这一层** |
| **灰阶位平面 + 整图缓冲** | `灰阶位平面分配失败`、`灰阶平面未就绪 lsb=%d msb=%d`、`灰阶整图缓冲分配失败 (%u 字节)`、`%u 级灰阶整图已上屏`、`灰阶波形上屏用时 %lu ms` | 灰阶走 lsb/msb 双平面 + 整图缓冲，并且**自己打上屏耗时** |
| **4bpp 文字目标页 + 两遍法** | `文字 4bpp 目标页分配失败`、`文字两遍法整屏满 %d 次`、`文字 4bpp 动画未就绪`、`文字 4bpp 滚动动画未就绪` | 文字单独一张 4bpp 目标页，两遍法上屏，还支持滚动动画 |
| **灰阶级数协商 + 快照缓存** | `本机有 %u 级整图灰阶通道`、`[SLP] cover %u 级灰阶快照命中: %s`、`[GRAYIMG] 灰阶快照%s`、`灰阶整图 + 锁标合成` | 按机型能力选择灰阶级数；锁屏/封面做灰阶快照缓存（等价于 EDCBook 的 `_o0..o3.cache`） |

另外两条细节：

- `开机首帧即文字 AA 帧` —— 它能把**开机第一帧就做成抗锯齿文字帧**，而不是先黑白再灰度；
- `行队列欠载` —— epdiy 的行队列欠载告警被本地化了，说明作者确实盯着这条底层错误。

**结论**：CrossLink 在"刷新控制"这一层的复杂度**高于 EDCBook**（DC 平衡、差分链上限、相位池、4bpp 目标页、灰阶能力协商），
而 EDCBook 的优势仍在 **预烘焙字库** 与 **多温度档波形** 两处。这两者是互补的。

### 32.7 CrossLink 的图片/灰阶管线：全生态唯一做了"色调曲线 + 误差扩散"

用 §40.1 的 `callgraph.py`（`calln` 解码，已用 EDCBook 的 objdump 结果标定到 **100% 命中**）
把含 `[GRAYIMG]` / `[JPG]` / `[IMG]` 日志的函数与它们的调用关系拉出来后，能看出 CrossLink
有一条**完整的图片→灰阶渲染管线**，日志逐段计时：

```
[JPG] Image dimensions: %dx%d
[JPG] Decoding JPEG: %s
[JPG] %dx%d -> %dx%d (scaleX=%.3f scaleY=%.3f)
[JPG] adaptive tone mean=%u dark=%u bright=%u bias=%d          ← 自适应色调分析
[JPG] adaptive tone analysis failed, rendering without extra tone
[JPG] pixel histogram 0=%lu 1=%lu … 14=%lu                     ← 16 级直方图
[JPG] 2x2 canvas alloc failed (%ux%u), falling back to 4-level FS  ← Floyd–Steinberg 到 4 级
[GRAYIMG] 解码 %dx%d 用时 %lu ms
[GRAYIMG] 误差扩散 %dx%d@%d 用时 %lu ms
[GRAYIMG] 面板没提供实测色调表
[GRAYIMG] %u 级灰阶整图已上屏
[GRAYIMG] 灰阶波形上屏用时 %lu ms
[JPG] plane blit=%lums
```

**并且找到了它的 16 级色调表**（全生态唯此一份，其余 7 个固件里都没有）：

```
0x3c38701c:  00 16 2c 44 5c 70 82 94 aa c3 d0 dc e8 f0 f7 ff
```

这是一条**非均匀单调递增曲线**（0x00→0xFF，中间步长从 0x16 递减到 0x08），
典型的"面板实测色调 / gamma 校正"数据：把线性 16 级灰映射到面板非线性响应的 16 级目标值。
配合 `面板没提供实测色调表` 这条告警可以确认：**没有实测表时会退回默认曲线**。

**和 EDCBook 的对比**：

| 能力 | EDCBook | CrossLink | 其余 6 个 |
|---|---|---|---|
| 抖动 | 6 组 2bpp 图案（有序抖动） | **Floyd–Steinberg 误差扩散（4 级）** | 无 / 仅 gamma |
| 色调映射 | 无 | **自适应 tone（mean/dark/bright/bias）+ 16 级色调表** | 无 |
| 图片解码 | M5GFX miniz（PNG） | JPEG 硬解 + 缩放 + 直方图 + 分带缓存 | 各异 |
| 大图支持 | — | `Image too large … max supported: %d pixels` 明确上限 | — |

这就是"显示效果好"里**最后一块 EDCBook 没有的东西**：EDCBook 靠波形表本身的灰阶梯子（它没有色调曲线），
CrossLink 额外做了一层**面板响应校正 + 误差扩散**，所以渐变色块和照片更不容易出现色阶断裂（banding）。

**模块标签分布**（可作为它的代码组织地图）：
`[ERS]` 101（阅读服务：TOC 预取/overlay 暂停恢复）、`[SLP]` 56（锁屏）、`[IMG]` 53、
`[JPG]` 19、`[XTH]` 19（灰阶通道）、`[GRAYIMG]` 9、`[GFX]` 7、`[PRV]` 6。

> 注：`[ERS]` 是 "Epub Reader Service"，不是误差扩散；它的 `gray16 images: decode=%lums aborted=%d failed=%d plane=%d`
> 仍属于图片统计。

### 32.8 这轮新增的两个可复现手段

1. **`calln` 精确解码**：Xtensa 的 `call0/4/8/12` 编码为 `word[3:0]==0x5`，`n=(word>>4)&3`，
   `imm18 = word>>6`（**必须做 18 位符号扩展**），目标 `= ((pc+4)&~3) + imm18*4`。
   用 EDCBook 已反汇编的 32,275 条 `calln` 标定，**命中 100%**。
   有了它就能在没有反汇编器的情况下建调用图——本轮还原 CrossLink 的日志函数、模块布局全靠这个。
2. **波形结构扫描**（§32.5）与**色调表/直方图特征搜索**（本节）：
   后者靠"256 字节全排列（Bayer 矩阵）"和"16 项单调递增且两端 0x00/0xFF 的字节表"两个特征，
   能在一堆固件里快速定位抖动矩阵与 gamma 表。

## 33. freeink-sdk 的真实形态（修正上一轮误判）

`0x1abin/freeink-sdk` 自称 "A hardware-independent SDK for building e-paper reader firmware"，
实测确实是**驱动抽象层**，这是理解 B 族的关键：

```
libs/display/FreeInkDisplay/src/driver/
    EpdiyLcdDriver.cpp        ← 并行 LCD_CAM 路径（小纸 Pico 用这个）
    CrossMuxSsd1677Driver.cpp
    Ssd1677Driver / Ssd2677Driver / Uc8179Driver
    Uc8253MurphyDriver / Uc8253X3Driver
    Uc8279Driver / Uc8279X4Driver / Uc8279cA4Driver
    It8951Driver / M5OfficialDriver / PaperMonoDriver
    Ed2208M5Driver / LgfxEpdDriver
libs/display/EpdiyLcd/src/epdiy/…          ← 内嵌 epdiy 源码（含 output_lcd）
libs/display/EpdiyLcd/src/e0470/waveforms/ ← 与官方同一套 e0470 波形
libs/display/FreeInkDisplay/src/lut/       ← 各控制器 LUT，含 UltraChipDirectGrayLuts.h
libs/hardware/BoardReadPico/src/ReadPicoEpdiyConfig.cpp  ← 小纸 Pico 的 epdiy 配置
```

**结论**：在小纸 Pico 上，RickyOS / CPYOS / CrossMux 走的是 **`EpdiyLcdDriver` + e0470 波形**，
与官方 Demo **同一套显示栈**。上一版把 `HalDisplay` 里的 LSB/MSB 双平面当成"小纸 Pico 只能 4 级灰"
是错的——那是它对 Xteink X3/X4、Waveshare 3.97" 那些 **SPI 控制器机型**的分支。

另一个被低估的点：`libs/font/FreeInkFont/` 里编进了**完整 FreeType**
（`afautofit` / `afcjk` 自动 hinting、`GSUB`/`GPOS` 字距与连字），外加 `stb_truetype`。
这意味着 B 族的**文字排版质量上限高于 EDCBook**：EDCBook 是预烘焙位图，没有 hinting、没有 kerning。

## 34. 判据：把 EDCBook 的优势拆成 8 条可检验指标

| # | 指标 | EDCBook 实测 | 小纸生态最佳实现 |
|---|---|---|---|
| M1 | 并行总线 + DMA | 8bit@24MHz + GDMA + IRAM ISR | ✅ 全 A 族 + B 族（Read Pico 分支） |
| M2 | 4bpp / 16 级真灰 | ✅ | ✅ A 族全部；CPYOS 另有 16 灰实验 |
| M3 | 差分 + 脏区裁剪 | 行/列 dirty + 差分包 | ✅ **按列裁剪 diff**（更细） |
| M4 | 相位裁剪 / 跳相 | 按 profile 固定截断 14/17/20 步（**有损**） | ✅ **按 (from,to) 直方图无损跳前导空相**（更强） |
| M5 | 分带流水 | 无 | ✅ kiikoread 8 带 / 44 节拍 / 11.09 ms |
| M6 | 实时笔迹 / 跟手 | 无 | ✅ `continuous_du` 逐像素相位记账 |
| M7 | 字体 | 预烘焙 43,511 字 / 16 级 / 58% 压缩 / XIP | ⚠️ 运行时 TTF（更灵活、排版更好，但无预热优势） |
| M8 | 温度分档波形 | **7 档 × 0–21 °C**，每档独立相位数 | ❌ **全生态单一 0–50 °C 档** |

M1–M6 小纸生态**全面具备、且 M3/M4/M5/M6 技术上优于 EDCBook**；M7 是路线不同；**M8 是唯一空白**。

## 35. 逐系统技术分析

### 35.1 官方 Demo（基线，必读）

**波形组件 `e0470_epaper_waveform`** 提供四张表：

| 符号 | 内容 | 用途 |
|---|---|---|
| `E0470_WAVEFORM` | GC16 **36 相** / GL16 **37 相**（开机裁剪派生）+ 阈值 DU（目标 0–7→黑，8–15→白） | 页面刷新主用 |
| `E0470_FULL_WAVEFORM` | GC16/GL16 **48 相**，DU **20 相**，单一 0–50 °C 档 | 对照 / A-B 对比 |
| `E0470_GRAY8_WAVEFORM` | **8 级可分辨灰**，GC16/GL16 **30 相**，整屏 ≈360 ms（默认表 ≈430 ms） | 可选"更快但仍带灰"模式 |
| `E0470_FOLLOW_WAVEFORM` | 开机生成的 **8 帧短 DU**（黑 7 / 白 8） | 触摸笔迹、实时读数 |

**裁剪器 `e0470_waveform_trim()`** —— 这是比 EDCBook 更讲究的地方。
它利用"同一套骨架"的前提（保持补齐 → 往反向轨道擦除 → 在目标轨道饱和 → **灰阶尾** → 结尾保持），
**保留灰阶尾段不动**，只裁"擦除上限"和"饱和开头"，再把所有 (from,to) 序列右对齐。
默认参数：`erase_max=11, sat_cut=5, white_sat_cut=0, hold=3`。
代价写得很清楚：**擦除余量变小，旧内容残影会先出现**，参数要对着残影在真机上调。

对照 EDCBook：EDCBook 是按场景**截断相位数**（14/17/20），灰阶尾段可能被切掉，所以需要
`_CRISP`/`_ENHANCED` 这类"多给几步"的补偿档；官方的做法是**结构性裁剪**，灰阶不受影响。

**epdiy fork 的四处改动**（`components/epdiy/README.md`）：

1. 删除 ESP32 I2S 输出路径，只保留 S3 的 LCD 路径；
2. 换掉 board 定义与 displays（只保留 `E0470_DISPLAY`）；
3. `render.c` / `highlevel.c`：**差分按列裁剪** + **按 (from,to) 直方图无损跳过前导空相位** + 各阶段耗时记录；
4. `output_lcd/render_lcd.c`：**每帧前预填行数可配置**（这是分带流水的旋钮）。

跳相的代码证据（`components/epdiy/src/render.c`）：

```c
static bool s_leading_skip_enabled;
void epd_set_leading_skip(bool enable);      // 开关
int  epd_last_leading_skip(void);            // 上次跳了几帧
static int leading_skip_frames(...);         // 取"出现过的 (from,to) 里最早真正有动作的相号"
                                             // present[] 为本次更新涉及的转换集合
                                             // skip >= phases 时退化为 phases-1
```

**无损**是关键词：它只跳过"对本帧确实什么都不做"的前导帧，之后的灰阶尾一帧不少。

### 35.2 kiikoread（推荐首选）

在官方基线上加的东西最多，而且都有量化口径：

| 机制 | 具体参数 | 出处 |
|---|---|---|
| 主刷新模式 | 普通 / **快速** / **水波纹(water)** 三档，普通与水波纹保留灰阶 | README |
| 分带流水 | **8 带 / 44 节拍 / 11,090 µs 目标**，且**每像素 37 相全部跑完** | README |
| 主屏波纹耗时 | 软件目标 **≈488 ms**（上一版 624 ms） | README |
| 逐像素连续 DU | 一次扫描推**一个**相位，每像素自记剩余相位；整屏一扫 **≈50 ms**，**与标记像素数无关** | `components/continuous_du/README.md` |
| S3 SIMD | `pie_pixels.S` + `pie_pixels_bench.c` | 源文件 |
| 锁屏帧缓存 | 16 级抖动帧存 `.readpico/locks/wallpaper.bin`，源图/方向/算法变更即失效 | README |
| 阅读字体 AA | 开关只改边缘覆盖率，**不改变排版、不多留一份字形缓存** | README |
| 内置黑体 | 覆盖 **6,763 个 GB2312 汉字**，无需 TF 卡字体包 | README |
| 自定义波形 | `my_waveform_du14.h`（DU 14 相） | 源文件 |
| Host 测试 | `reader_waveform_host_test.c`、`navigation_waveform_host_test.c`、`settings_motion_waveform_host_test.c`、`keyboard_refresh_host_test.c` 等 | `boards/metalio47/tests/tools/` |

**评价**：这是把"快"和"不掉灰"同时做到位的样本——它不是靠少跑相位换速度，而是靠
**分带流水 + 无损跳相 + 逐像素相位记账**。8 带/44 节拍这种参数化程度，比 EDCBook 手调的
24 个 profile 更工程化。

### 35.3 if-ink OS（翻页观感最讲究）

与 kiikoread 同源，但多了两件别人没有的：

- **`components/e0470_page_turn`** —— 独立成组件的**专用翻页波形**。EDCBook 里对应的是
  `TEXT_RAPID_BEGIN/CONTINUE/SETTLE` 三段 profile，但那是"场景名 + 步数"，而这里是一个
  真正独立、可独立调参的波形模块。
- **`main/ui/ui_image_dither.c`** —— 图片抖动的显式实现（对应 EDCBook 那 6 组 2bpp 图案表的功能位）。

附带 `md4c`（Markdown 渲染）与 `pico_weread`（微信读书）。

### 35.4 XH View OS / YanReader

- **XH View OS**：与 if-ink 几乎同一套组件（含 `e0470_page_turn`、`continuous_du`），
  多了 `read_pico_ble_pager`（BLE 翻页）、`read_pico_home_link`（双机联动），
  以及 `tools/test_native_preview_gray16.py` —— **16 级灰的离线预览校验工具**，
  说明作者在灰阶正确性上有回归手段。
- **YanReader**：结构最特殊。它同时 vendor 了**官方 `read_pico_firmware` 全套**和
  **`components/crossmux`（freeink-sdk）**，再加 `lua54`。等于把 A、B 两族的显示栈都带进来了，
  并把上层做成可脚本化。`tests/host/dither/` 有独立的抖动单测。

### 35.5 PageRest / WhiteOS（无源码，但有明确证据）

- **PageRest**：文档原文"针对小纸 Pico 的 4.7 英寸 **16 级灰阶**墨水屏设计，提供**标准灰阶和快速刷新路径**，
  并支持**可配置的清残影周期**"。这三句正好对应 M2 / M4 / M8 的"清残影"半边。
  仓库 `fengcheng01/read_pico_firmware` 已 404（私有或改名），无法验证实现。
- **WhiteOS**：仓库是发布站（203 文件，`firmware/`、`flash/`、`manual/`），但发布包内附带
  `firmware/licenses/source/components/{continuous_du, e0470_epaper_waveform, epdiy}/LICENSE`
  —— 这是 LGPL 合规的典型痕迹，**反证其二进制内确实链接了这三件套**，即 A 族。

### 35.6 B 族（CrossMux / RickyOS / CPYOS）

**共性**：`freeink-sdk` 的 `EpdiyLcdDriver` + e0470 波形（小纸 Pico），上层是一套跨机型的
`GfxRenderer` / `EpdFont` / `HalDisplay`。优势是"一份代码跑 10+ 机型"，劣势是在特定机型上
不如专用固件激进。

- **CrossMux**：SDK 本体 + 官网 Nightly 内测。是这一族的"上游"。
- **RickyOS**：UI/字体做得最重（`lib/EpdFont` 131 文件、`src/activities` 312 文件、
  `docs/engineering` 35 篇、`docs/sd-card-font-cache.md`、`rickyos-font-pack.md`），
  还有 `test/metalio_refresh`、`test/gfx_two_bit_mapping` 这类回归测试。
  纯从工程规整度看是这一族里最好的。
- **脆皮鸭 CPYOS**：最值得注意的是它在**往 16 级真灰推进**：
  `test/absolute_grayscale/AbsoluteGrayscaleTest.cpp`、`test/native_grayscale/`（含 `gray16.jpg`）、
  `lib/GfxRenderer/GrayCoverage.h`、`scripts/tests/test_native_grayscale.py`。
  还有一组 `docs/engineering/read-pico-*.md`（`refresh-stability` / `remaining-work` / `upstream-merge`），
  说明它对小纸 Pico 的刷新稳定性做了专门跟踪，并有 `patches/freeink-sdk/*.patch` 维护补丁。

### 35.7 原先的"C 族"：已由二进制实证推翻

**最初只能从文档推断，现已把 8 个镜像全部取到并实证**（详见 §32.1）。结论：

- **8 个闭源系统全部是 A 族**：VanOS、AuraReader、Take Easy、Pico Page、Folio Book、ThingsOS、CrossLink、Just Read。
  它们的 `__FILE__` 字符串里都能找到 `components/epdiy/src/output_lcd/lcd_driver.c` 与
  `components/e0470_epaper_waveform/e0470_epaper_waveform.c`（Pico Page 是 vendor 官方源码，
  ThingsOS 是在 CrossMux 树里引用官方 references）。
  → **"哪个系统画质更好"这个问题，在驱动层其实没有差异**：它们跑的是同一套 epdiy + 同一套 e0470 波形。
  差异只在**上层：刷新策略、字体、排版、UI 密度**。
- **CrossLink 一度判为 B 族，已被固件推翻**：其 OSS 桶可列举，取到 `pixel-pico-full.bin-v4.3.1T`（16 MB），
  `__FILE__` 显示 `components/pico/epdiy/src/output_lcd/*`，是 A 族；project=`linkui`，IDF v5.4.2。
- **Just Read 已取得**：`cdn.xmoa.smn.icu/downloads/mindreset-read-pico-s3/ota/stable/0.3.3/firmware.bin`，A 族。
- 原先"依赖 SD 卡字体的首帧更慢"这一条仍然成立（VanOS/Take Easy/Folio Book/PageRest 都属于这类），
  但**不再是"血统不同"的问题，而是"字体资源放在哪"的问题**。

## 36. 横向对比矩阵（显示相关）

| 系统 | 总线 | 灰阶 | 差分裁剪 | 相位优化 | 分带 | 连续DU | 字体 | 温度档 |
|---|---|---|---|---|---|---|---|---|
| **官方 Demo** | 并行 | 16 | **按列** | **无损跳相** | 可配置预填行 | ✅ | 运行时 TTF + 内置回退 | 1 档 |
| **kiikoread** | 并行 | 16 | 按列 | 无损跳相 | **8 带/44 节拍** | ✅ | 运行时 TTF + AA 开关 + 内置 6763 字 | 1 档 |
| **if-ink OS** | 并行 | 16 | 按列 | 无损跳相 | 有 | ✅ | 运行时 TTF | 1 档 |
| **XH View OS** | 并行 | 16 | 按列 | 无损跳相 | 有 | ✅ | 运行时 TTF | 1 档 |
| **YanReader** | 并行 | 16 | 按列 | 无损跳相 | 有 | ✅ | TTF + FreeType | 1 档 |
| **PageRest** | ? | **16（文档）** | ? | **快刷路径（文档）** | ? | ? | TTF（TF 导入） | ? |
| **WhiteOS** | 并行（证据） | 16（推定） | ? | ? | ? | ✅（证据） | ? | 1 档 |
| **CrossMux/RickyOS/CPYOS** | 并行（Read Pico 分支） | 16 | 按列 | 无损跳相 | 有 | ✅ | **FreeType 全量 + GSUB/GPOS** | 1 档 |
| **VanOS / AuraReader / Take Easy**（已验） | 并行 | 16 | 按列 | 无损跳相 | 有 | ✅ | 运行时 TTF（stb） | 1 档 |
| **Pico Page / Folio Book / ThingsOS**（已验） | 并行 | 16 | 按列 | 无损跳相 | 有 | 部分 | 运行时 TTF（stb） | 1 档 |
| **CrossLink**（已验） | 并行 | 16（级数协商） | 按列 | **自定义 trim 39 相 + 5 相加速桩** | 有 | 有**相位池** | stb + 灰阶位平面 + 4bpp 目标页 + **FS 误扩散/色调曲线** | 1 档 |
| **Just Read**（已验） | 并行 | 16 | 按列 | 无损跳相 | 有 | 部分 | stb + SD 卡字体 | 1 档 |
| **EDCBook（对照）** | 并行 | 16 | 行/列 | **固定截断（有损）** | ❌ | ❌ | **预烘焙 43,511 字** | **7 档** |

## 37. 选型推荐（面向"实际使用"）

> 判据分两类，**分开标注**：
> **【实证】** = 二进制/源码/发布数据可验证；**【判断】** = 基于文档与工程信号的推测；**【未知】** = 我没有证据。
> 排序权重：显示效果 > 翻页观感 > 成熟度/迭代活跃度 > 功能 > 可改造性。

### 37.1 成熟度硬数据（GitHub Releases，2026-11-18 采）

| 系统 | 仓库 | Release 数 | 最新版本 | 最近发布 |
|---|---|---|---|---|
| **kiikoread** | wegooo-cell/read-pico-reader | **35** | `v0.3.3-rc108` | 2026-11-16 |
| **YanReader** | autumnc/YanReader-pico | **31** | `v1.9.7` | 2026-11-07 |
| **if-ink OS** | yiifanrecyclable/if-ink-OS | 26 | `v0.2.4-beta.1` | 2026-11-17 |
| RickyOS | chinoryunqin/RickyOS | 7 | `v1.1.5` | 2026-10-10 |
| CPYOS | Yana-Hangabina/cpyos | 7 | `cpyos-0.7.0` | 2026-11-06 |
| XH View OS | XHFO/XH-View-OS-For-Pico | 4 | `v0.40.0-dual112` | 2026-11-15 |
| 官方 Demo | MindReset/read_pico_firmware | 0（仅 commit） | — | 2026-10-11（最后 push） |
| ThingsOS | flowflic/ThingsOS | 0 | — | 2026-10-18 |

闭源系统只有版本线索：**CrossLink** 的 OSS 上 pico 包有 `v4.2.2T / v4.2.4T / v4.3.0T / v4.3.1T`
（4.x 线、多版本并存）；**AuraReader** 是 `alpha.79-rc.64`（**alpha 通道**）；VanOS `2026.11.17.3`；
Pico Page `0.6.2`；Take Easy `2.3`；ThingsOS `0.4.0`；Just Read `0.3.3`。

### 37.2 排序（面向使用）

| 档 | 系统 | 为什么排这 | 主要风险 |
|---|---|---|---|
| **S1** | **kiikoread** | 【实证】37 个灰度相位一相不省、8 带/44 节拍、水波纹模式、AA 开关、`continuous_du`、内置 6763 字、host 波形单测；【实证】**35 个 release、rc108**，是全生态迭代最猛的 | 新版材料用 Personal Study License（个人学习可用，**商用需授权**） |
| **S2** | **CrossLink** | 【实证】画质管线最强：**16 级色调曲线 + Floyd–Steinberg 误差扩散 + 自适应 tone**、DC 平衡恢复、差分链上限、相位池、4bpp 文字目标页；【判断】4.x 版本线 + 104 条中文埋点，像长期打磨过 | 【未知】闭源，功能面与稳定性无法验证 |
| **A1** | **YanReader** | 【实证】31 个 release，版本号已到 **v1.9.7**（语义化稳定度高）；A+B 双栈 + Lua 扩展 | 双栈结构复杂，出问题难定位 |
| **A2** | **官方 Demo** | 【实证】厂商维护的技术基线（无损跳相、按列 diff、波形裁剪器都在这里）；最保守 | 功能最少（更像"参考实现"） |
| **B1** | **if-ink OS** | 【实证】唯一有**独立翻页波形组件** + 图片抖动 + Markdown + 坚果云 + 微信读书；26 release | 停在 `v0.2.4-beta.1`，beta 期 |
| **B2** | **RickyOS** | 【实证】字体系统最强（完整 FreeType + GSUB/GPOS + SD 字体缓存）；多机型 | 为多机型设计，小纸 Pico 上不是最优路径 |
| **B3** | **CPYOS** | 【实证】在做 16 级真灰实验（`absolute_grayscale`）；CrossPoint 系 UI | 0.7.0，灰度实验未定型 |
| **B4** | **XH View OS** | 【实证】双机联动/BLE 翻页器/游戏联动 + 16 灰预览校验 | 4 个 release，功能面广但迭代少 |
| **B5** | **Pico Page** | 【实证】刷新设置最细（自动全刷间隔、清晰模式每页全刷）+ GRAY8 档 | 【未知】闭源，`0.6.2` 早期 |
| **B6** | **VanOS** | 【实证】A 族 + SD 卡换字体方便 + 蓝牙翻页器 + GRAY8 | 【判断】策略层很薄，翻页观感偏基础 |
| **C** | **PageRest / WhiteOS / ThingsOS / AuraReader / Take Easy / Folio Book / Just Read** | 【实证】均为 A 族（除 ThingsOS 是 A/B 混合），驱动层同源；按功能选：PageRest=16 级+可配清残影；WhiteOS=微信读书+词典；ThingsOS=微信读书+Markdown；AuraReader=深度清残影；Take Easy=水波纹；Folio=PDF；Just Read=SD 字体 | 【未知】多为 0.3–0.6 早期版本；AuraReader 还在 alpha |

### 37.3 按诉求直接选

| 你的诉求 | 选 | 理由 |
|---|---|---|
| **要"最好看"（灰阶/渐变/照片）** | **CrossLink** | 全生态唯一做色调曲线 + 误差扩散 |
| **要"翻页爽且稳，能自己调"** | **kiikoread** | 8 带节拍 + 37 相全保留 + 三种刷新模式 + 迭代最活跃 |
| **要"功能多"（微信读书/Markdown/PDF）** | if-ink OS / WhiteOS / ThingsOS / Folio Book | 各自有独占功能 |
| **要"最稳、不折腾"** | 官方 Demo | 厂商基线，改动最少 |
| **要"能改、能学"** | kiikoread（源码+测试最全）或 YanReader（Lua 可脚本化） | 前者可读性最好 |

### 37.4 我判断不了的部分（诚实边界）

以下四项**我没有任何证据**，但它们对"日常用"影响很大：
1. **长期稳定性**（会不会死机/卡死/掉电后丢进度）——release 数量只能反映活跃度，不反映 bug 率；
2. **续航**（同一个波形架构下，差异主要来自刷新策略与休眠实现）；
3. **实际手感**（翻页延迟、触摸/按键响应、菜单层级）；
4. **残影长期表现**（这个必须真机跑几百页）。

要补这四项，最小成本路径是：**读各项目的 release notes / issue 列表**（开源那 6 个可以做），
以及**真机试刷 2–3 个**。需要的话我可以把开源项目的 issue 密度、未修 bug 类型统计出来，
作为"稳定性"的代理指标。

## 38. 生态空白：温度分档波形（EDCBook 唯一的明确领先）

我在 kiikoread 与 if-ink OS 的波形配置里读到了一模一样的注释：

```c
// 温度档 0-50°C。在此固件中没有温度分档的演示。
// / One 0–50°C temp range. This firmware has no multi-range demo.
static const EpdWaveformTempInterval e0470_intervals[] = { { .min = 0, .max = 50 } };
```

而 EDCBook 是 **7 档 × 3 °C 覆盖 0–21 °C**，每档独立相位数：

| 温度档 | 0-3 | 3-6 | 6-9 | 9-12 | 12-15 | 15-18 | 18-21 |
|---|---|---|---|---|---|---|---|
| DU 相位 | 25 | 22 | 22 | 22 | 18 | 17 | **15** |
| GC16 相位 | 46 | 43 | 40 | 38 | 38 | 44 | 57 |

也就是说：**"冷天不糊、热天不慢"这件事，小纸生态目前没人做。**
这是唯一一处 EDCBook 明确领先、且改动面很干净的位置——只需在
`e0470_epaper_waveform.c` 里把 `temp_intervals` 拆档并为每档提供 LUT，上层无需改动。

> 反过来，CrossLink 的"色调曲线 + Floyd–Steinberg 误差扩散"（§32.7）是 EDCBook 没有的，
> 两者恰好互补：**EDCBook 强在"波形随温度"和"字库预烘焙"，CrossLink 强在"面板响应校正 + 抖动 + 刷新控制"**。

## 39. 勘误：本报告第 36 节之前的两个错误判断

1. **"RickyOS 是 SPI + 4 级灰度，做不到 16 级"** —— 错。
   那是它对 Xteink X3/X4、Waveshare 3.97" 等 SPI 机型的分支；
   小纸 Pico 走 `libs/display/FreeInkDisplay/src/driver/EpdiyLcdDriver.cpp` + e0470 波形，是并行 + 16 级。
2. **"官方 Demo 用运行时 TTF 所以排版不如 EDCBook"** —— 对 A 族成立、对 B 族不成立。
   freeink-sdk 编入的是**完整 FreeType**（`afautofit`/`afcjk` 自动 hinting + `GSUB`/`GPOS`），
   排版质量上限**高于** EDCBook 的预烘焙位图。

### 39.1 第三条勘误（针对小纸生态）

3. **"CrossLink 属 B 族（freeink 血统）"** —— 错。这是我从它的刷写器设备表（x3/x4/x4pro/mofeiM4/eegoA4/sticky/nologo397/paperMono/wodle/pico）
   反推出来的，但拿到 16 MB 镜像后发现 `__FILE__` 是 `components/pico/epdiy/src/output_lcd/lcd_driver.c`，
   **是 A 族（epdiy 并行）**。教训：设备表相同只说明"支持同一批机型"，不能反推驱动实现。

4. **"波形可能被各系统改过"** —— 被 §32.2 否定。8 个固件逐字节包含官方 e0470 的 DU/GC16/GL16 LUT，
   无人改动。这也说明我原先猜测的"某些系统可能改波形换画质"不成立。

## 40. 证据索引

| 结论 | 证据位置 |
|---|---|
| 面板 684×1216 / 帧周期 11,090 µs | `components/e0470_epaper_waveform/README.md` |
| 四张波形表与相位数 | 同上（表 + 参数一节） |
| 裁剪器骨架与默认参数 | 同上（Trimmer 一节） |
| 无损跳相实现 | `components/epdiy/src/render.c`（`leading_skip_frames` 等） |
| epdiy fork 的四处改动 | `components/epdiy/README.md` |
| 8 带 / 44 节拍 / 37 相全保留 | `wegooo-cell/read-pico-reader/README.md` |
| 连续 DU 实现与 50 ms 扫描 | `components/continuous_du/README.md` |
| 独立翻页波形组件 | `yiifanrecyclable/if-ink-OS/components/e0470_page_turn/` |
| 单温度档注释 | `…/e0470_epaper_waveform.c` 第 24–27 行（if-ink）、第 59–62 行（kiikoread） |
| freeink-sdk 多驱动 | `libs/display/FreeInkDisplay/src/driver/` |
| 小纸 Pico 的 epdiy 配置 | `libs/hardware/BoardReadPico/src/ReadPicoEpdiyConfig.cpp` |
| 完整 FreeType | `libs/font/FreeInkFont/src/freetype/`（含 `autofit/afcjk.c`） |
| CPYOS 16 灰实验 | `test/absolute_grayscale/`、`test/native_grayscale/gray16.jpg`、`lib/GfxRenderer/GrayCoverage.h` |
| WhiteOS 血统证据 | `firmware/licenses/source/components/{epdiy,e0470_epaper_waveform,continuous_du}/LICENSE` |
| 17 个系统清单与描述 | `MindReset/dot_web_docs/zh-Hans-CN/read_0/start/*.mdx` |
| 闭源固件血统实证 | 镜像 app_desc + `__FILE__` 路径；见 §32.1 表 |
| CrossLink 镜像 | `crosslink-reader.oss-cn-hangzhou.aliyuncs.com/?prefix=firmware/`（桶可列举）→ `firmware/pixel-pico-full.bin-v4.3.1T` |
| Just Read 镜像 | `cdn.xmoa.smn.icu/downloads/models.json` → `mindreset-read-pico-s3/ota/stable/0.3.3/firmware.bin` |
| 波形同一性证据 | 官方 `waveforms/{du,gc16,gl16,gray8_gc16}.h` 的数组体字节，在 8 个固件中各命中 1 次（ThingsOS 2 次） |
| 策略词表 | 各固件中文 UI/日志字符串；CrossLink 见其 104 条 `E/W/I (%lu)` 日志 |
| 波形**配置**（相位数） | 扫 `EpdWaveform`/`EpdWaveformMode`/`EpdWaveformPhases` 结构；脚本 `pico_tools/wf.py` |
| CrossLink 模块布局还原 | 段映射 + l32r 交叉引用后按代码地址排序；脚本 `pico_tools/mimg.py` |
| 闭源血统批量判定 | `pico_tools/lin.py`（app_desc + `__FILE__` 关键路径） |

### 40.1 复现工具（已随报告附带）

`pico_tools/` 下三个脚本，都是纯 Python、无需反汇编器：

| 脚本 | 作用 |
|---|---|
| `lin.py` | 输入任意 Read Pico 固件（合并镜像或 app 分区），输出 app_desc 与"血统标记"命中表 |
| `mimg.py` | 解析合并镜像的段表，建立 vaddr→文件偏移映射，提供 `l32rs()` 交叉引用与中文串提取 |
| `wf.py` | 扫描 `EpdWaveform` 三件套结构，输出每个固件链接的 `{模式: 相位数}` 与温度区间 |
| `callgraph.py` | 依据 `mimg.py` 的段映射，解 `calln`（18 位有符号扩展）并建立函数级调用图；用于还原模块布局与调用链 |

用法：
```bash
python3 pico_tools/lin.py  <firmware.bin>
python3 pico_tools/mimg.py            # 库；被 wf.py 调用
python3 pico_tools/wf.py   <firmware.bin>
python3 pico_tools/callgraph.py   # 库；build(path) -> (img, entries, edges, fn_of_addr)
```
| Take Easy 镜像 | `take-easy.pages.dev/firmware/manifest.json` → `v2.3/firmware.bin` |
| VanOS 镜像 | `vanos.pages.dev/manifest-full.json` → `merged-binary.bin` |
| AuraReader 镜像 | `aurareader.cn/firmware/manifest.json` → `…full-16MB.bin` |
| ThingsOS 镜像 | `thingsos.scholarcn.com/release.json` → `…-usb.bin` |
| Folio Book 镜像 | `esp-flasher…`（sharecode Cookie 后）`firmware/foliobook/FolioBook-full.bin` |
| CrossLink 设备表 | `crosslink-reader.top` chunk `page-0f48…js` 的 `A={…}`；固件基址 OSS `/firmware` |
| Just Read 固件协议 | `flasher.smn.icu` chunk 中 `Lo="/downloads/"` 与 `ota/<ch>/release.json` |

---

# 41. 补充核实：EDCBook 的正文模型是纯文本（不渲染书内图片）

> 起因：验证"EDCBook 快的一个原因是不显示文件里的图片"这个假设。

## 41.1 结论

**假设基本成立，但机制需要修正**：不是"渲染时跳过图片"，而是**导入阶段就把书压成扁平文本**，
图片在进入阅读模型之前就没了。

## 41.2 证据链

| # | 证据 | 位置/原文 | 含义 |
|---|---|---|---|
| 1 | 官方上传提示明确只收 txt | web UI：`"hint":"支持 UTF-8/GBK/UTF-16LE/UTF-16BE/BIG5 编码的 txt 文件。"` | 主路径就是 TXT |
| 2 | 内部中间格式是扁平文本 | `.fbtxt` / `.fbtxt.src` / `chapters.idx` / `.pidx` / `.mpidx` / `.aidx` | 书被"投影"成文本 + 索引，图片无处存放 |
| 3 | **解析器标签表里没有 `img`** | 标签表（FB2/HTML 风格）：`div h1..h6 ul li dl dt dd blockquote table thead tbody tfoot tr caption article aside header footer figure figcaption hr br nav center form fieldset address v subtitle text-author date empty-line image epigraph cite poem stanza annotation span` | 标准 EPUB 的 `<img src>` 属于**未识别标签 → 静默丢弃** |
| 4 | 没有 `src` 属性处理 | `\0src\0` = 0 次；`\0xlink\0` = 0 次；`xlink:href` = 0 次 | 连图片引用都不解析 |
| 5 | 连占位符都不画 | `[图片]` / `[Image]` / `[插图]` / `（图片）` 全为 0 | 说明图片根本不在版式模型里 |
| 6 | 图片能力只出现在"外壳" | 设置键 `lock_cover`、`off_pic`、`online_pic`、`reading_bg`；路径 `.saved/*_o0..o3.cache` | 锁屏/关机/背景/在线图，不是书内 |
| 7 | FB2 的 `<image/>`、`<binary>` 在标签表里 | 解析器表含 `image/`（匹配自闭合形式）与 `binary` | **很可能是为了把 base64 块剔出正文**，而不是为了显示 |

## 41.3 但"解码器是有的"

这点必须说清楚，否则容易误判：

- 内嵌 **20 个 PNG**（签名 20 处，IHDR 尺寸含 480×800、800×480、540×960 等）→ 开机/引导/UI 资源；
- **JPEG 解码存在**：JPEG 的 zigzag 扫描表在镜像里命中 **1 次**（该表只有 JPEG 解码器会用）；
- 所以 `M5GFX` 的 PNG/JPEG 解码是编进去的，但服务于：内嵌资源、用户上传的锁屏/关机/背景图、封面。

## 41.4 为什么这确实让翻页更快（与 CrossLink 对照）

CrossLink 的图片管线（§32.7）每张图都有这些开销，EDCBook **一条都没有**：

```
[JPG] decode → [JPG] %dx%d -> %dx%d (scaleX/scaleY) → [JPG] adaptive tone
→ [GRAYIMG] 误差扩散 用时 %lums → [JPG] plane blit=%lums → [IMG] Cache band
```

但**真正省下的不是解码时间**，而是这三点：

1. **翻页差分面积更小更规整**：纯文本页只有字形像素变，图片页几乎整块变；
2. **不必为灰度图升级波形**：EDCBook 的 24 个 profile 里，
   `NATURAL_GRAY` / `LIGHT_GRAY_CRISP` / `BLACK_CLEAN_GRAY` 就是给灰度内容的；
   它既然不渲染书内图，翻页就能一直走 `LIGHT_TEXT` / `TEXT_FAST`（14–17 步），
   而满波形 GL16/GC16 是 37/46–48 相 —— 按 §20 的 5.5 ms/相算，等于把单次翻页从 ~200 ms 压到 ~80–95 ms；
3. **不需要图片缓存与抖动**：没有 `Cache band`、没有误差扩散、没有 16 级色调校准。

## 41.5 仍未确认的一点

**FB2 的 `<binary>` 到底有没有被解码上屏**，我没有拿到直接证据（需要跟踪图纸管线）。
从"没有图片占位符 + 没有媒体缓存文件 + 中间格式是扁平文本"三点推断，**大概率也是丢弃**。

## 41.6 这对选型意味着什么

如果你要的正是"纯文字、翻页极快"，EDCBook 这条路（纯文本模型 + 少相波形）是最优解。
但小纸生态里**没有一个系统走这条路**——它们在 A 族基线上都保留了图片能力（CrossLink 更是做满了）。
如果你想在小纸 Pico 上复刻 EDCBook 的手感，最有性价比的一步不是改波形，而是：
**在导入时把 EPUB 的 `<img>` 直接剔除（不做解码/抖动/缓存），并把翻页 profile 固定到 14–17 步的文本档。**
