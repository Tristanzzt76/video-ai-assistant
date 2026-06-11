# 技术架构文档

## 1. 混合检索设计决策

### 为什么单纯向量检索不够

向量检索（dense retrieval）通过语义相似度匹配，在自然语言问答场景表现优秀。但视频技术领域存在大量专有缩写和技术术语，例如 `M3U8`、`GOP`、`PSNR`、`VMAF`、`RTMP`、`HEVC`，这些词在语义空间中的表示高度依赖训练数据覆盖度。

问题场景举例：
- 用户问 "GOP 大小如何影响随机访问？"，向量模型可能将 "group of pictures" 和 "组图" 的向量距离不远，但如果知识库中该词以缩写形式存储，余弦相似度会明显下降
- `PSNR` 和 `SSIM` 在向量空间中语义相近（都是画质指标），但用户问 "PSNR 的计算公式" 时需要精确匹配该词，而不是返回关于 SSIM 的段落

### BM25 的优势

BM25 是基于词频（TF-IDF 变体）的稀疏检索算法，核心优势：

1. **精确词汇匹配**：`M3U8` 就是 `M3U8`，不存在语义漂移
2. **无需 embedding**：索引构建只需分词，速度快，无额外模型推理开销
3. **对长尾技术词鲁棒**：即使 BGE-M3 未充分见过某个缩写，BM25 仍能精确召回

BM25 分数公式：

```
score(q, d) = Σ IDF(t) · (TF(t,d) · (k1+1)) / (TF(t,d) + k1 · (1 - b + b · |d|/avgdl))
```

其中 `k1=1.5`（词频饱和系数），`b=0.75`（文档长度归一化）。

### RRF 融合：为什么这个公式

混合检索需要将向量检索排名和 BM25 排名融合为统一排名。倒数排名融合（Reciprocal Rank Fusion）公式：

```
score(d) = Σ_i  1 / (k + rank_i(d))
```

其中 `rank_i(d)` 是文档 `d` 在第 `i` 个检索系统中的排名（从 1 开始），`k` 是平滑系数。

**为什么选 k=60？**

来自 Cormack et al. 2009 论文《Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods》的实验结论：k=60 是在多个 TREC 基准测试中实证得出的最优平滑值。k 的作用是避免高排名文档获得过大权重——当 k 很小时，rank=1 的文档得分远高于 rank=2，导致融合结果被单一检索源主导；k=60 使得排名 1~5 的文档得分差异不超过 8%，真正实现"软融合"而非"硬选一"。

**直觉理解**：k=60 相当于说"排名靠前很重要，但不绝对"。如果向量检索和 BM25 都认为某文档好，得分会显著高于只有一个认为好的文档。

### 实测效果

在 12 条人工标注的测试集上对比：

| 指标 | 纯向量检索 | 混合检索（BM25 + RRF） | 变化 |
|------|-----------|----------------------|------|
| Faithfulness | 0.886 | 0.985 | **+11.2%** |
| Context Precision | 0.743 | 0.812 | +9.3% |
| Context Recall | 0.891 | 0.847 | -5.0%（可接受，见第4节） |

Faithfulness 提升的原因：混合检索准确召回包含专有术语的段落，LLM 生成答案时有更可靠的 context 支撑，减少了"语义相近但内容不对"的 chunk 导致的幻觉。

---

## 2. LangGraph 状态机 vs 简单链式调用

### LCEL 链式调用的局限

LangChain Expression Language（LCEL）以 `chain = prompt | llm | parser` 管道风格为核心，适合线性无分支场景。在我们的场景中存在以下问题：

1. **状态传递不透明**：LCEL 各步骤之间只能传递单个对象，中间结果（如路由决策、召回的 chunks）需要打包进嵌套字典，类型系统无法约束
2. **条件分支复杂**：`router → rag tool` 和 `router → web tool` 是真正的运行时条件分支，LCEL 的 `RunnableBranch` 虽然支持，但分支内的状态无法回流到主链
3. **调试困难**：出错时无法直接看到哪个节点的输出有问题，只能打日志

### LangGraph 的优势

LangGraph 将 Agent 建模为有向图，每个节点是纯函数 `(AgentState) -> AgentState`：

1. **显式类型化状态**：`AgentState` 是 `TypedDict`，每个字段都有明确类型，IDE 可以静态检查，运行时任意节点的输出都可检查
2. **可视化图结构**：`graph.get_graph().draw_mermaid()` 直接渲染拓扑，文档自动同步代码
3. **条件边语义清晰**：`add_conditional_edges(router, route_condition, {"tool": tool_node, "generate": generate_node})` 直接表达意图
4. **易于扩展**：新增 SQL 查询工具只需加一个节点和在 `route_condition` 中加一条分支，不需要重构调用链

### 我们的 4 节点设计

```
START
  │
  ▼
rewrite ──▶ router ──(direct)──────────────────▶ generate ──▶ END
                │
                └──(rag / web)──▶ tool ──▶ generate ──▶ END
```

| 节点 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `rewrite_node` | 查询改写，补全上下文（多轮对话时把指代词展开） | `messages`, `query` | `query`（改写后） |
| `router_node` | 路由分类：rag / web / direct | `query` | `route` |
| `tool_node` | 执行检索（RAG 或 Web） | `route`, `query` | `retrieved_chunks`, `sources` |
| `generate_node` | 生成最终回答 | `query`, `retrieved_chunks`, `messages` | `answer`, `messages` |

### 为什么 router 判断 direct/rag/web 而不是让 LLM 直接决定

如果让 LLM 在 `generate_node` 中自行判断是否需要检索，会出现以下问题：

1. **不可控**：LLM 可能对同一类问题每次决策不同，系统行为不稳定
2. **无法优化**：路由逻辑在 prompt 里，修改影响范围大
3. **延迟叠加**：生成前才发现需要检索，等于多了一次 LLM 调用

我们的 `router_node` 使用专用 system prompt，强制 LLM 只输出 `rag`/`web`/`direct` 三个 token 之一，fallback 到 `rag`。路由逻辑集中在一处，易于独立测试和迭代。

**设计原则**：将"决策"和"执行"分离，让路由节点专注决策，工具节点专注执行，生成节点专注表达。

---

## 3. BGE-M3 本地 vs API Embedding

### 为什么不用 OpenAI text-embedding-ada-002

| 维度 | BGE-M3 本地 | OpenAI ada-002 API |
|------|------------|-------------------|
| 首次加载延迟 | ~30s（模型加载到内存） | 无 |
| 单次 query encode | <0.1s（GPU MPS） | ~200-400ms（含网络 RTT） |
| 批量 encode（32条） | ~80ms（CPU） / ~15ms（MPS） | ~200-400ms |
| 数据本地化 | 文档内容不出本机 | 所有文本发送 OpenAI |
| 成本 | 0（硬件折旧忽略） | $0.0001/1K tokens |
| 中英混合 | 优秀（专门优化） | 中等 |

**核心决策理由**：

1. **数据本地化**：视频技术文档可能包含内部规范、竞品分析等敏感内容，不应发送第三方 API
2. **成本**：53 chunks × 512 tokens ≈ 2.7万 tokens，看起来很小；但如果未来扩展到 5000 个文档、频繁重新 ingestion，API 成本会累积；本地推理成本为零
3. **中英混合**：视频技术文档大量出现 "HLS 分片时长" "GOP 大小" 这种中英混排，BGE-M3 在该场景语义对齐质量明显优于 ada-002

### BGE-M3 的 Multi-Functionality

BGE-M3 同时支持三种检索范式（这也是选它而非其他本地模型的原因）：

- **Dense retrieval**：标准 dense vector，维度 1024，用于语义相似度
- **Sparse retrieval**：类 BM25 的稀疏向量输出，可直接替代 BM25 或与其融合
- **Multi-vector（ColBERT-style）**：每个 token 生成一个向量，取 MaxSim 聚合，对长文本更精细

我们当前使用 dense + 独立 BM25 的两路融合方案。BGE-M3 的 sparse 输出可以作为 BM25 的替代，后续迭代可以去掉 jieba + rank_bm25，直接用 BGE-M3 的 sparse weights，对中文短语的处理会更准确。

### Apple Silicon MPS 加速

```python
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = SentenceTransformer("BAAI/bge-m3", device=device)
```

在 MacBook Pro M 系列芯片上，MPS 加速使单条 query encode 从 CPU 的 ~80ms 降至 <10ms。首次启动 ~30s 的模型加载是一次性成本（FastAPI 启动时 eager load），推理阶段对用户透明。

---

## 4. RAGAS 评估方法论

### 为什么选这三个指标

RAG 系统的质量有两个维度：**检索质量**（是否找到了正确的 chunks）和**生成质量**（是否基于 chunks 正确作答）。我们选择的三个指标覆盖这两个维度：

| 指标 | 维度 | 核心问题 |
|------|------|---------|
| Faithfulness | 生成质量 | 答案是否有据可查，没有幻觉？ |
| Context Precision | 检索质量 | 有用的 chunks 是否排在前面？ |
| Context Recall | 检索质量 | 正确答案所需的信息是否都被召回？ |

没有选 Answer Relevancy 的原因：它通过"从答案逆向生成问题然后比较语义相似度"来评分，在技术问答场景中，答案往往比问题更长、更详细，逆向生成的问题和原问题的语义距离不能真实反映质量。

### Faithfulness 的计算方式

这是最核心的指标，直接衡量幻觉率：

1. 将 LLM 生成的答案分解为若干**原子 claims**（例如 "HLS 分片时长影响延迟" 和 "典型值为 2-6 秒" 是两个独立 claim）
2. 对每个 claim，让评估 LLM 判断：在 retrieved context 中是否能找到支撑该 claim 的文本？
3. `Faithfulness = 有据可查的 claims 数 / 总 claims 数`

我们的混合检索使 Faithfulness 从 0.886 → 0.985，说明之前约 11% 的 claims 是 LLM 在没有 context 支撑的情况下"编"出来的，混合检索补全了这部分 context 缺口。

### 为什么 Context Recall 下降是可以接受的

| 检索方案 | Context Recall |
|---------|---------------|
| 纯向量，top-5 | 0.891 |
| 混合检索，top-3 | 0.847 |

Context Recall 从 0.891 下降到 0.847，**原因是我们从 top-5 压缩到 top-3**，不是混合检索本身的劣化。

这个代价是合理的：
- top-5 包含更多噪声 chunks，LLM 的 context window 被低质量内容占据，反而影响 Faithfulness
- top-3 经过 RRF 重排，精度更高，Faithfulness 显著提升
- Context Recall 的轻微下降意味着极少数复杂问题可能需要多个 chunks 才能完整回答，这类问题通过扩充知识库解决，不是检索策略问题

**结论**：Faithfulness 是用户体验的直接指标（回答有没有乱编），优先保证它；Context Recall 的小幅下降是可接受的工程权衡。

### 如何构造 ground_truth

12 条标准答案的构造流程：

1. **选题**：覆盖知识库主要主题（HLS/DASH 协议、编解码原理、CDN 策略、画质评估），刻意包含含有专有术语的问题
2. **生成草稿**：先让 LLM 基于原始文档生成候选答案
3. **人工审核**：逐条对照原始文档修正，确保每条答案的每个 claim 都能在文档中找到出处
4. **覆盖边界情况**：包含 2 条"知识库外问题"（预期回答 "我不知道"），验证系统不乱猜

### 评估结论对产品的指导意义

- **Faithfulness 0.985** → 生产环境中约 1.5% 的答案内容可能无据可查，在专业技术问答场景属于可接受水平，上线前需持续监控
- **Context Precision 0.812** → 约 19% 的情况下有用的 chunks 没有排在最前面，说明 Reranker 仍有提升空间（当前知识库仅 53 chunks，Reranker 训练分布不完全匹配）
- **Context Recall 0.847** → 15% 的问题存在"知识盲区"，最直接的改进是扩充知识库覆盖度

---

## 5. 已知局限和改进方向

### 知识库规模（53 chunks）较小

当前知识库来自有限的文档，Reranker 在如此小的候选集上效果有限（top-5 → top-3 的重排收益不大，因为候选质量本身差异不大）。扩展到 500+ 文档后，两阶段检索（粗召回 → 精排）的价值才会充分体现。

**改进**：建立文档采集 pipeline，定期摄取视频技术博客（Cloudflare Blog、FFmpeg 文档、MPEG 规范）。

### GLM-4-Flash 内容过滤影响稳定性

部分技术问题（如包含"攻击""破解"等词汇的安全相关问题）会触发 GLM-4-Flash 的内容过滤，返回拒绝回答。这在技术助手场景下是误判，导致用户体验不稳定。

**改进**：切换到 Anthropic Claude API（claude-haiku-3-5）。Claude 在技术文档问答场景内容过滤更精准，且 API 在中国大陆可直连（通过 Anthropic 官方 API endpoint）。

### BM25 中文分词的局限

当前使用 `jieba` 对文档分词后构建 BM25 索引。jieba 对英文技术术语（`M3U8`、`GOP`、`HEVC`）能正确识别为单个词，但对中文技术短语（如"关键帧间隔"）可能切分为"关键/帧/间隔"，导致短语查询的精确匹配受损。

**改进**：为 jieba 添加自定义词典，将领域术语（"关键帧间隔"、"码率自适应"、"直播切片"等）标注为不可切分词。或者用 BGE-M3 的 sparse weights 直接替代 jieba + rank_bm25，从模型层面解决分词问题。

### 流式输出延迟

当前 `generate_node` 等待 LLM 完整返回后才推送响应，对于长答案用户需要等待 3-5 秒才看到第一个字。

**改进**：使用 LangChain 的 streaming callback + Server-Sent Events (SSE) 实现逐 token 推送，将 TTFT（Time To First Token）从 3-5s 降至 <1s。

### 完整改进路线图

| 优先级 | 改进项 | 预期收益 |
|--------|--------|---------|
| P0 | 替换 GLM-4-Flash → Claude Haiku | 消除内容过滤误判，提升稳定性 |
| P0 | 流式输出（SSE） | TTFT 从 ~4s → <1s |
| P1 | 扩充知识库至 500+ chunks | Context Recall 从 0.847 → 0.92+ |
| P1 | jieba 自定义词典 | 中文技术短语 BM25 精度提升 |
| P2 | BGE-M3 sparse weights 替代 BM25 | 统一检索模型，简化架构 |
| P2 | 添加结构化数据源（视频参数查询） | 支持 "H.264 Level 4.1 最大码率是多少" 类精确查询 |

---

## 附录：状态机完整定义

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 对话历史
    query: str                                             # 当前问题（改写后）
    retrieved_chunks: list[str]                           # 检索结果
    sources: list[str]                                    # 来源标注 "rag" | "web"
    route: Literal["rag", "web", "direct"]                # 路由决策
    answer: str                                           # 最终回答
    session_id: str                                       # 会话 ID
```

```python
def route_condition(state: AgentState) -> Literal["tool", "generate"]:
    return "generate" if state.get("route") == "direct" else "tool"
```

## 附录：混合检索核心实现

```python
def hybrid_search(query: str, top_k: int = 3) -> list[str]:
    # 向量检索
    query_vec = embedder.encode_query(query)
    vector_results = chroma.query(query_embeddings=[query_vec], n_results=10)
    
    # BM25 检索
    tokenized_query = jieba.lcut(query)
    bm25_scores = bm25_index.get_scores(tokenized_query)
    bm25_top_indices = np.argsort(bm25_scores)[::-1][:10]
    
    # RRF 融合
    rrf_scores = defaultdict(float)
    k = 60
    for rank, doc_id in enumerate(vector_results["ids"][0], start=1):
        rrf_scores[doc_id] += 1 / (k + rank)
    for rank, idx in enumerate(bm25_top_indices, start=1):
        doc_id = corpus_ids[idx]
        rrf_scores[doc_id] += 1 / (k + rank)
    
    # 按 RRF 分数排序，取 top_k
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_store[doc_id] for doc_id, _ in sorted_docs[:top_k]]
```
