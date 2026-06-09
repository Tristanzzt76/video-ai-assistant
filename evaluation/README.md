# RAGAS 评估模块

对比基础RAG（无 Reranker）和加 BGE-Reranker 后的检索增强效果。

## 依赖安装

```bash
pip install ragas datasets langchain-openai
```

## 运行方式

```bash
# 切到项目根目录
cd /path/to/video-ai-assistant

# 只评估基础RAG（无 Reranker）
python evaluation/evaluate.py --mode baseline

# 只评估加 Reranker
python evaluation/evaluate.py --mode rerank

# 两者对比（默认）
python evaluation/evaluate.py --mode compare
python evaluation/evaluate.py
```

需要 `.env` 中配置 `ZHIPU_API_KEY`，且 ChromaDB 已有数据（先运行文档加载）。

## 实际评估结果（2026-06-09）

```
=== RAGAS 评估结果对比 ===

指标                   基础RAG    加Reranker    变化
faithfulness           0.9848     0.9677      -1.7%
context_precision      0.9861     0.9861       0.0%
context_recall         1.0000     0.9722      -2.8%
```

**分析结论**：

整体分数极高（faithfulness 0.98、context_recall 1.0），说明知识库质量高、RAG 流水线运行正常。

Reranker 在当前场景（33 chunks 小知识库）无明显提升，原因：
- 向量检索在小知识库中本身精度已很高（precision 0.99）
- Reranker 将 top-5 压缩到 top-3，反而使 context_recall 从 1.0 降至 0.97
- Reranker 在**大规模知识库**（1000+ chunks）中才能发挥最大价值：初始检索噪声多，精排能显著提升准确率

**扩展实验方向**：扩充知识库到 200+ 文档后重跑评估，预期 Reranker 效果更显著。

## 数据集

`dataset.json` 包含 12 个视频技术问答对，覆盖：
- HLS 协议（M3U8、.ts 切片、ABR 自适应码率）
- H.264 编码（GOP、IDR 帧、CBR/VBR 码率控制）
- DASH 协议（MPD 文件、Segment、与 HLS 区别）
- CDN 分发（边缘节点、回源策略）
- 视频质量（PSNR、SSIM、主观质量 MOS）

## 结果文件

每次运行生成 `evaluation/results_{timestamp}.json`，包含各指标原始分数，可用于横向对比多次实验。
