# DASH 协议详解

## DASH 概述

DASH（Dynamic Adaptive Streaming over HTTP，动态自适应 HTTP 流媒体）是由 MPEG 和 3GPP 联合制定的国际标准（ISO/IEC 23009-1），发布于 2012 年。与 HLS 类似，DASH 通过 HTTP 传输切片化的媒体内容，并支持 ABR 自适应码率切换。

DASH 的主要优势：

- **开放标准**：非厂商私有协议，生态更开放
- **灵活的容器格式**：支持 fMP4（推荐）和 MPEG-TS
- **统一 DRM 接口**：通过 Common Encryption（CENC）支持多种 DRM 系统
- **丰富的元数据描述**：MPD 文件可精确描述媒体属性、时间轴、辅助信息

DASH 广泛应用于 YouTube、Netflix、bilibili 等主流视频平台。

---

## MPD 文件结构

MPD（Media Presentation Description）是 DASH 的 XML 格式索引文件，类似于 HLS 的 M3U8。

### 层次结构

```
MPD
└── Period（时间段，可含广告切换）
    └── AdaptationSet（媒体类型：视频/音频/字幕）
        └── Representation（具体码率/分辨率的一路流）
            └── SegmentTemplate / SegmentList / SegmentBase
```

### 核心元素说明

**MPD 根元素属性**：
- `type="static"`：点播（VOD）；`type="dynamic"`：直播
- `mediaPresentationDuration`：总时长（如 `PT1H30M`）
- `minBufferTime`：最小缓冲时间建议
- `maxSegmentDuration`：最大切片时长

**Period**：
- 代表一段连续的时间区间，多 Period 用于广告插入或内容拼接
- `start` 属性标识该 Period 在整个呈现中的起始时间

**AdaptationSet**：
- `mimeType`：媒体类型（`video/mp4`、`audio/mp4`、`text/vtt`）
- `codecs`：编解码器标识（如 `avc1.640028`、`mp4a.40.2`）
- `lang`：音频/字幕语言
- `segmentAlignment="true"`：切片在时间上对齐（ABR 切换保障）

**Representation**：
- `id`：唯一标识
- `bandwidth`：码率（bps）
- `width` / `height`：分辨率（视频）
- `frameRate`：帧率
- `audioSamplingRate`：采样率（音频）

---

## 完整 MPD 示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     type="static"
     mediaPresentationDuration="PT2M30S"
     minBufferTime="PT2S"
     profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">

  <Period id="1" start="PT0S">

    <!-- 视频轨 -->
    <AdaptationSet mimeType="video/mp4"
                   codecs="avc1.640028"
                   segmentAlignment="true"
                   startWithSAP="1">

      <SegmentTemplate timescale="90000"
                       media="video_$RepresentationID$_seg$Number$.m4s"
                       initialization="video_$RepresentationID$_init.mp4"
                       startNumber="1"
                       duration="270000"/>

      <Representation id="360p"  bandwidth="800000"  width="640"  height="360"/>
      <Representation id="720p"  bandwidth="1500000" width="1280" height="720"/>
      <Representation id="1080p" bandwidth="3000000" width="1920" height="1080"/>
    </AdaptationSet>

    <!-- 音频轨 -->
    <AdaptationSet mimeType="audio/mp4"
                   codecs="mp4a.40.2"
                   lang="zh">
      <SegmentTemplate timescale="44100"
                       media="audio_seg$Number$.m4s"
                       initialization="audio_init.mp4"
                       startNumber="1"
                       duration="132300"/>
      <Representation id="audio_128k" bandwidth="128000" audioSamplingRate="44100"/>
    </AdaptationSet>

  </Period>
</MPD>
```

---

## Segment 格式

### fMP4（Fragmented MP4）—— 推荐格式

fMP4 是标准 MP4 的流式扩展，由以下 box 组成：

- **`ftyp`（File Type Box）**：声明文件兼容性
- **`moov`（Movie Box）**：全局元数据，Initialization Segment 中包含
- **`moof`（Movie Fragment Box）**：片段元数据，每个 Media Segment 开头
- **`mdat`（Media Data Box）**：实际媒体数据

DASH 中典型的 Segment 类型：

| Segment | 文件名示例 | 说明 |
|---------|-----------|------|
| Initialization Segment | `video_init.mp4` | 包含 ftyp + moov，播放前必须先获取 |
| Media Segment | `video_seg001.m4s` | 包含 moof + mdat，实际媒体内容 |
| Index Segment | `video_index.sidx` | 可选，记录各 Segment 的字节偏移 |

### MPEG-TS

- DASH 也支持 MPEG-TS 格式（继承自早期实现）
- 兼容性较好，但文件开销大于 fMP4
- 目前主流实现均推荐迁移至 fMP4

---

## DASH vs HLS 详细对比

| 特性 | DASH | HLS |
|------|------|-----|
| 标准化机构 | MPEG/3GPP（ISO 标准） | Apple（IETF RFC 8216） |
| 索引文件格式 | MPD（XML） | M3U8（文本） |
| 媒体容器 | fMP4（推荐）/ TS | TS（传统）/ fMP4（v6+） |
| 浏览器原生支持 | 通过 MSE（Media Source Extensions） | Safari/iOS 原生，其他需 MSE |
| iOS 支持 | 需要第三方播放器或 MSE | 原生支持 |
| 直播延迟 | 2~5s（低延迟 DASH）| 默认 20~45s，LL-HLS 1~3s |
| DRM 支持 | CENC（Widevine + PlayReady + ClearKey） | FairPlay（Apple），需额外配置 |
| ABR 支持 | 原生支持 | 原生支持 |
| 字幕/多音轨 | 完善（AdaptationSet） | 支持（EXT-X-MEDIA） |
| CDN 兼容性 | 标准 HTTP，完全兼容 | 标准 HTTP，完全兼容 |
| 流行度 | YouTube/Netflix/bilibili | Apple 生态、iOS 直播 |

---

## CMAF（Common Media Application Format）

CMAF 由 Apple 和 Microsoft 于 2016 年联合提出，目标是统一 HLS 和 DASH 的媒体容器格式，减少存储和转码成本。

**核心思想**：

- 使用 fMP4 作为统一容器（替代 HLS 的 TS）
- 同一份媒体文件可同时服务 HLS 和 DASH 请求
- 只需一份转码输出，通过不同索引文件（M3U8 / MPD）分发

**存储节省示例**：

```
传统方案：
  HLS 1080p TS 文件 + DASH 1080p fMP4 文件 = 2x 存储

CMAF 方案：
  CMAF fMP4 切片（共用）+ M3U8 索引 + MPD 索引 = 1x 存储 + 2 个索引文件
```

**CMAF 关键规范**：

- 切片格式：fMP4（`.m4s`）
- 编码：H.264/H.265 + AAC
- 加密：CENC（AES-128 CTR 模式），支持 FairPlay、Widevine、PlayReady
- 低延迟支持：CMAF Chunk（子切片），配合 HTTP/2 Server Push 和 LL-HLS/低延迟 DASH

CMAF 已被主流 CDN（Akamai、AWS CloudFront）和转码平台（AWS MediaConvert、FFmpeg）广泛支持。
