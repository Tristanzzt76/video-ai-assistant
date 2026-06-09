# Video AI Assistant

A RAG-based Q&A assistant for video technology, built with LangGraph Agent + BGE-M3 local embedding + Claude API. Designed to answer domain-specific questions about HLS/DASH protocols, H.264/H.265 encoding, CDN distribution, and bitrate control with grounded, source-cited responses.

## Why This Project

Generic LLM chatbots hallucinate on niche video engineering questions. This project combines a curated knowledge base with a stateful Agent that decides *how* to answer—retrieval, web search, or direct generation—before doing so.

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────┐
│               FastAPI  (port 8000)               │
│    POST /api/v1/chat                             │
└───────────────────┬─────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│          LangGraph State Machine                  │
│                                                   │
│  ┌──────────┐    rag ──▶ ┌──────────────────┐   │
│  │  router  │────web ──▶ │    tool_node      │   │
│  │  (LLM)   │            │  rag_search /     │   │
│  └──────────┘            │  web_search       │   │
│       │                  └────────┬─────────┘   │
│    direct                         │              │
│       │           ┌───────────────┘              │
│       ▼           ▼                              │
│  ┌─────────────────────┐                         │
│  │    generate_node     │                         │
│  │   (Claude API)       │                         │
│  └─────────────────────┘                         │
└────────────────────┬────────────────────────────┘
                     │
         ┌───────────┴────────────┐
         ▼                        ▼
┌─────────────────┐    ┌─────────────────────────┐
│  ChromaDB       │    │   Claude claude-sonnet-  │
│  (local)        │    │   4-6  (remote API)      │
│                 │    └─────────────────────────┘
│ BGE-M3 embed    │
│ (local infer)   │
│ BGE-Reranker    │
│ (local infer)   │
└─────────────────┘
         │
         ▼
┌──────────────────┐
│  Next.js 14      │
│  (port 3000)     │
└──────────────────┘
```

**Data flow for a RAG request:**

1. `router_node` calls Claude to classify the query → `rag / web / direct`
2. `tool_node` calls `rag_search`: BGE-M3 encodes the query → ChromaDB cosine search (top-5) → BGE-Reranker rescores and prunes to top-3
3. `generate_node` calls Claude with retrieved chunks as context → final answer with source attribution

## Technology Choices

### LangGraph over LangChain LCEL

LangChain LCEL chains execute linearly and require explicit branching via `RunnableBranch`. LangGraph models execution as a typed state machine with nodes and conditional edges, which maps naturally to the routing logic here (classify → maybe retrieve → generate). Adding a new tool (e.g., SQL lookup) only requires a new node and a new branch in `route_condition`—no chain refactoring. The `AgentState` TypedDict also makes intermediate state inspectable and testable.

### BGE-M3 Local vs. Embedding API

BGE-M3 (`BAAI/bge-m3`) runs entirely on-device via `sentence-transformers`:

- **No API latency or cost** for embedding at query time or during bulk document ingestion
- **Domain alignment**: BGE-M3 is trained on diverse multilingual corpora including technical Chinese/English text, making it a better fit for mixed-language video engineering documentation than OpenAI `text-embedding-ada-002`
- **Trade-off**: first load takes 10–30 s and consumes ~1.5 GB RAM; mitigated by pre-loading on FastAPI startup (`lifespan`)

### Claude API for Generation

Claude handles both routing classification and final answer generation. The router prompt is deliberately constrained to return only `rag/web/direct` to minimize token usage for the classification step (~100 input tokens per request).

## Features

- **Agent routing**: LLM-based query classifier routes to RAG, Tavily web search, or direct generation
- **Hybrid retrieval**: BGE-M3 vector search (ChromaDB, cosine similarity) → BGE-Reranker two-stage re-scoring
- **Document ingestion**: Upload PDF, Markdown, or plain text; LlamaIndex `SentenceSplitter(chunk_size=512, overlap=50)` chunking
- **Session context**: `AgentState.messages` accumulates conversation history across turns
- **RAGAS evaluation**: automated pipeline to measure faithfulness, answer relevancy, context precision, and context recall
- **Graceful degradation**: reranker load failure falls back to raw vector scores; router default is `rag`

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-username/video-ai-assistant.git
cd video-ai-assistant

# 2. Configure environment
cp .env.example .env
# Edit .env — required keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   TAVILY_API_KEY=tvly-...   (optional, for web search)

# 3. Install Python dependencies (Python 3.11+ recommended)
pip install -r requirements.txt

# 4. Start backend (BGE-M3 loads on first startup, ~30 s)
make dev-backend
# → http://localhost:8000/docs  (Swagger UI)

# 5. Start frontend (new terminal)
cd frontend && npm install
make dev-frontend
# → http://localhost:3000
```

**Docker (alternative):**

```bash
make build && make up
```

## Project Structure

```
video-ai-assistant/
├── app.py                  # FastAPI entry point, lifespan pre-loads BGE-M3
├── requirements.txt
├── Makefile
├── docker-compose.yml
├── src/
│   ├── config.py           # Pydantic Settings, reads .env
│   ├── agent/
│   │   ├── graph.py        # LangGraph StateGraph definition
│   │   ├── state.py        # AgentState TypedDict
│   │   └── tools.py        # rag_search / web_search @tool definitions
│   ├── rag/
│   │   ├── loader.py       # DocumentLoader (SentenceSplitter)
│   │   ├── embedder.py     # BGEEmbedder singleton (BAAI/bge-m3)
│   │   └── retriever.py    # ChromaRetriever + BGE-Reranker
│   ├── models/
│   │   └── schemas.py      # Pydantic request/response models
│   └── api/
│       └── routes.py       # FastAPI route handlers
├── frontend/               # Next.js 14 chat UI
├── evaluation/             # RAGAS evaluation scripts
├── data/
│   ├── docs/               # Uploaded source documents
│   └── chroma/             # Persisted ChromaDB vector store
└── tests/
```

## RAGAS Evaluation

[RAGAS](https://docs.ragas.io/) measures RAG pipeline quality without human labels by using an LLM-as-judge approach.

**Run evaluation:**

```bash
cd evaluation
python run_eval.py   # reads evaluation/testset.json, writes results to evaluation/results.json
```

**Metrics:**

| Metric | What it measures |
|--------|-----------------|
| `faithfulness` | Are all claims in the answer supported by the retrieved context? (hallucination detector) |
| `answer_relevancy` | Does the answer actually address the question? |
| `context_precision` | Are the retrieved chunks relevant to the question? |
| `context_recall` | Does the retrieved context cover all information needed to answer? |

Scores range from 0 to 1. A production-grade RAG system typically targets faithfulness > 0.85 and answer_relevancy > 0.80.

## Roadmap

| Week | Goal |
|------|------|
| 1-2 | Core RAG pipeline: document ingestion, BGE-M3 embedding, ChromaDB storage, basic retrieval |
| 3-4 | LangGraph Agent: router node, tool nodes, generate node, FastAPI integration |
| 5   | BGE-Reranker two-stage retrieval, session history, web search fallback |
| 6   | Next.js 14 frontend, streaming response support |
| 7   | RAGAS evaluation pipeline, testset construction, metric baseline |
| 8   | Docker packaging, performance profiling, README polish |
