# Video AI Assistant

![Python 3.11](https://img.shields.io/badge/Python-3.11-blue?logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green?logo=fastapi) ![LangGraph](https://img.shields.io/badge/LangGraph-0.1-orange) ![License MIT](https://img.shields.io/badge/License-MIT-yellow)

视频技术领域 RAG + LangGraph Agent 问答系统。混合检索（BM25 + 向量）相比基础向量检索使 **faithfulness +11.2%**，达到 0.985。

## RAGAS 评估结果

| 指标 | 基础向量 | +Reranker | 混合检索 | 提升 |
|------|---------|-----------|---------|------|
| faithfulness | 0.886 | 0.981 | 0.985 | **+11.2%** |
| context_precision | 0.986 | 0.986 | 0.986 | 0.0% |
| context_recall | 1.000 | 0.972 | 0.972 | -2.8% |

## 系统架构

```
用户问题
  ↓ Query 改写（GLM-4-Flash）
  ↓ 混合检索
  ├── BM25 检索（精确词汇）
  └── 向量检索（语义相似，BGE-M3）
  ↓ RRF 融合
  ↓ BGE-Reranker 精排
  ↓ LangGraph Agent（路由：RAG/Web/Direct）
  ↓ GLM-4-Flash 生成回答
  ↓ SSE 流式返回前端
```

## 技术选型

| 技术 | 选用原因 |
|------|---------|
| **LangGraph** vs LangChain LCEL | 状态机模型天然适合"路由→检索→生成"的复杂对话流程，新增工具只加节点和边，无需重构链 |
| **BGE-M3 本地推理** vs Embedding API | 数据不出本地，推理延迟可控（~0.1s），中英文混合技术文档效果优于 `text-embedding-ada-002` |
| **BM25 + 向量混合检索** | M3U8、GOP、HLS 等专有名词靠 BM25 精确召回，语义理解靠向量检索，两者互补 |
| **GLM-4-Flash** | 永久免费 API，中文理解强，视频技术领域表现稳定 |

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/your-username/video-ai-assistant.git
cd video-ai-assistant

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入：ZHIPUAI_API_KEY=xxx  TAVILY_API_KEY=xxx（可选）

# 3. 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 4. 启动后端（首次启动加载 BGE-M3 约 30s）
make dev-backend
# → http://localhost:8000/docs

# 5. 启动前端（新终端）
cd frontend && npm install && make dev-frontend
# → http://localhost:3000
```

## 项目结构

```
video-ai-assistant/
├── app.py                  # FastAPI 入口，预加载 BGE-M3
├── requirements.txt
├── src/
│   ├── agent/
│   │   ├── graph.py        # LangGraph StateGraph 定义
│   │   ├── state.py        # AgentState TypedDict
│   │   └── tools.py        # rag_search / web_search 工具
│   ├── rag/
│   │   ├── embedder.py     # BGEEmbedder（BAAI/bge-m3）
│   │   ├── retriever.py    # 混合检索 + BGE-Reranker 精排
│   │   └── bm25.py         # BM25 + jieba 分词
│   └── api/
│       └── routes.py       # SSE 流式接口
├── evaluation/             # RAGAS 评估脚本
├── data/
│   ├── docs/               # 原始文档
│   └── chroma/             # ChromaDB 向量库
└── frontend/               # Next.js 14 聊天界面
```

## 评估方法

使用 [RAGAS](https://docs.ragas.io/) 框架，基于 LLM-as-judge 方法自动评估 RAG 流水线质量，无需人工标注。评估集（`evaluation/testset.json`）包含视频技术领域问题，覆盖 HLS 协议、H.265 编码、CDN 分发、码率控制等子领域。三组对比实验分别在基础向量检索、加 Reranker、加 BM25 混合检索配置下运行，复现方式：

```bash
cd evaluation && python run_eval.py
```

## License

MIT
