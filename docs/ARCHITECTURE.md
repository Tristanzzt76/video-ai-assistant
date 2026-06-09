# Architecture

## LangGraph State Machine

### State Definition

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # conversation history
    query: str                                             # current user question
    retrieved_chunks: list[str]                           # tool output
    sources: list[str]                                    # "rag" | "web"
    route: Literal["rag", "web", "direct"]                # routing decision
    answer: str                                           # final response
    session_id: str
```

### Nodes

#### `router_node`

Invokes Claude with a tightly scoped system prompt that returns exactly one token: `rag`, `web`, or `direct`. Using the LLM for routing (rather than regex/keyword matching) handles paraphrased and multilingual inputs correctly. The prompt explicitly lists the domains that should route to `rag` (HLS/DASH/RTMP, H.264/H.265/AV1, CDN, GOP, ABR…), `web` (real-time/news queries), and `direct` (greetings, no retrieval needed).

Fallback: any unexpected response defaults to `"rag"` to avoid skipping retrieval on domain questions.

#### `tool_node`

Dispatches to the appropriate `@tool` based on `state["route"]`:

- `rag_search(query)` — calls `ChromaRetriever.search()` → returns formatted string of top-3 reranked chunks with source and relevance score
- `web_search(query)` — calls Tavily API → returns top-3 result titles, URLs, and snippets
- `direct` — skips tool execution entirely, returns empty chunks

Result is stored as `retrieved_chunks: list[str]`.

#### `generate_node`

Builds the prompt:

- If `retrieved_chunks` is non-empty: prepends `"参考以下资料回答问题：\n\n{context}\n\n问题：{query}"`
- Otherwise: sends the raw query

Calls Claude with the system prompt (domain expert persona + citation rules) and accumulated `messages` for multi-turn context. Appends the response to `messages` for the next turn.

### Graph Topology

```
START
  │
  ▼
router ──(direct)──────────────────────▶ generate ──▶ END
  │
  └──(rag / web)──▶ tool ──▶ generate ──▶ END
```

**Conditional edge** (`route_condition`):

```python
def route_condition(state: AgentState) -> Literal["tool", "generate"]:
    return "generate" if state.get("route") == "direct" else "tool"
```

### Why LangGraph Over if/else

A plain `if/else` dispatcher works for a static two-branch pipeline. LangGraph adds:

1. **Typed state propagation** — every node receives and returns the full `AgentState`, making intermediate values inspectable without side effects or global mutation.
2. **Graph visualization** — `graph.get_graph().draw_mermaid()` renders the topology automatically, useful for documentation and debugging.
3. **Incremental extensibility** — adding a new tool (e.g., SQL lookup for structured data) requires adding one node and one branch in `route_condition`. A chained if/else approach requires restructuring call sites.
4. **Built-in interrupt/resume** — LangGraph supports `interrupt_before` for human-in-the-loop approval without reimplementing async checkpointing.

The overhead for a three-node graph is negligible; the structural benefits pay off as complexity grows.

---

## RAG Pipeline

### Document Processing

**Loader**: LlamaIndex `SimpleDirectoryReader` handles PDF (via `pypdf`) and Markdown. Each file is passed to `SentenceSplitter(chunk_size=512, chunk_overlap=50)`.

**Chunk size rationale (512 tokens)**:

- Video engineering documentation tends to have dense, self-contained paragraphs (protocol specs, algorithm descriptions). 512 tokens captures a full concept without truncating mid-sentence.
- Too large (1024+): retrieval becomes noisy—one chunk covers multiple concepts, and cosine similarity averages across all of them.
- Too small (128): loses the surrounding context that makes a chunk independently answerable; also increases ChromaDB collection size quadratically.

**Overlap (50 tokens)**: Prevents boundary artifacts where a key sentence is split across two chunks. 50 tokens (~3-4 sentences) is sufficient to maintain continuity without duplicating significant content.

### Embedding: BGE-M3 Local Inference

`BGEEmbedder` wraps `sentence-transformers` `SentenceTransformer("BAAI/bge-m3")` as a singleton pre-loaded at FastAPI startup.

**Trade-off analysis:**

| Dimension | BGE-M3 local | OpenAI text-embedding-ada-002 (API) |
|-----------|-------------|-------------------------------------|
| Latency (batch 32) | ~80 ms (CPU) / ~15 ms (GPU) | ~200-400 ms (network RTT) |
| Cost | 0 (after hardware) | $0.0001 / 1K tokens |
| Multilingual | Strong (trained on 100+ languages) | Good |
| Chinese/English mix | Excellent | Moderate |
| Offline capability | Yes | No |
| Cold start | ~20 s (model load) | None |

For a video tech knowledge base with mixed Chinese/English content (protocol specs often have English terms with Chinese explanations), BGE-M3's multilingual training provides better semantic alignment than ada-002.

Embeddings are L2-normalized (`normalize_embeddings=True`), enabling cosine similarity via dot product—which ChromaDB's `hnsw:space=cosine` collection computes directly.

### Retrieval: Two-Stage Pipeline

```
query
  │
  ▼ encode_query()
query vector (1024-dim)
  │
  ▼ ChromaDB cosine search
top-5 candidate chunks  (vector similarity stage)
  │
  ▼ BGE-Reranker.compute_score(pairs, normalize=True)
rescored chunks
  │
  ▼ sort by reranker score, return top-3
final context
```

**Stage 1 — Vector retrieval (top-5):**

ChromaDB HNSW index retrieves the 5 nearest neighbors by cosine distance. This stage is fast (~5 ms) but operates on compressed semantic representations—similar-sounding but semantically different phrases can score highly.

**Stage 2 — BGE-Reranker (top-3):**

`FlagReranker("BAAI/bge-reranker-base")` takes `(query, chunk)` pairs and produces cross-attention relevance scores (0–1 after normalization). Cross-encoders consider the full token interaction between query and candidate—much more accurate than bi-encoder cosine similarity, but too slow to run over the entire corpus. Running it over 5 candidates adds ~30–50 ms on CPU.

Fallback: if `FlagReranker` fails to load (missing `FlagEmbedding` library or OOM), the pipeline returns the raw vector-similarity ranking with a `WARNING` log.

---

## Hybrid Architecture: Local + Remote

```
Local machine                         Remote
┌────────────────────────┐           ┌──────────────────┐
│ BGE-M3  (embedding)    │           │  Claude API      │
│ BGE-Reranker           │           │  (router +       │
│ ChromaDB               │           │   generator)     │
│ FastAPI + LangGraph    │──HTTPS───▶│                  │
│ Next.js                │           └──────────────────┘
└────────────────────────┘
```

All embedding and retrieval runs locally—no document content is sent to external services during ingestion or retrieval. Only the query + retrieved chunks (already chunked, anonymized text) are sent to the Claude API for generation.

This matters for:
- **Proprietary documentation**: internal specs or internal wikis never leave the local environment
- **Cost**: embedding 10,000 chunks at 512 tokens each is ~5M tokens; at $0.0001/1K that is $0.50 as a one-time cost with API, versus $0 locally for every re-ingestion
- **Latency**: removes one network hop in the retrieval path

---

## RAGAS Evaluation

RAGAS evaluates RAG quality by generating an LLM-judged score for each metric on a held-out question set, without requiring human-labeled ground-truth answers for every question.

### Metrics

**Faithfulness**: Decomposes the answer into atomic claims, then asks an LLM whether each claim is supported by the retrieved context. Score = `supported claims / total claims`. Directly measures hallucination rate.

**Answer Relevancy**: Generates synthetic questions from the answer, then measures how similar they are to the original question (via embedding cosine similarity). Answers that address the question score high; answers that drift off-topic or add unnecessary content score lower.

**Context Precision**: Measures whether the retrieved chunks that are actually useful appear early in the ranking. A perfect score means all and only the useful chunks were retrieved at the top.

**Context Recall**: Given a ground-truth answer, measures what fraction of the required information was present in the retrieved context. Requires a reference answer in the test set.

### Testset Format

```json
[
  {
    "question": "HLS 的分片时长如何影响直播延迟？",
    "ground_truth": "分片时长越短，直播延迟越低，但服务端产生的分片文件数越多，CDN 回源压力越大。典型值为 2-6 秒。",
    "contexts": []  // filled automatically by the eval script
  }
]
```

### Running Evaluation

```bash
cd evaluation
python run_eval.py \
  --testset testset.json \
  --output results.json \
  --top-k 5
```

The script:
1. Loads each question from `testset.json`
2. Runs the full LangGraph pipeline (router → retrieval → generate)
3. Collects `retrieved_chunks` and `answer` from `AgentState`
4. Passes `(question, answer, contexts, ground_truth)` to `ragas.evaluate()`
5. Writes per-question scores and aggregate metrics to `results.json`
