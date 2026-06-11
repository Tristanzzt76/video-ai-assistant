# 核心代码解读：视频技术 AI 问答助手

> 面试代码讲解文档，覆盖 AgentState、LangGraph 状态机、混合检索、BGE-M3 Embedding、RAGAS 评估五个核心模块。

---

## 模块 1：AgentState 设计（state.py）

```python
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """LangGraph 状态：贯穿整个 Agent 执行流的数据容器。"""
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    retrieved_chunks: list[str]
    sources: list[str]
    route: Literal["rag", "web", "direct"]
    answer: str
    session_id: str
```

**逐行解释**：

- 第 1-4 行：导入 `TypedDict`（类型安全字典基类）、`Annotated`（带元数据的类型注解）、`add_messages`（LangGraph 内置的消息列表 reducer）、`BaseMessage`（LangChain 消息基类）。
- 第 6 行：`class AgentState(TypedDict)` — 继承 `TypedDict` 而非普通 `dict`。普通 dict 没有字段约束，访问不存在的 key 只在运行时报错；`TypedDict` 在静态分析（mypy/Pylance）阶段就能检测到字段拼写错误，IDE 也能提供自动补全。
- 第 8 行：`messages: Annotated[list[BaseMessage], add_messages]` — `Annotated` 的第二个参数 `add_messages` 是 LangGraph 的 **reducer**。LangGraph 在合并多个节点输出时，对于普通字段会直接覆盖，而带有 `add_messages` reducer 的字段会执行**追加**而非覆盖，保证多轮对话历史不被清空。
- 第 9 行：`query: str` — 当前处理的用户问题，经过 `rewrite_query_node` 改写后会被替换为语义增强版本。
- 第 10-11 行：`retrieved_chunks` 存储检索到的文档文本片段，`sources` 存储对应来源标识（`"rag"` 或 `"web"`）。两个字段分离的原因：RAGAS 评估需要单独拿到 `contexts` 列表，源标识则用于前端展示"参考来源"角标，职责不同故分开。
- 第 12 行：`route: Literal["rag", "web", "direct"]` — `Literal` 类型将字段值限定为三个枚举字符串，其他值在静态检查时报错。这避免了拼写错误导致路由失效，比 `str` 类型更安全。
- 第 13-14 行：`answer` 存最终生成的回答，`session_id` 用于多用户并发时区分会话上下文。

**面试话术**：

> 这个 `AgentState` 是整个 Agent 流水线的数据载体，用 `TypedDict` 而不是普通 dict，是为了让 IDE 有静态类型检查，防止字段拼写错误。最关键的设计是 `messages` 字段用了 `Annotated` 加上 `add_messages` 这个 reducer——LangGraph 节点返回 state 片段时，普通字段是覆盖，而这个字段是追加，这样多轮对话历史才不会丢失。`route` 用 `Literal` 约束枚举值，`retrieved_chunks` 和 `sources` 分开存是因为评估框架和前端对这两份数据有不同消费方式。

---

## 模块 2：LangGraph 状态机（graph.py）

### 2.1 rewrite_query_node

```python
def rewrite_query_node(state: AgentState) -> AgentState:
    """对用户 query 做语义改写，提升检索精度。"""
    query = state["query"]
    # 简短问候不改写
    if len(query) < 10 or any(w in query for w in ["你好", "hello", "hi", "谢谢", "感谢"]):
        return state
    try:
        llm = _get_llm()
        response = llm.invoke([HumanMessage(content=REWRITE_PROMPT.format(query=query))])
        rewritten = response.content.strip()
        if rewritten and rewritten != query:
            logger.info(f"Query 改写: '{query}' → '{rewritten}'")
            return {**state, "query": rewritten}
    except Exception as e:
        logger.warning(f"Query 改写失败，使用原始 query: {e}")
    return state
```

**逐行解释**：

- 第 4-5 行：短问候跳过改写的防御逻辑。长度 < 10 或包含问候词时直接返回原 state，避免把"你好"改写成无意义的检索语句，也节省一次 LLM 调用。
- 第 7-8 行：用 `REWRITE_PROMPT` 模板构造 prompt，`{query}` 占位符替换为实际问题，通过 `llm.invoke` 同步调用 LLM 得到改写结果。
- 第 9-12 行：`rewritten != query` 检查防止 LLM 原样返回时触发无效更新。`{**state, "query": rewritten}` 是 Python 字典展开语法，保留所有原有字段并只替换 `query`，符合 LangGraph "节点返回 state 片段" 的惯例。
- 第 13-14 行：LLM 调用失败时降级返回原始 state，不抛异常，保证流水线不中断。

### 2.2 router_node

```python
def router_node(state: AgentState) -> AgentState:
    """判断 query 路由到哪个 Tool 或直接生成。"""
    llm = _get_llm()
    query = state["query"]
    response = llm.invoke([
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=query),
    ])
    route = response.content.strip().lower()
    if route not in ("rag", "web", "direct"):
        route = "rag"  # 降级到 RAG
    logger.info(f"路由决策: {route}，query={query[:50]}")
    return {**state, "route": route}
```

**逐行解释**：

- 第 5-8 行：`SystemMessage` 放 ROUTER_PROMPT（分类指令），`HumanMessage` 放用户问题。系统消息和用户消息分离是 Chat 模型的标准用法，让模型清楚哪部分是指令、哪部分是输入。
- 第 9 行：`.strip().lower()` 处理 LLM 可能输出的多余空格或大写。
- 第 10-11 行：`route not in ("rag", "web", "direct")` 的降级逻辑——当 LLM 输出格外内容（如"我认为应该用rag"）时，强制降级到 RAG，保证后续条件边能正常分支，而不是遇到未知值崩溃。

### 2.3 route_condition 与 build_graph

```python
def route_condition(state: AgentState) -> Literal["tool", "generate"]:
    """条件边：direct 路由跳过 tool_node 直接生成。"""
    return "generate" if state.get("route") == "direct" else "tool"


def build_graph():
    """构建并编译 LangGraph 状态机。"""
    graph = StateGraph(AgentState)
    graph.add_node("rewrite", rewrite_query_node)
    graph.add_node("router", router_node)
    graph.add_node("tool", tool_node_func)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "rewrite")
    graph.add_edge("rewrite", "router")
    graph.add_conditional_edges("router", route_condition, {"tool": "tool", "generate": "generate"})
    graph.add_edge("tool", "generate")
    graph.add_edge("generate", END)

    return graph.compile()
```

**逐行解释**：

- `route_condition` 函数：这是 LangGraph 的**条件边函数**，返回值必须是 `add_conditional_edges` 第三个参数（映射字典）中的 key。`"direct"` 时返回 `"generate"` 直接生成，其余路由走 `"tool"` 先检索再生成。
- `StateGraph(AgentState)`：声明状态机，绑定 state schema，后续节点的输入输出都须与 `AgentState` 的字段对应。
- `add_node`：注册节点，第一个参数是节点名（在图中唯一），第二个参数是处理函数。
- `add_edge(START, "rewrite")`：显式声明入口，`START` 是 LangGraph 内置的虚拟起始节点。
- `add_conditional_edges("router", route_condition, {...})`：从 `router` 节点出发，调用 `route_condition` 得到字符串 key，再按映射字典跳转对应节点。这是 LangGraph 实现多路分支的核心 API。
- 最终图结构：`START → rewrite → router → (条件) → tool → generate → END`，`direct` 路由时 tool 节点被跳过。
- `graph.compile()`：将声明式图结构编译为可执行的 `CompiledGraph`，此后可调用 `.invoke` / `.astream`。

### 2.4 stream_graph 异步生成器

```python
async def stream_graph(query: str, session_id: str = "default"):
    """异步流式生成，yield token 字符串。"""
    # ... 前三个节点同步执行 ...
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield f"data: {json.dumps({'type': 'token', 'content': chunk.content}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
```

**逐行解释**：

- `async def` + `yield`：这是 Python 的**异步生成器**。调用方用 `async for` 消费，每次 `yield` 立即把 token 推送给前端，无需等待全部生成完毕。
- `llm.astream(messages)`：与 `llm.invoke` 的区别在于 `astream` 是异步流式接口，LLM 每生成一个 token 就 yield 一个 chunk，而 `invoke` 是阻塞等待全部结果。`astream` 降低了首字节延迟（TTFT），用户看到第一个字的时间更短。
- `f"data: {json.dumps(...)}\n\n"`：遵循 SSE（Server-Sent Events）协议格式，每条消息以 `data:` 开头，双换行结尾，前端 `EventSource` API 可直接解析。
- `ensure_ascii=False`：JSON 序列化时保留中文字符，避免中文被转义为 `\uXXXX`。

**面试话术**：

> `build_graph` 这段是 LangGraph 的声明式图构建，核心是 `add_conditional_edges`——路由节点结束后调用 `route_condition` 函数，根据返回值跳转不同节点，实现了"问候直接回答、视频技术走 RAG 检索、实时信息走网络搜索"三路分支。`stream_graph` 用异步生成器加 `llm.astream` 实现流式输出，每来一个 token 就通过 SSE 推给前端，而不是等全文生成完再返回，这样用户感知到的响应速度快很多。

---

## 模块 3：混合检索实现（retriever.py）

### 3.1 _get_bm25 懒加载

```python
def _get_bm25(self):
    """懒加载 BM25 索引（从 ChromaDB 全量拉取文本构建）。"""
    if self._bm25 is not None:
        return self._bm25
    try:
        import jieba
        from rank_bm25 import BM25Okapi
        all_docs = self.collection.get(include=["documents", "metadatas"])  # ids 默认返回
        texts = all_docs.get("documents") or []
        if not texts:
            return None
        # 中文分词 + 英文空格切分
        tokenized = [list(jieba.cut(t)) for t in texts]
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_docs = texts
        self._bm25_ids = all_docs.get("ids") or []
        self._bm25_meta = all_docs.get("metadatas") or []
        logger.info(f"BM25 索引构建完成，共 {len(texts)} 个文档")
    except Exception as e:
        logger.warning(f"BM25 索引构建失败: {e}")
        return None
    return self._bm25
```

**逐行解释**：

- 第 3 行：懒加载模式——`_bm25` 不为 None 说明已构建，直接返回缓存，避免重复从 ChromaDB 拉全量数据。
- 第 8 行：`collection.get(include=["documents", "metadatas"])` 从 ChromaDB 一次性拉取所有文档文本和元数据（ids 默认包含在返回中）。BM25 是内存倒排索引，必须持有全量文本才能构建，无法像向量检索一样只查 top-k。
- 第 12 行：`[list(jieba.cut(t)) for t in texts]` — jieba 对中文进行分词，将连续汉字切分为词语列表（如"视频切片"→`["视频", "切片"]`）。BM25Okapi 的输入是分词后的 token 列表，不能直接接受原始字符串。
- 第 13 行：`BM25Okapi(tokenized)` 构建 BM25 索引，内部计算每个词的 IDF（逆文档频率）权重。
- 新文档写入时（`add_documents`），`self._bm25 = None` 使缓存失效，下次调用时重建索引，保证 BM25 索引与 ChromaDB 数据同步。

### 3.2 hybrid_search（核心方法）

```python
def hybrid_search(
    self,
    query: str,
    top_k: int = 5,
    rrf_k: int = 60,
    rerank: bool = True,
    rerank_top_k: int = 3,
) -> list[RetrievedChunk]:
    """混合检索：BM25 + 向量检索，RRF 融合后可选 Reranker 精排。"""
    import jieba

    # 1. 向量检索
    vector_chunks = self.search(query, top_k=top_k, rerank=False)

    # 2. BM25 检索
    bm25 = self._get_bm25()
    bm25_chunks = []
    if bm25 is not None:
        try:
            tokens = list(jieba.cut(query))
            scores = bm25.get_scores(tokens)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            for rank, idx in enumerate(top_indices):
                if scores[idx] > 0:
                    bm25_chunks.append(RetrievedChunk(
                        text=self._bm25_docs[idx],
                        source=self._bm25_meta[idx].get("source", "unknown") if self._bm25_meta else "unknown",
                        score=scores[idx],
                        metadata=self._bm25_meta[idx] if self._bm25_meta else {},
                    ))
        except Exception as e:
            logger.warning(f"BM25 检索失败，降级到纯向量检索: {e}")

    if not bm25_chunks:
        return self.search(query, top_k=top_k, rerank=rerank, rerank_top_k=rerank_top_k)

    # 3. RRF 融合
    scores_map: dict[str, float] = {}
    text_map: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_chunks):
        key = chunk.text[:100]
        scores_map[key] = scores_map.get(key, 0) + 1 / (rrf_k + rank + 1)
        text_map[key] = chunk

    for rank, chunk in enumerate(bm25_chunks):
        key = chunk.text[:100]
        scores_map[key] = scores_map.get(key, 0) + 1 / (rrf_k + rank + 1)
        text_map[key] = chunk

    merged = sorted(
        [text_map[k] for k in scores_map],
        key=lambda c: scores_map[c.text[:100]],
        reverse=True,
    )[:top_k]

    for chunk in merged:
        chunk.score = scores_map[chunk.text[:100]]

    if not rerank:
        return merged

    # 4. Reranker 精排
    reranker = self._get_reranker()
    if reranker is None:
        return merged
    try:
        pairs = [[query, c.text] for c in merged]
        rerank_scores = reranker.predict(pairs)
        for chunk, s in zip(merged, rerank_scores):
            chunk.score = float(s)
        merged.sort(key=lambda c: c.score, reverse=True)
        return merged[:rerank_top_k]
    except Exception as e:
        logger.warning(f"Reranker 精排失败: {e}")
        return merged
```

**逐行解释**：

- **第一步（向量检索）**：`self.search(query, top_k=top_k, rerank=False)` — 调用 ChromaDB 向量相似度检索，`rerank=False` 跳过内部精排，因为后续 RRF 融合后统一再精排一次。
- **第二步（BM25 检索）**：
  - `bm25.get_scores(tokens)` — 对所有文档计算 BM25 分数，返回长度等于语料库大小的 float 数组。
  - `sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]` — 取分数最高的 top_k 个文档的**下标**，而不是分数本身，因为 `_bm25_docs` 需要用下标索引。
  - `if scores[idx] > 0` — 过滤掉 BM25 分数为 0 的文档（query 词一个都没命中的文档），避免引入无关噪声。
- **降级逻辑**：`if not bm25_chunks: return self.search(...)` — BM25 构建失败或全部分数为 0 时，降级回纯向量检索，保证接口不返回空结果。
- **第三步（RRF 融合）**：
  - `key = chunk.text[:100]`：用文本前 100 个字符作为文档唯一标识（chunk 在两个检索结果中可能都出现，需要去重合并分数）。
  - `1 / (rrf_k + rank + 1)`：这是 **Reciprocal Rank Fusion** 公式的核心。`rrf_k=60` 是平滑常数（防止第 1 名分数过于悬殊），`rank` 从 0 开始。同一文档在向量检索和 BM25 中的 RRF 分数相加，两个检索都排名靠前的文档会获得更高的融合分数。这个公式比直接加权相加的好处是：它只关注排名，不关注原始分数的量纲差异（向量相似度是 0-1，BM25 分数是任意正数，无法直接加权）。
  - `merged = sorted(...)[:top_k]`：按融合分数降序取 top_k，得到混合检索候选集。
- **第四步（CrossEncoder 精排）**：
  - `pairs = [[query, c.text] for c in merged]`：将 query 和每个候选文档拼成 pair 对，CrossEncoder 会对每个 pair 独立打分（而非 Bi-Encoder 的向量内积），精度更高但速度慢，所以只对 top_k 个候选做精排。
  - `reranker.predict(pairs)`：返回 raw logit 分数（非概率，可正可负），分数越高越相关。
  - 最终返回 `merged[:rerank_top_k]`（默认 top 3），给 LLM 生成时的上下文窗口控制 token 数。

**面试话术**：

> `hybrid_search` 分四步走：向量检索用语义相似度，BM25 检索用关键词匹配，两路各取 top-5。合并时用 RRF 公式 `1/(60+rank+1)` 对两路结果按排名打分再累加，这个公式的优势是不用管原始分数的量纲——向量相似度和 BM25 分数根本没法直接加权，但排名是可比的。最后用 CrossEncoder Reranker 对合并后的候选做精排，CrossEncoder 每次把 query 和文档拼在一起过一遍模型，比向量内积精度高，但只对少量候选做，性能可接受。整个流程还有两处降级：BM25 失败时退回纯向量，Reranker 失败时保留 RRF 结果。

---

## 模块 4：BGE-M3 Embedding（embedder.py）

```python
class BGEEmbedder:
    """BGE-M3 本地 Embedding，单例模式，应用启动时预加载。"""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, model_name: str = "BAAI/bge-m3") -> None:
        """加载模型（应在 FastAPI startup 事件中调用）。"""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载 Embedding 模型: {model_name}（首次加载约 10-30s）")
            self._model = SentenceTransformer(model_name)
            logger.info("Embedding 模型加载完成")
        except Exception as e:
            logger.error(f"加载 Embedding 模型失败: {e}")
            raise

    def encode(self, texts: Union[str, list[str]], batch_size: int = 32) -> np.ndarray:
        """将文本编码为向量。单个字符串或字符串列表均可。"""
        if self._model is None:
            raise RuntimeError("模型未加载，请先调用 load()")
        if isinstance(texts, str):
            texts = [texts]
        return self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # 归一化，适合余弦相似度
        )

    def encode_query(self, query: str) -> np.ndarray:
        """编码单个 query，返回 1D 向量。"""
        return self.encode(query)[0]


@lru_cache(maxsize=1)
def get_embedder():
    import os
    if os.getenv("EMBEDDING_MODEL", "local").lower() == "api":
        return ZhipuAPIEmbedder()
    return BGEEmbedder()
```

**逐行解释**：

- 第 4-5 行：`_instance` 和 `_model` 是**类变量**（不是实例变量），所有实例共享。这是实现单例的基础。
- 第 7-10 行：`__new__` 是 Python 创建对象的钩子，在 `__init__` 之前执行。`if cls._instance is None` 保证全局只创建一个实例，后续所有 `BGEEmbedder()` 调用都返回同一个对象。这样避免了 BGE-M3 模型（约 4.3GB）被重复加载进显存/内存。
- 第 13-14 行：`load()` 里的 `if self._model is not None: return` 是**幂等保护**，无论调用多少次，模型只加载一次。`load()` 被设计为在 FastAPI startup 事件中主动调用，而不是等第一次请求时懒加载，避免第一个请求响应超时。
- 第 28-29 行：`if isinstance(texts, str): texts = [texts]` — 统一入参格式，让 `encode` 同时支持单字符串和列表，调用方不需要手动包装列表。
- 第 33 行：`normalize_embeddings=True` — 对输出向量做 L2 归一化（每个向量长度变为 1）。ChromaDB 使用余弦相似度（`hnsw:space: cosine`）计算距离，数学上等价于归一化后的内积。归一化后内积计算更快，且避免向量模长差异影响相似度结果。
- 第 36-37 行：`encode_query` 是对 `encode` 的薄封装，返回 `[0]` 取第一个（也是唯一一个）向量，得到 1D ndarray，与 ChromaDB 的 `query_embeddings` 接口对齐。
- 第 40-41 行：`@lru_cache(maxsize=1)` 是函数级缓存，`get_embedder()` 第一次调用时创建实例，之后永远返回缓存的同一个对象。`maxsize=1` 表示只缓存一个调用结果（无参函数只有一种调用），与单例模式形成双保险。

**面试话术**：

> `BGEEmbedder` 用 `__new__` 实现单例，原因是 BGE-M3 模型有几个 GB，如果每次请求都重新加载，内存会炸。`__new__` 是 Python 创建对象之前的钩子，在这里判断 `_instance` 是否为空，保证全局只有一个实例。`normalize_embeddings=True` 是为了配合余弦相似度——余弦相似度本质上是归一化内积，提前归一化后 ChromaDB 的距离计算更快。`get_embedder()` 外面再加一层 `lru_cache` 是函数级别的缓存，和单例共同保证模型只加载一次。

---

## 模块 5：RAGAS 评估（evaluate.py）

### 5.1 retrieve_contexts 三种模式

```python
def retrieve_contexts(retriever: ChromaRetriever, question: str, mode: str = "baseline") -> list[str]:
    """调用检索器，mode: baseline=纯向量, rerank=向量+Reranker, hybrid=混合检索+Reranker。"""
    if mode == "hybrid":
        chunks = retriever.hybrid_search(query=question, top_k=5, rerank=True, rerank_top_k=3)
    elif mode == "rerank":
        chunks = retriever.search(query=question, top_k=5, rerank=True, rerank_top_k=3)
    else:  # baseline
        chunks = retriever.search(query=question, top_k=5, rerank=False)
    return [chunk.text for chunk in chunks] if chunks else [""]
```

**逐行解释**：

- `baseline` 模式：`search(rerank=False)` — 纯向量检索，top-5，无任何后处理，作为对照基准。
- `rerank` 模式：`search(rerank=True)` — 向量检索 + CrossEncoder 精排，控制变量实验，单独验证 Reranker 的增益。
- `hybrid` 模式：`hybrid_search(rerank=True)` — 混合检索（向量 + BM25 + RRF 融合）再精排，验证混合检索是否优于纯向量。
- 最后一行：`[chunk.text for chunk in chunks] if chunks else [""]` — 提取纯文本列表，RAGAS 的 `contexts` 字段要求 `list[str]`；空列表时返回 `[""]` 防止 RAGAS 报类型错误。

### 5.2 build_ragas_dataset

```python
def build_ragas_dataset(
    samples: list[dict],
    retriever: ChromaRetriever,
    mode: str = "baseline",
) -> Dataset:
    """对每个 sample 做检索 + 生成，返回 RAGAS 格式的 Dataset。mode: baseline/rerank/hybrid"""
    questions, answers, contexts_list, ground_truths = [], [], [], []

    for i, sample in enumerate(samples):
        q = sample["question"]
        gt = sample["ground_truth"]
        print(f"  [{i+1}/{len(samples)}] {q[:40]}...")

        ctxs = retrieve_contexts(retriever, q, mode=mode)
        ans = generate_answer(q, ctxs)

        questions.append(q)
        answers.append(ans)
        contexts_list.append(ctxs)
        ground_truths.append(gt)

    return Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    })
```

**逐行解释**：

- 第 7 行：四个列表分别收集，最后一次性构建 Dataset，比逐行 append 到 DataFrame 更高效。
- 第 9-15 行：遍历每个样本，先检索上下文，再调用 `generate_answer` 让 LLM 基于上下文生成回答。这模拟了真实 RAG 流水线的完整链路，确保评估的是端到端效果而非单纯检索质量。
- 第 21-26 行：`Dataset.from_dict({...})` — HuggingFace `datasets` 库的构建方式，四个字段是 RAGAS 框架的**硬性要求**：
  - `question`：原始问题（用于 faithfulness/precision 评估）
  - `answer`：RAG 生成的答案（用于 faithfulness 评估）
  - `contexts`：检索到的文档片段列表（用于 context_precision/recall 评估）
  - `ground_truth`：标注的参考答案（用于 context_recall 评估）

### 5.3 run_evaluation

```python
def run_evaluation(dataset: Dataset, label: str) -> dict:
    """运行 RAGAS evaluate，返回 {metric_name: score} 字典。"""
    print(f"\n正在运行 RAGAS 评估（{label}）...")
    judge_llm = _get_judge_llm()

    result = evaluate(
        dataset=dataset,
        metrics=METRICS,
        llm=judge_llm,
        raise_exceptions=False,
        show_progress=True,
    )

    import numpy as np
    scores = {}
    for name in METRIC_NAMES:
        try:
            vals = result[name]  # list of per-sample floats
            scores[name] = float(np.nanmean([v for v in vals if v is not None]))
        except Exception:
            scores[name] = 0.0
    return scores
```

**逐行解释**：

- 第 4 行：`_get_judge_llm()` 返回用 `LangchainLLMWrapper` 包装的 GLM-4-Flash，这是 RAGAS 框架要求的 LLM 接口格式。RAGAS 内部用这个 judge LLM 评判答案是否忠实于上下文（faithfulness）等指标，所以需要一个独立的 LLM 而不是被评估的那个 LLM。
- 第 6-11 行：`evaluate(dataset, metrics, llm)` 是 RAGAS 的核心调用。`raise_exceptions=False` 使单个样本评估失败时不中断整个评估流程（某些问题 LLM 可能超时）。`metrics=[faithfulness, context_precision, context_recall]` 分别衡量：答案是否基于检索内容（忠实度）、检索结果是否精准（精确率）、相关文档是否被检索到（召回率）。
- 第 15-19 行：`result[name]` 返回每个样本的分数列表（per-sample），`np.nanmean` 忽略 NaN 计算平均值。用 `nanmean` 而非 `mean` 是因为部分样本可能因超时返回 `None`，直接 `mean` 会得到 NaN。

### 5.4 print_three_way 三组对比输出

```python
def print_three_way(baseline: dict, rerank: dict, hybrid: dict) -> None:
    print("\n=== RAGAS 三组对比（基础向量 vs +Reranker vs 混合检索）===\n")
    header = f"{'指标':<22} {'基础向量':>10} {'向量+Reranker':>14} {'混合检索':>10} {'混合提升':>10}"
    print(header)
    print("-" * 72)
    for name in METRIC_NAMES:
        b, r, h = baseline[name], rerank[name], hybrid[name]
        delta = ((h - b) / b * 100) if b > 0 else 0.0
        sign = "+" if delta >= 0 else ""
        print(f"{name:<22} {b:>10.4f} {r:>14.4f} {h:>10.4f} {sign}{delta:>8.1f}%")
```

**逐行解释**：

- 第 3 行：f-string 中 `:<22` 表示左对齐宽度 22，`:>10` 表示右对齐宽度 10，让表格列对齐。
- 第 7 行：同时解包三组分数 `b, r, h`，对应 baseline、rerank、hybrid 三组。
- 第 8 行：`delta = ((h - b) / b * 100)` — 计算混合检索相对于基础向量的**相对提升百分比**（注意是相对提升而非绝对差值）。`if b > 0` 防止除以零。
- 第 9-10 行：`sign = "+" if delta >= 0` 让正提升显式标 `+`（Python 默认不显示正号），格式为 `+12.3%`，一眼看出提升效果。

**面试话术**：

> `evaluate.py` 的核心思路是控制变量：三种模式用完全相同的问题集和生成逻辑，只换检索策略，这样 RAGAS 评出来的分数差异就真实反映了检索方式的好坏。`run_evaluation` 里调 `evaluate(dataset, metrics, llm)` 时传一个专门的 judge LLM，它和业务 LLM 是分开的——judge LLM 负责评判"这个答案是否真的基于检索内容"，用同一个 LLM 自评会有偏差。`nanmean` 处理 None 是工程上的细节，防止少量样本超时导致整组评估结果变 NaN。
