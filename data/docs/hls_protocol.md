# HLS 协议详解

## 概述

HLS（HTTP Live Streaming）是由 Apple 于 2009 年开发并提出的基于 HTTP 的自适应流媒体传输协议，最初用于 iOS 设备上的视频直播与点播。协议规范由 IETF 以 RFC 8216 正式发布。

HLS 的核心思想是将媒体流切分为若干小片段（通常为 2~10 秒），通过标准 HTTP 协议传输，客户端根据网络状况动态选择合适的码率。由于基于 HTTP，HLS 天然穿越防火墙，且可利用现有 CDN 基础设施进行大规模分发。

---

## M3U8 文件格式详解

M3U8 是 HLS 的索引文件，本质是 UTF-8 编码的 M3U 播放列表，分为两类：

### 主播放列表（Master Playlist）

用于描述多个不同码率/分辨率的媒体流，供客户端进行 ABR 选择。

关键标签：

- `#EXTM3U`：文件标识，必须位于第一行
- `#EXT-X-VERSION:<n>`：协议版本号，常见值为 3、6、7
- `#EXT-X-STREAM-INF:BANDWIDTH=<bps>,RESOLUTION=<WxH>,CODECS="..."`：描述一路子流的属性，紧跟子流 URI

### 媒体播放列表（Media Playlist）

描述具体一路流的切片列表。

关键标签：

- `#EXT-X-VERSION:<n>`：协议版本
- `#EXT-X-TARGETDURATION:<s>`：所有切片中最大时长（秒），客户端据此决定刷新间隔
- `#EXTINF:<duration>[,<title>]`：紧跟的切片时长（秒），精确到小数
- `#EXT-X-MEDIA-SEQUENCE:<n>`：当前播放列表中第一个切片的序列号
- `#EXT-X-ENDLIST`：标志 VOD 播放列表结束，直播列表中不出现此标签
- `#EXT-X-KEY:METHOD=AES-128,URI="...",IV=...`：加密信息
- `#EXT-X-DISCONTINUITY`：片段间存在不连续性（如广告插入后恢复）

---

## 完整 M3U8 示例

### 主播放列表（master.m3u8）

```
#EXTM3U
#EXT-X-VERSION:3

#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.42c01e,mp4a.40.2"
360p/index.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=1400000,RESOLUTION=1280x720,CODECS="avc1.4d401f,mp4a.40.2"
720p/index.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2"
1080p/index.m3u8
```

### 媒体播放列表（720p/index.m3u8）

```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:0

#EXTINF:5.880,
seg0.ts
#EXTINF:6.000,
seg1.ts
#EXTINF:5.960,
seg2.ts
#EXTINF:6.000,
seg3.ts

#EXT-X-ENDLIST
```

---

## .ts 片段（Transport Stream）

HLS 传统上使用 MPEG-2 Transport Stream（`.ts`）作为媒体容器。TS 是为数字广播设计的容器格式，具有以下特点：

- **固定包大小**：每个 TS 包 188 字节，便于同步
- **多路复用**：一个 TS 流可携带多个 PID（Program ID），分别承载视频、音频、字幕
- **随机访问**：每个切片以 IDR 帧开始，支持独立解码
- **容错性强**：即使丢包也能继续播放后续包

HLS 协议版本 6 及以后，也支持使用 fMP4（Fragmented MP4）替代 TS 作为容器，与 DASH 互通性更好。

---

## ABR 自适应码率

HLS 的 ABR（Adaptive Bitrate）机制允许客户端根据实时网络状况，在多路不同码率的流之间动态切换：

1. **上行感知**：客户端周期性测量下载速度
2. **切换策略**：
   - 网络变差 → 切换到低码率流（降级）
   - 网络好转 → 切换到高码率流（升级）
3. **缓冲安全**：切换时机通常结合当前缓冲时长，避免过于激进的切换导致卡顿
4. **无缝切换**：每路流在相同时间点的切片边界对齐（GOP 对齐），切换时不需要重新缓冲

常见 ABR 算法：基于吞吐量、基于缓冲区（BBA）、以及两者结合的混合算法（如 Netflix BOLA）。

---

## GOP 对齐原则

在 HLS 多码率流中，所有码率的切片边界必须在时间上对齐，且每个切片必须以 IDR（关键帧）开头。

**原因**：

- IDR 帧可独立解码，不依赖前后帧
- 若切换时当前码率的切片边界与目标码率不对齐，播放器必须等待下一个对齐点，导致延迟

**实践**：

- 编码时设置固定 GOP 大小（如 2 秒）
- 切片时长设为 GOP 时长的整数倍
- 多路流使用相同帧率和 GOP 结构，确保时间轴精确对齐

---

## 延迟特性

| 模式 | 典型延迟 | 说明 |
|------|----------|------|
| 标准 HLS | 20~45 秒 | 默认切片 6s + 3 个切片缓冲 |
| 低延迟优化 | 8~15 秒 | 减小切片时长至 2s |
| LL-HLS（Low-Latency HLS） | 1~3 秒 | Apple HLS 扩展，支持部分切片（Partial Segments）和 HTTP/2 Push |

**LL-HLS 关键特性**：

- `#EXT-X-PART`：发布切片的局部片段，无需等待整个切片完成
- `#EXT-X-SERVER-CONTROL`：服务端控制推送和阻塞加载行为
- Blocking Playlist Reload：客户端发起带 `_HLS_msn` 参数的请求，服务端在新切片可用前阻塞响应

---

## HLS vs RTMP 对比

| 特性 | HLS | RTMP |
|------|-----|------|
| 传输协议 | HTTP/HTTPS | TCP 自定义协议 |
| 延迟 | 默认 20~45s，LL-HLS 1~3s | 1~3 秒 |
| 防火墙穿越 | 天然支持（HTTP 80/443） | 常被防火墙拦截（1935 端口） |
| CDN 支持 | 完善，标准 HTTP 缓存 | 需专用 CDN 支持 |
| 移动端兼容性 | iOS/Android 原生支持 | 需 Flash 或特殊播放器 |
| ABR 支持 | 原生支持 | 不支持 |
| 使用场景 | 点播、直播分发 | 推流（OBS → 直播平台） |
| DRM | 支持 AES-128、FairPlay | 支持 RTMPE |

**典型链路**：推流端使用 RTMP 推流到流媒体服务器（如 Nginx-RTMP），服务器将 RTMP 流转封装为 HLS 输出，再经 CDN 分发给播放端。
