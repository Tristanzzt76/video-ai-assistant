# 流媒体传输协议全景

## 协议延迟对比

不同协议在延迟、可靠性、适用场景上有显著差异：

| 协议 | 典型延迟 | 传输层 | 主要用途 |
|------|---------|-------|---------|
| WebRTC | < 1s | UDP / DTLS-SRTP | 实时互动（视频会议、连麦） |
| SRT | < 1s | UDP | 贡献链路（制作侧传输） |
| RTMP | 1–3s | TCP | 推流到服务器 |
| LL-HLS | 2–5s | HTTP/2 | 低延迟直播分发 |
| RTSP | 2–5s | TCP/UDP | 监控摄像头、IPTV |
| DASH | 10–30s | HTTP | 点播/自适应流 |
| HLS（标准） | 20–30s | HTTP | 直播/点播分发 |

---

## RTMP（Real-Time Messaging Protocol）

### 基本特性

**RTMP** 由 Macromedia（后被 Adobe 收购）开发，基于 TCP，是互联网直播推流的事实标准协议。

- **端口**：默认 1935（RTMPS 使用 443，通过 TLS 加密）
- **传输层**：TCP，保证有序可靠传输
- **延迟**：1-3 秒
- **容器**：FLV 封装

### 为何仍是推流标准

尽管 Flash Player 已死，RTMP 作为**推流协议**仍被 OBS、直播软件、直播平台广泛使用：

- 协议简单，各平台编码器实现成熟
- 支持实时双向通信（信令 + 媒体复用在同一连接）
- 连接建立快，握手开销低

### 局限性

- **浏览器不原生支持**：现代浏览器已移除 Flash，无法直接播放 RTMP 流，只能作为推流协议
- **不支持 H.265/AV1**：FLV 封装对新编码格式支持有限
- **防火墙穿透性差**：1935 端口常被企业防火墙屏蔽

### 典型工作流

```
OBS 客户端 --[RTMP推流]--> 流媒体服务器（SRS/Nginx-RTMP）
                                    |
                          ┌─────────┴─────────┐
                     HLS 切片              DASH 切片
                    （.m3u8）               （.mpd）
                          |                   |
                    CDN 分发              CDN 分发
                          |                   |
                      观众播放             观众播放
```

---

## WebRTC（Web Real-Time Communication）

### 基本特性

**WebRTC** 是 W3C/IETF 标准化的实时通信框架，浏览器原生支持，无需插件。

- **传输层**：ICE/STUN/TURN + DTLS-SRTP（加密 UDP）
- **延迟**：< 500ms（理想条件下 < 100ms）
- **视频编码**：VP8、VP9、H.264（AV1 逐步支持）
- **音频编码**：Opus（自适应码率，20-510 kbps）

### 核心机制

**ICE（Interactive Connectivity Establishment）**：自动寻找两个对端之间最优网络路径：
1. 优先尝试直连（P2P，局域网内极低延迟）
2. 失败则通过 TURN 服务器中继（服务器中转）

**SDP（Session Description Protocol）**：信令协商媒体能力（分辨率/编码/带宽）

**SRTP**：媒体流全程加密，WebRTC 强制要求

### 典型场景

- 视频会议（Zoom、Google Meet 底层均使用 WebRTC）
- 直播连麦、PK 互动（主播与用户超低延迟互动）
- 在线教育实时互动课堂
- WebRTC CDN 分发（将 RTMP 输入转为 WebRTC 输出，实现 CDN 级低延迟分发）

### 局限性

- P2P 模式在大规模直播（1 对多）中服务器压力大，需 SFU（Selective Forwarding Unit）架构
- 网络质量敏感，弱网下画质/流畅性波动明显
- 服务端实现复杂度高

---

## SRT（Secure Reliable Transport）

### 基本特性

**SRT** 由 Haivision 开发并开源（2017 年），专为**互联网不可靠网络上的低延迟高质量传输**设计。

- **传输层**：基于 UDT（UDP-based Data Transfer），实现可靠传输
- **延迟**：可配置（通常 120-800ms），在丢包环境下通过 ARQ 重传保质量
- **加密**：AES-128/256 内置加密
- **端口**：自定义（通常 9000-9999）

### 核心优势

SRT 在**贡献链路（Contribution）**场景中大放异彩：

- **丢包恢复**：通过 FEC（前向纠错）和 ARQ（自动重传请求）在丢包率 10-30% 的网络下维持低延迟传输
- **自适应缓冲**：根据网络 RTT 动态调整缓冲大小
- **带宽估计**：实时探测可用带宽并调整推流码率

### 典型场景

- 场外 ENG 摄像机通过 4G/5G 回传演播室（替代卫星传输车）
- 跨国直播信号传输（洲际延迟不稳定场景）
- 数据中心之间的视频流中继
- OBS 2020+ 版本已原生支持 SRT 推流

```bash
# FFmpeg SRT 推流示例
ffmpeg -i input.mp4 -c copy "srt://192.168.1.100:9000?pkt_size=1316"

# FFmpeg SRT 接收示例
ffmpeg -i "srt://0.0.0.0:9000?mode=listener" -c copy output.ts
```

---

## QUIC / HTTP/3

### 背景：解决 Head-of-Line Blocking

HTTP/1.1 和 HTTP/2 基于 TCP，TCP 的队头阻塞问题（Head-of-Line Blocking）在丢包时会导致所有流同时卡顿。HTTP/2 虽实现了多路复用，但底层 TCP 的一个包丢失仍会阻塞所有流。

**QUIC** 是 Google 设计的基于 UDP 的新型传输协议，解决了上述问题：

- **多流独立**：每条 QUIC 流独立传输，一条流丢包不影响其他流
- **0-RTT 握手**：复用连接时无需完整 TLS 握手，延迟更低
- **连接迁移**：IP 地址变化（如 4G 切 WiFi）时连接不中断
- **HTTP/3**：基于 QUIC 的 HTTP 协议，正在被各大 CDN 采用

### 对流媒体的影响

- CDN 回源和边缘分发逐步采用 HTTP/3/QUIC
- 弱网（移动端、高丢包）场景下 QUIC 相比 TCP 有明显优势
- 主流 CDN（Cloudflare、Fastly、阿里云 CDN）已支持 HTTP/3

---

## 推流协议 vs 播流协议的分离

现代直播架构将推流和播流协议完全分离：

```
推流端                    流媒体服务器                播放端
┌─────────┐              ┌──────────────┐            ┌─────────┐
│  OBS    │ RTMP/SRT ──> │   Ingest     │            │ 观众    │
│  FFmpeg │              │   Server     │ HLS ──────>│ 播放器  │
│  手机   │              │  (SRS/NIM)   │ DASH ─────>│ Web端   │
└─────────┘              └──────────────┘ WebRTC ──> └─────────┘
```

- **推流**：RTMP / SRT / WebRTC（WHIP 协议）
- **播流**：HLS / DASH / WebRTC（WHEP 协议）/ HTTP-FLV（遗留）

**WHIP（WebRTC-HTTP Ingestion Protocol）** 和 **WHEP（WebRTC-HTTP Egress Protocol）** 是正在标准化的基于 HTTP 的 WebRTC 信令协议，目标是让 WebRTC 推/播流像 HLS 一样简单。

---

## 场景选型建议

| 场景 | 推荐推流 | 推荐播流 |
|------|---------|---------|
| 大众直播（低延迟要求一般） | RTMP | HLS / DASH |
| 游戏/体育实时互动 | RTMP / SRT | LL-HLS / WebRTC |
| 视频会议 | WebRTC | WebRTC |
| 主播连麦/PK | WebRTC（WHIP） | WebRTC（WHEP） |
| 户外 4G 回传 | SRT | HLS |
| 点播 | — | DASH + HLS（fMP4） |
| 监控/安防 | RTSP | RTSP / WebRTC |
