# RAGAS 评估模块

三组对比：基础向量检索 vs 向量+Reranker vs 混合检索（BM25+向量+RRF+Reranker）。

## 依赖安装

```bash
pip install ragas datasets langchain-openai rank-bm25 jieba
```

## 运行方式

```bash
cd /path/to/video-ai-assistant

python evaluation/evaluate.py --mode compare_all   # 三组完整对比（默认）
python evaluation/evaluate.py --mode baseline       # 仅基础向量
python evaluation/evaluate.py --mode rerank         # 仅向量+Reranker
python evaluation/evaluate.py --mode hybrid         # 仅混合检索
python evaluation/evaluate.py --mode compare        # 基础 vs Reranker 两组
```

需要 `.env` 中配置 `ZHIPU_API_KEY`，且 ChromaDB 已有数据（先运行文档加载）。

## 评估结果（2026-06-10）

```
=== RAGAS 三组对比（基础向量 vs +Reranker vs 混合检索）===

指标               基础向量    向量+Reranker    混合检索    混合提升
faithfulness       0.8860      0.9808          0.9851    +11.2%
context_precision  0.9861      0.9861          0.9861      0.0%
context_recall     1.0000      0.9722          0.9722     -2.8%
```

**核心结论**：

混合检索（BM25 + 向量 + RRF + Reranker）使 **faithfulness 提升 11.2%**（0.886 → 0.985）：
- BM25 擅长精确词汇匹配（如 `M3U8`、`GOP`、`PSNR` 等专有名词）
- 向量检索擅长语义理解（同义表达、上下文语义）
- RRF 融合两者排名，召回更全面的上下文
- 结果：LLM 生成的回答更忠实于检索内容，减少幻觉

context_recall 略降（1.0 → 0.97）是 Reranker 将 top-5 压缩到 top-3 的合理代价。

## 数据集

`dataset.json` 包含 12 个视频技术问答对，覆盖：
- HLS 协议（M3U8、.ts 切片、ABR 自适应码率）
- H.264 编码（GOP、IDR 帧、CBR/VBR 码率控制）
- DASH 协议（MPD 文件、Segment、与 HLS 区别）
- CDN 分发（边缘节点、回源策略）
- 视频质量（PSNR、SSIM、主观质量 MOS）

## 结果文件

每次运行生成 `evaluation/results_{timestamp}.json`，包含各指标原始分数，可用于横向对比多次实验。
