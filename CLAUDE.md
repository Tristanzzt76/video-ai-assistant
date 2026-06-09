# 视频技术 AI 问答助手

## 项目定位
秋招 sideproject，面向视频技术领域的 RAG + LangGraph Agent 问答系统。
目标：LangGraph Agent 自主路由（RAG vs Web Search）+ RAGAS 量化评估改进过程。

## 技术栈
- Python 3.11 + FastAPI + uvicorn
- LangGraph（Agent 编排核心）
- LlamaIndex（文档处理 + RAG Pipeline）
- ChromaDB（本地向量数据库）
- BGE-M3（本地 Embedding，sentence-transformers / FlagEmbedding 加载）
- BGE-Reranker（本地精排）
- Claude API claude-sonnet-4-6（LLM 生成，远端）
- Next.js 14 + TypeScript + Tailwind + shadcn/ui（前端）
- RAGAS（评估）
- Docker Compose

## 目录结构
```
video-ai-assistant/
├── src/
│   ├── api/          # FastAPI 路由层
│   ├── rag/          # RAG Pipeline（loader/embedder/retriever）
│   ├── agent/        # LangGraph 状态机（state/tools/graph）
│   ├── models/       # Pydantic schemas
│   └── config.py     # 配置（pydantic-settings 读取 .env）
├── frontend/         # Next.js 14
│   ├── app/
│   │   ├── page.tsx          # 对话页
│   │   └── upload/page.tsx   # 上传页
│   ├── components/
│   │   ├── ChatWindow.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── UploadZone.tsx
│   │   └── Navbar.tsx
│   └── lib/api.ts            # 后端 API 调用封装
├── docs/
│   ├── ARCHITECTURE.md
│   └── API.md
├── data/
│   ├── docs/         # 原始文档（PDF/Markdown）
│   └── chroma/       # ChromaDB 持久化存储
├── evaluation/
│   ├── dataset.json  # RAGAS 测试集
│   └── evaluate.py   # RAGAS 评估脚本
├── tests/
├── README.md
├── .env.example
├── requirements.txt
├── Makefile
└── docker-compose.yml
```

## 代码规范
- 全部类型注解（Python typing / TypeScript）
- 不写无意义注释，只写 why 不明显的地方
- 每个函数单一职责
- 外部 API 调用（Claude/ChromaDB）加 try/except，内部逻辑不加
- 配置全部走 .env，不硬编码任何 key 或路径

## 环境变量（.env）
```
ANTHROPIC_API_KEY=           # Claude API key
EMBEDDING_MODEL=local        # "local" 或 "api"
LLM_PROVIDER=claude          # "claude" 或 "openai"
CHROMA_PATH=./data/chroma
DOCS_PATH=./data/docs
CORS_ORIGINS=http://localhost:3000
TAVILY_API_KEY=              # Web 搜索（可选）
```

## LangGraph 状态机设计
节点：
- `router`：判断问题能否从知识库回答，决定走 rag_search 还是 web_search
- `tool_node`：执行选中的 Tool（rag_search / web_search）
- `generate`：调用 Claude API 生成最终回答

边：
- START → router → (条件边) → tool_node → generate → END
- router 也可直接 → generate（无需检索的问候等）

## 开发约定
- 每个模块实现完立即 `git commit`
- 骨架阶段：函数写好签名 + docstring，实现可以是 `raise NotImplementedError`
- 实现阶段：单模块逐个填充，实现完跑对应测试再 commit
- 不要在骨架阶段就做完整实现，先跑通 import 再填充逻辑
