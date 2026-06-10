# 视频转码技术详解

## 转码 vs 传码（Transcoding vs Transmuxing）

**转码（Transcoding）** 是将视频从一种编码格式重新编码为另一种格式的过程，需要完整的解码 → 处理 → 重新编码流程，计算开销大。例如将 H.264 视频转为 H.265，或将 1080P 降档为 720P。

**传码（Transmuxing）** 也称为封装转换，仅改变容器格式，不重新编码媒体流。例如将 MP4 中的 H.264 流重新封装为 TS 片段（HLS 场景），视频质量无损，速度远快于转码（通常快 10-50 倍）。

| 操作 | 是否重新编码 | 质量损失 | 速度 | 典型场景 |
|------|-------------|---------|------|---------|
| 转码 | 是 | 有（有损） | 慢 | 分辨率/码率转换、格式兼容 |
| 传码 | 否 | 无 | 极快 | MP4 → fMP4/TS、HLS 切片 |

---

## 转码流水线

完整的转码流水线分为三个阶段：

### 1. 输入解码（Demux + Decode）

- **解封装（Demux）**：从容器格式（MP4/MKV/FLV）中分离音频流和视频流
- **解码（Decode）**：将压缩的码流（H.264/H.265/VP9）还原为原始 YUV/PCM 帧

### 2. 滤镜处理（Filter）

在原始帧上进行各种处理：

- **缩放（Scale）**：1080P → 720P / 480P
- **裁剪（Crop）**：去除黑边、竖屏裁横屏
- **叠加（Overlay）**：水印、字幕烧录
- **帧率转换（FPS）**：60fps → 30fps 抽帧
- **色彩空间转换**：BT.601 ↔ BT.709、SDR → HDR Tone Mapping

### 3. 编码输出（Encode + Mux）

- **编码（Encode）**：将原始帧压缩为目标编码格式
- **封装（Mux）**：将音视频流写入目标容器格式

---

## 关键转码参数

### 分辨率（Resolution）

常见档位：4K（3840×2160）、1080P（1920×1080）、720P（1280×720）、540P（960×540）、480P（854×480）、360P（640×360）

转码时应保持宽高比（DAR/SAR），避免画面拉伸变形。

### 帧率（Frame Rate）

- 标准：23.976fps、25fps、29.97fps、30fps、60fps
- 直播通常用 25/30fps，体育/游戏内容可用 60fps
- 降帧率（60→30）可显著降低码率

### 码率（Bitrate）

- **CBR（恒定码率）**：直播传输首选，方便带宽规划
- **VBR（可变码率）**：点播首选，复杂场景多分配码率，静止场景少用，整体质量更高
- **CRF（恒定质量因子）**：x264/x265 中的质量模式，值越小质量越高（x264 推荐 18-28，x265 推荐 24-32）

### 主流编码器对比

| 编码器 | 标准 | 压缩效率 | 编码速度 | 硬件支持 | 适用场景 |
|--------|------|---------|---------|---------|---------|
| x264 | H.264/AVC | 基准 | 快 | 极广 | 兼容性优先 |
| x265 | H.265/HEVC | +40% | 中 | 较广 | 4K/高质量存储 |
| VP9 | VP9 | +30% | 慢 | 一般 | YouTube/Web |
| AV1 | AV1 | +50% | 极慢（软件）| 增长中 | 新一代流媒体 |
| libsvtav1 | AV1 | +50% | 中（优化版） | Intel ARC | AV1 实用编码 |

---

## 转码预设（Preset）：速度 vs 质量权衡

x264/x265 提供预设选项，在相同 CRF 下控制编码速度和压缩效率的权衡：

```
ultrafast → superfast → veryfast → faster → fast → medium → slow → slower → veryslow
```

- **更慢的预设**：编码时间更长，但输出文件更小（压缩效率更高）
- **更快的预设**：适合实时/直播场景，但文件稍大
- **推荐**：点播 VOD 用 `slow` 或 `medium`，直播用 `veryfast` 或 `superfast`

```bash
# 点播高质量转码
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset slow -c:a aac -b:a 128k output.mp4

# 直播实时转码（快速）
ffmpeg -i rtmp://source -c:v libx264 -crf 28 -preset veryfast -tune zerolatency output.flv
```

---

## 硬件加速

软件编码（CPU）质量最佳但速度慢，硬件编码大幅提升速度，代价是质量略低。

### NVIDIA NVENC

```bash
# H.264 NVENC 编码
ffmpeg -i input.mp4 -c:v h264_nvenc -preset p4 -cq 23 output.mp4

# H.265 NVENC 编码
ffmpeg -i input.mp4 -c:v hevc_nvenc -preset p4 -cq 28 output.mp4
```

### Intel QuickSync

```bash
ffmpeg -i input.mp4 -c:v h264_qsv -global_quality 23 output.mp4
```

### Apple VideoToolbox（Apple Silicon M 系列）

Apple Silicon 的 Media Engine 提供硬件 H.264/H.265/ProRes 编解码：

```bash
# macOS VideoToolbox H.264
ffmpeg -i input.mp4 -c:v h264_videotoolbox -b:v 4000k output.mp4

# macOS VideoToolbox H.265（HEVC）
ffmpeg -i input.mp4 -c:v hevc_videotoolbox -b:v 2500k output.mp4
```

**性能对比**（1080P H.264，相对速度）：
- CPU (x264 slow)：1x
- CPU (x264 veryfast)：5-8x
- NVENC：15-30x
- VideoToolbox：20-40x

---

## 音视频同步（AV Sync）问题

音视频同步是转码中的常见问题，主要原因：

1. **时间戳不连续**：源文件存在跳变的 PTS/DTS，转码后偏移累积
2. **音频重采样误差**：采样率转换（44100 → 48000）时浮点精度丢失
3. **B 帧延迟**：编码器 B 帧 lookahead 引入额外延迟

**排查和修复**：

```bash
# 修复时间戳（-vsync cfr 强制恒定帧率，-async 1 修复音频同步）
ffmpeg -i input.mp4 -vsync cfr -async 1 -c:v libx264 -c:a aac output.mp4

# 手动添加音频延迟（单位：秒，正值延迟音频）
ffmpeg -i input.mp4 -itsoffset 0.5 -i input.mp4 -map 0:v -map 1:a -c copy output.mp4
```

---

## 点播转码 vs 直播转码

| 维度 | 点播（VOD）转码 | 直播转码 |
|------|--------------|---------|
| 实时性要求 | 无（离线处理） | 极高（延迟 <2s） |
| 编码预设 | slow/medium（质量优先） | veryfast/superfast（速度优先） |
| 码率模式 | VBR/CRF（质量恒定） | CBR（带宽可控） |
| 并发方式 | 批量队列，可弹性扩缩容 | 实时流，不可中断 |
| 错误处理 | 失败可重试 | 丢帧继续，不能停止 |
| 多码率 | 离线生成多分辨率 Ladder | 实时多路编码（消耗高） |
| 关键帧 | 灵活，按场景切换 | 固定 GOP（2s/4s），保证切片对齐 |

---

## FFmpeg 常用命令参考

```bash
# 基础格式转换
ffmpeg -i input.mp4 output.avi

# 视频转码：H.264 → H.265，降低码率
ffmpeg -i input.mp4 -c:v libx265 -crf 28 -c:a copy output.mp4

# 分辨率缩放（保持宽高比，宽度缩至 1280）
ffmpeg -i input.mp4 -vf scale=1280:-2 -c:v libx264 -crf 23 output.mp4

# 提取视频流（不含音频）
ffmpeg -i input.mp4 -an -c:v copy video_only.mp4

# HLS 切片（fMP4 格式）
ffmpeg -i input.mp4 -c:v libx264 -c:a aac \
  -f hls -hls_time 6 -hls_segment_type fmp4 \
  -hls_playlist_type vod output.m3u8

# 多码率转码（720P + 480P 同时输出）
ffmpeg -i input.mp4 \
  -c:v libx264 -crf 23 -vf scale=1280:720 output_720p.mp4 \
  -c:v libx264 -crf 25 -vf scale=854:480 output_480p.mp4

# 查看视频信息
ffprobe -v quiet -print_format json -show_streams input.mp4
```
