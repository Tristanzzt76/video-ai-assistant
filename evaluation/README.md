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

## 预期输出

```
=== RAGAS 评估结果对比 ===

指标                   基础RAG    加Reranker    提升
faithfulness           0.61       0.79        +29.5%
answer_relevancy       0.73       0.81        +11.0%
context_precision      0.58       0.76        +31.0%
context_recall         0.69       0.74        +7.2%

结果已保存到: evaluation/results_20240610_143022.json
```

## 数据集

`dataset.json` 包含 12 个视频技术问答对，覆盖：
- HLS 协议（M3U8、.ts 切片、ABR 自适应码率）
- H.264 编码（GOP、IDR 帧、CBR/VBR 码率控制）
- DASH 协议（MPD 文件、Segment、与 HLS 区别）
- CDN 分发（边缘节点、回源策略）
- 视频质量（PSNR、SSIM、主观质量 MOS）

## 结果文件

每次运行生成 `evaluation/results_{timestamp}.json`，包含各指标原始分数，可用于横向对比多次实验。
