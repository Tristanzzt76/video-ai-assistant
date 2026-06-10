# 视频容器格式详解

## 容器格式的作用

视频容器格式（Container Format）是一种文件封装规范，负责将**视频流、音频流、字幕、章节信息、元数据**等多种媒体轨道组织打包到同一个文件中，并定义：

- **轨道索引**：记录各轨道的位置、时长、时间戳
- **时间同步**：维护音视频同步所需的 PTS（Presentation Timestamp）和 DTS（Decode Timestamp）
- **随机访问**：索引表（moov atom / index）支持 seek 跳转
- **元数据**：编码器信息、创建时间、版权等

容器格式本身**不负责压缩**，压缩工作由编码格式（Codec）完成。

---

## 容器格式 vs 编码格式

这是初学者最容易混淆的概念：

| 层次 | 例子 | 作用 |
|------|------|------|
| 容器格式 | .mp4、.mkv、.webm、.ts | 封装、组织多路媒体数据 |
| 视频编码格式 | H.264、H.265、VP9、AV1 | 视频帧压缩算法 |
| 音频编码格式 | AAC、MP3、Opus、AC-3 | 音频样本压缩算法 |

一个 `.mp4` 文件可以包含 H.264 视频 + AAC 音频，也可以包含 H.265 视频 + AC-3 音频。容器和编码是正交的，但并非任意组合都被广泛支持。

---

## 主流容器格式详解

### MP4 / fMP4（MPEG-4 Part 14）

**MP4** 是目前最广泛使用的视频容器格式，基于 Apple QuickTime（.mov）演化而来。

- **编码兼容**：H.264、H.265、AAC、MP3、AC-3
- **优点**：兼容性极佳，几乎所有设备和浏览器原生支持
- **缺点**：标准 MP4 的 `moov atom`（索引）在文件末尾，需完整下载才能播放

**fMP4（Fragmented MP4）** 是 MP4 的流式变体，将媒体数据切分为独立的 Fragment（片段），每个 Fragment 自包含：

- 支持**边下边播**，无需预先知道文件总长度
- 是 **DASH 和现代 HLS** 的标准片段格式（CMAF 规范）
- `moov atom` 仅包含轨道描述，具体数据在各 Fragment 的 `moof` + `mdat` 中

### TS（MPEG-2 Transport Stream）

**TS** 是 MPEG-2 定义的流式传输容器，最初为数字广播电视设计。

- **结构**：固定 188 字节的 Packet，具有强大的**容错性**（单包损坏不影响整体）
- **HLS 传统格式**：HLS 1.0 规范使用 TS 作为片段格式（`.ts` 文件）
- **优点**：广播和直播领域成熟稳定，解码器支持广泛
- **缺点**：188 字节对齐开销约 10%，不支持 H.265 以外的现代编码（WebM/AV1 无法封装），无法跨流复用（每个流独立 TS）

### MKV（Matroska）

**MKV** 是完全开放的容器格式，设计目标是支持尽可能多的音视频轨道和特性。

- **编码兼容**：几乎所有视频/音频编码，包括 H.264、H.265、AV1、VP9、Opus、FLAC
- **特色功能**：
  - 支持无限数量的音轨、字幕轨、章节
  - 支持软字幕（ASS/SSA/SRT 格式）
  - 支持 HDR 元数据（HDR10、Dolby Vision）
- **局限**：浏览器原生播放支持有限，主要用于本地存储和 PC 播放器（VLC、MPC-HC）

### WebM

**WebM** 是 Google 主导的开源容器格式，基于 MKV 简化而来，专为 Web 浏览器设计。

- **强绑定编码**：VP8/VP9（视频）+ Vorbis/Opus（音频）；AV1 + Opus
- **浏览器支持**：Chrome/Firefox 原生支持，Safari 支持有限
- **开源免版税**：VP9/AV1 均无专利授权费，适合互联网公司大规模部署
- YouTube 使用 WebM/VP9 作为主力格式

### FLV（Flash Video）

**FLV** 是 Adobe 为 Flash Player 设计的历史格式。

- **现状**：已基本淘汰。Flash Player 于 2020 年底停止支持
- **遗留场景**：部分 RTMP 推流协议仍使用 FLV 封装（直播推流），服务端收到后立即转为 HLS/DASH 分发
- **局限**：不支持 H.265，不支持 HDR，文件索引结构简单

---

## 封装与解封装

**封装（Mux / Multiplex）**：将多路编码后的媒体流合并写入容器文件
```
[H.264 视频流] + [AAC 音频流] → MP4 封装 → output.mp4
```

**解封装（Demux / Demultiplex）**：从容器中分离各路媒体流
```
input.mp4 → 解封装 → [H.264 视频流] + [AAC 音频流]
```

FFmpeg 中的 `-c copy` 参数即为传码（仅换容器，不重新编码）：

```bash
# MKV → MP4（仅重新封装，不重新编码）
ffmpeg -i input.mkv -c copy output.mp4

# MP4 → fMP4（切片，为 DASH/HLS 准备）
ffmpeg -i input.mp4 -c copy -f mp4 -movflags frag_keyframe+empty_moov output.fmp4
```

---

## TS vs fMP4 在 HLS 中的选择

HLS 协议历史上使用 TS 格式切片，Apple 在 2016 年的 HLS 规范更新（WWDC 2016）中引入了 fMP4 支持：

| 维度 | TS 片段 | fMP4 片段 |
|------|--------|----------|
| HLS 规范版本 | 传统，HLS v1+ | 现代，HLS v7+（需 iOS 10+ / macOS 10.12+） |
| H.265/HEVC 支持 | 支持 | 支持 |
| AV1 支持 | 不支持 | 支持 |
| 存储开销 | 约 10% 封装开销 | 更低（无 188B 对齐限制） |
| 跨协议复用 | 不可与 DASH 复用 | **可与 DASH 共用片段（CMAF）** |
| 设备兼容性 | 极广（老设备） | 主流设备均支持 |

**CMAF（Common Media Application Format）** 是基于 fMP4 的统一规范，目标是让 HLS 和 DASH 共用同一套切片文件，减少存储和转码成本：

```
同一个 fMP4 片段
  ├── HLS 播放列表（.m3u8）引用
  └── DASH 播放列表（.mpd）引用
```

现代点播平台（Netflix、YouTube、Bilibili）均已迁移至 fMP4/CMAF。

---

## 格式选型建议

| 场景 | 推荐格式 |
|------|---------|
| 点播流媒体（HLS/DASH） | fMP4（CMAF） |
| 传统 HLS 兼容性优先 | TS |
| 本地存储/高质量归档 | MKV |
| Web 开源/Google 生态 | WebM（VP9/AV1） |
| 通用下载分发 | MP4（H.264 + AAC） |
| 直播推流（RTMP） | FLV（遗留）/ TS |
