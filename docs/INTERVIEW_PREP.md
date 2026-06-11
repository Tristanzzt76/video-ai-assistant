# 面试准备文档 — 视频技术 AI 问答助手

## Part 1: 2 分钟项目介绍（背下来）

我做了一个视频技术领域的 AI 问答助手，用 RAG 技术让 LLM 能够准确回答视频编解码、转码、CDN 分发等专业问题。

核心技术亮点有三个：第一，实现了 BM25 + 向量检索 + RRF 融合的混合检索链路，配合 BGE-Reranker 两阶段精排，相比纯向量检索把 faithfulness 从 0.886 提升到 0.985，提升了 11.2%；第二，用 LangGraph 构建了一个四节点的 Agent 状态机，实现了 Query 改写、智能路由（知识库/Web 搜索/直接回答）、工具调用、最终生成的完整链路，具备良好的可扩展性；第三，引入 RAGAS 框架做了系统化的 RAG 质量评估，context_precision 达到 0.986，context_recall 达到 1.0。

整体技术栈是 Python + FastAPI + LangGraph + LlamaIndex + ChromaDB，Embedding 用本地部署的 BGE-M3，LLM 用 GLM-4-Flash，前端是 Next.js 14，支持 SSE 流式输出。

---

## Part 2: 技术深度问答

### Q1：为什么用 LangGraph 而不是简单的 if/else 或 LangChain LCEL？

**标准答案：**

if/else 在简单场景够用，但这个项目有三个需求推动了用 LangGraph：一是路由逻辑需要根据 Query 的语义动态决策（去 RAG、去 Web、直接回答），不是简单的条件分支；二是 Agent 需要状态管理，每个节点的输出要传递给下一个节点，LangGraph 的 StateGraph 天然支持这种有向图状态流转；三是可扩展性——后续加新工具或新节点只需要增加节点和边，不需要改核心逻辑。LCEL 的 `|` 管道是线性链，不适合表达有条件分支和工具调用的 Agent 结构。LangGraph 本质上是把 Agent 抽象成一个有限状态机。

**追问防御：**
- Q: LangGraph 的状态是怎么定义的？ → A: 用 `TypedDict` 定义 `AgentState`，包含 `messages`、`query`、`context` 等字段，每个节点接收 state 并返回 state 的更新部分。
- Q: 有没有用到 LangGraph 的 checkpoint？ → A: 当前项目没用持久化 checkpoint，如果要支持多轮对话会话恢复，可以接 SQLite 或 Redis checkpointer。

---

### Q2：混合检索具体是怎么实现的？BM25 和向量检索各解决什么问题？

**标准答案：**

两者互补解决不同类型的匹配问题。BM25 是基于词频统计的稀疏检索，擅长处理精确词匹配，比如用户搜"H.264"、"GOP"这种专业术语，BM25 能直接命中包含这些词的文档；向量检索是语义检索，把 Query 和文档都编码到同一个语义空间，擅长处理语义相近但词面不同的情况，比如"视频卡顿"和"缓冲延迟"。技术上，BM25 用 `rank_bm25` 库 + jieba 分词，向量检索用 BGE-M3 本地 Embedding + ChromaDB。两路各自返回 Top-K 候选，然后用 RRF 做排名融合，最后再过 BGE-Reranker 精排取 Top-3 送给 LLM。

**追问防御：**
- Q: 两路检索的权重怎么分配？ → A: RRF 不需要手动调权重，它通过排名位置自动融合，这正是选 RRF 的原因之一。
- Q: BM25 召回多少，向量召回多少？ → A: 两路各取 Top-10，RRF 融合后取 Top-10，Reranker 精排后取 Top-3。

---

### Q3：RRF（Reciprocal Rank Fusion）算法原理是什么？为什么 k=60？

**标准答案：**

RRF 的核心公式是 `score(d) = Σ 1/(k + rank_i(d))`，对文档 d 在每个检索系统中的排名取倒数再求和。排名越靠前得分越高，多个系统都排前面的文档会得到叠加加分。k 是平滑参数，防止排名第 1 的文档得分过于突出（分母最小为 k+1=61），使得排名差异对最终得分的影响更平滑。k=60 是 RRF 原论文（Cormack et al., 2009）的推荐默认值，在大量实验中表现稳定，不需要对每个场景单独调参。这也是 RRF 的优势之一——相比加权融合，它对超参不敏感，工程上简单可靠。

**追问防御：**
- Q: 有没有试过其他融合方法？ → A: 有考虑过加权线性融合，但两路得分的量纲不一样（BM25 无界，余弦相似度在 0-1），需要归一化，引入额外超参，不如 RRF 简洁。
- Q: k=60 是你调出来的还是默认值？ → A: 沿用原论文默认值，在当前数据规模（53 chunks）上没有做进一步调参，如果数据量大幅增加需要重新实验。

---

### Q4：RAGAS 的 faithfulness 指标怎么计算的？

**标准答案：**

faithfulness 衡量 LLM 的回答是否忠实于检索到的上下文，防止幻觉。计算方式是：先让 LLM 把 answer 拆解成若干个原子陈述（atomic claims），然后对每个 claim 判断是否能从 retrieved context 中推导出来，最终 faithfulness = 可推导的 claim 数 / 总 claim 数。这个指标的计算本身也要依赖 LLM（做 NLI 判断），所以对 judge LLM 的质量有一定要求。我们的结果是 0.985，意味着生成的回答中 98.5% 的陈述都有上下文支撑，基本没有幻觉。

**追问防御：**
- Q: faithfulness 高就代表回答质量高吗？ → A: 不完全是。faithfulness 只保证回答不超出上下文，但如果上下文本身就检索错了，回答也会错。需要结合 context_precision 和 context_recall 一起看。
- Q: 0.985 和 0.886 的差距是怎么来的？ → A: 纯向量检索有时会召回语义相近但实际不相关的片段，LLM 看到这些噪声上下文容易生成不在知识库中的内容。混合检索 + Reranker 精排后上下文质量提升，faithfulness 随之提升。

---

### Q5：为什么 context_recall 从 1.0 降到 0.97 是可以接受的？

**标准答案：**

context_recall 衡量 ground_truth 中的信息有多少被检索到了。从 1.0 降到 0.97 意味着约 3% 的相关信息没有被召回。这个 trade-off 可以接受，原因有两点：第一，加入 Reranker 精排后把候选从 Top-10 压缩到 Top-3，理论上会损失一定召回，这是精排天然的代价；第二，对应 faithfulness 提升了 11.2%（0.886→0.985），生成质量的提升远大于召回损失。在实际应用场景中，用户更在意回答不出错（faithfulness），轻微的召回下降不会被感知到，但幻觉会直接损害用户信任。

**追问防御：**
- Q: 如果 context_recall 再低怎么办？ → A: 可以增大 Reranker 的 top_n（比如从 3 改到 5），牺牲一点 faithfulness 换回召回率，根据业务场景权衡。

---

### Q6：BGE-M3 为什么选本地而不是 API？有什么 trade-off？

**标准答案：**

选本地部署主要有三个原因：第一，数据隐私——视频技术文档可能包含内部知识，不想发给外部 API；第二，延迟确定性——本地推理延迟稳定，不受网络波动和 API 限速影响，对 RAG 链路的响应时间可预期；第三，成本——Embedding API 按 token 计费，知识库索引阶段和线上查询都有调用，规模大了费用可观。trade-off 是本地需要 GPU 内存（BGE-M3 约 2GB 显存），冷启动需要加载模型（约 10-20 秒），部署运维成本更高。当前项目在本地 GPU 上运行，这些代价可以接受。

**追问防御：**
- Q: BGE-M3 相比 OpenAI text-embedding-3-small 怎么样？ → A: BGE-M3 支持多语言（中文效果好）、多粒度（dense/sparse/colbert），在中文语义检索 benchmark 上表现不输 OpenAI，且完全免费。
- Q: 为什么不用 OpenAI Embedding API？ → A: 除了上述原因，这个项目的核心目标之一是探索本地部署方案的可行性。

---

### Q7：BGE-Reranker 放在什么位置，为什么用两阶段检索而不是直接用 Reranker？

**标准答案：**

Reranker 放在 RRF 融合之后、送 LLM 之前，是第二阶段的精排。直接用 Reranker 做全库检索不可行，原因是计算复杂度：Reranker（CrossEncoder）需要把 Query 和每个候选文档拼接在一起做 inference，复杂度是 O(n)，53 个 chunks 还勉强，百万文档就不可能每次都全量推理。两阶段设计是标准的召回-精排范式：第一阶段用向量/BM25 快速从全库召回 Top-K（O(log n) 或 O(n) 但常数小），第二阶段 Reranker 在小候选集上精排，质量高但慢。这样兼顾了效率和质量。

**追问防御：**
- Q: Reranker 和 Embedding 模型有什么本质区别？ → A: Embedding 是双塔模型，Query 和 Document 分别编码再算相似度，速度快但 Query-Document 的交互信息有损失；Reranker 是交叉编码器，把 Query 和 Document 拼接做联合 inference，捕获更细粒度的交互，质量更高但慢 10-100 倍。

---

### Q8：Query 改写（Query Rewriting）的作用是什么，如何实现的？

**标准答案：**

用户的原始提问往往有两类问题影响检索质量：一是表达不完整，比如多轮对话中的指代消解（"它是什么意思"中的"它"）；二是措辞和知识库不匹配，比如用口语问专业问题。Query 改写节点先于检索执行，用 LLM（GLM-4-Flash）把用户原始问题改写成更利于检索的形式：补全指代、扩展关键词、统一术语。实现上是 LangGraph 的第一个节点 `rewrite_query`，接收原始 messages，prompt 要求 LLM 输出一个改写后的搜索 query，然后把这个 query 送入后续的 router 节点。

**追问防御：**
- Q: 改写之后原始问题怎么办？ → A: 改写后的 query 用于检索，最终生成时 prompt 里同时包含原始问题和检索结果，保证 LLM 理解用户的原始意图。
- Q: 如果改写引入了错误怎么办？ → A: 当前没有做改写质量的显式校验，这是一个潜在风险点。改进方向是加改写置信度评估或多路改写取最优。

---

### Q9：系统是如何决定用 RAG 还是 Web Search 还是直接回答的？

**标准答案：**

路由由 LangGraph 的 `router` 节点实现，本质是让 LLM 做分类决策。router 节点拿到改写后的 query，调用 LLM 并附带 Function Calling 定义（`rag_search` 和 `web_search` 两个工具），LLM 根据 query 内容决定调用哪个工具，或者不调用工具（直接回答）。判断逻辑大致是：视频技术专业问题（编解码、转码、CDN）→ RAG；实时性信息或知识库外的问题 → Web Search；通用问题或闲聊 → 直接回答。路由结果通过 LangGraph 的条件边（conditional edges）决定下一个节点走向。

**追问防御：**
- Q: 路由准确率有多少？ → A: 没有单独评估路由准确率，从 RAGAS 结果来看整体链路质量达标。严格的生产环境需要构造路由专项测试集。
- Q: 如果 LLM 路由判断错了怎么办？ → A: 当前没有兜底机制，LLM 路由错误会导致回答质量下降。改进方向是加规则前置过滤（关键词判断是否是视频技术相关）。

---

### Q10：ChromaDB 和 Milvus/Pinecone 比有什么优缺点？为什么选 ChromaDB？

**标准答案：**

ChromaDB 是嵌入式向量数据库，最大优点是零运维——可以以库的形式直接嵌入 Python 进程，不需要单独部署服务，开发阶段极其方便；持久化只需要指定一个本地目录。缺点是性能天花板低，不支持分布式，单机内存受限，不适合亿级向量。Milvus 是分布式向量数据库，支持水平扩展、多种索引（HNSW/IVF/DiskANN）、高并发，但需要部署 etcd + MinIO + Milvus 服务，运维成本高。Pinecone 是 SaaS，无需自建，但数据在第三方，有隐私和成本问题。当前项目 53 个 chunks，选 ChromaDB 是合理的——开发效率优先，不需要生产级扩展性。

**追问防御：**
- Q: 如果数据量增长到百万，怎么迁移？ → A: ChromaDB 支持导出 embedding，可以把向量和元数据迁移到 Milvus，应用层只需要换一个 VectorStore 实现类（LlamaIndex 抽象了 VectorStore 接口）。

---

### Q11：如果知识库扩展到百万文档，当前架构哪里会成为瓶颈？

**标准答案：**

有三个主要瓶颈：第一，ChromaDB 单机内存限制，百万文档的 dense embedding（每个 1024 维 float32 = 4KB）需要约 4GB 内存，超出后性能急剧下降，需要替换成 Milvus 或 Elasticsearch + 向量插件；第二，BGE-Reranker 的候选集扩大问题，如果 RRF 融合后候选集从 10 扩大到 100，Reranker 的推理时间会线性增长，需要更大的 GPU 或批处理优化；第三，BM25 的全量扫描，`rank_bm25` 是纯 Python 实现，百万文档下词频统计会成为 CPU 瓶颈，需要替换成 Elasticsearch BM25（已有分布式索引）。索引阶段的 Embedding 生成也会成为耗时问题，需要批量 GPU 推理。

**追问防御：**
- Q: 查询延迟能接受多少？ → A: 当前 53 chunks 下端到端约 2-3 秒（含 LLM 生成），百万文档主要影响检索阶段，目标控制在 500ms 内。

---

### Q12：SSE 流式输出怎么实现的？为什么用 SSE 而不是 WebSocket？

**标准答案：**

SSE（Server-Sent Events）是单向的服务端推送协议，基于 HTTP 长连接，服务端持续推送 `data: ...\n\n` 格式的事件流。FastAPI 实现用 `StreamingResponse` + `EventSourceResponse`（`sse-starlette` 库），LLM 调用用 GLM-4-Flash 的流式 API，每收到一个 token 就 yield 一个 SSE event，前端 Next.js 用 `EventSource` API 或 `fetch` + `ReadableStream` 消费。选 SSE 而不是 WebSocket 的原因：LLM 流式输出是单向数据流（服务端 → 客户端），WebSocket 的双向全双工能力完全用不上，反而增加握手复杂度；SSE 基于 HTTP，天然走现有的反向代理和 CDN，不需要额外处理升级协议；断线重连 SSE 有内置的 `Last-Event-ID` 机制。

**追问防御：**
- Q: SSE 有没有消息大小限制？ → A: 没有硬限制，但建议每个 event 保持小粒度（单 token 或几个 token），避免 buffer 积压。
- Q: 前端怎么判断流结束？ → A: 服务端发送一个特殊的终止事件（比如 `data: [DONE]`），或者关闭连接，前端监听 `close` 事件。

---

### Q13：RAGAS 评估的 ground_truth 是怎么构造的？

**标准答案：**

ground_truth 是指对给定问题的标准参考答案，用于计算 context_recall（检索到的上下文能覆盖多少 ground_truth 信息）和 answer_correctness 等指标。构造方式：基于知识库文档手动编写了一组测试问题，对每个问题阅读原始文档写出参考答案，确保 ground_truth 完全基于知识库内容，没有引入外部信息。这个过程是手动的，共构造了若干个问答对作为评估数据集。局限性是规模小（和 53 chunks 的数据量匹配），没有做多轮标注来减少标注偏差，且 ground_truth 质量直接影响评估结论的可信度。

**追问防御：**
- Q: 能不能用 LLM 自动生成 ground_truth？ → A: 可以，LlamaIndex 和 RAGAS 都有 `generate_testset` 功能，但 LLM 生成的 ground_truth 可能有偏差，需要人工审核，当前数据量小，直接手写更可控。

---

### Q14：项目中遇到的最大技术挑战是什么？怎么解决的？

**标准答案：**

最大的挑战是依赖库版本兼容性问题，集中在两个地方：第一，BGE-Reranker 的 `FlagReranker` 类在新版 `transformers 5.x` 下报 `AttributeError`，排查发现是 FlagEmbedding 库假定的 transformers 内部 API 在新版中被重命名，解决方案是换成 `sentence-transformers` 的 `CrossEncoder` 类直接加载 BGE-Reranker 模型，API 更稳定；第二，RAGAS 0.2.x 版本 API 与旧教程完全不同，`LangchainLLMWrapper` 的初始化方式和 metrics 的调用方式都变了，花了大量时间阅读 RAGAS GitHub 的 CHANGELOG 和 Issues 才找到正确用法。这两个问题的本质都是快速迭代的 AI 生态导致文档滞后，解决方法是直接看源码和 GitHub Issues，而不是依赖博客教程。

**追问防御：**
- Q: 有没有其他挑战？ → A: 还有 HuggingFace 模型下载走 XET 协议失败的问题，设置 `HF_HUB_DISABLE_XET=1` 环境变量后解决。

---

### Q15：为什么 GLM-4-Flash 内容过滤会干扰 RAGAS 评估？如何解决的？

**标准答案：**

RAGAS 评估时，框架内部会用 judge LLM（我们用的是 GLM-4-Flash）来做 faithfulness 的原子 claim 判断，以及其他指标的 NLI 判断。GLM-4-Flash 的内容安全过滤有时会把 RAGAS 构造的中间 prompt（比如包含"判断以下陈述是否为真"这类表述）误判为敏感内容，直接返回拒绝回答，导致 RAGAS 评估流程抛异常或得到无效评分。解决方式：一是在 RAGAS 初始化时调整 prompt 模板，避免触发过滤的措辞；二是切换评估用的 judge LLM，评估阶段使用对内容审查更宽松的模型（如 GPT-3.5-turbo 或本地 LLM）；三是对 RAGAS 的异常做 catch，过滤掉无效评估样本后重新统计均值。

**追问防御：**
- Q: 生产环境也用 GLM-4-Flash 吗？ → A: 是的，问答服务本身用 GLM-4-Flash，它对正常的视频技术问答没有过滤问题，只有 RAGAS 的特殊 prompt 格式才会触发。

---

### Q16：BM25 中文分词用的 jieba，有什么局限性？

**标准答案：**

jieba 的主要局限性有三点：第一，专业术语覆盖不足——视频技术领域有大量专有名词（H.264、HEVC、GOP、PTS/DTS、ABR），jieba 默认词典没有这些词，会被错误切分（比如"H.264"被切成"H"和"264"），需要通过 `jieba.add_word()` 手动添加自定义词典；第二，新词识别依赖统计，对出现频率低的专业词效果差；第三，分词是基于最大概率路径，对歧义句的切分不保证语义正确性，可能影响 BM25 的词频统计准确性。当前项目通过添加部分视频技术专有词到 jieba 自定义词典缓解了这个问题，但没有做系统性的领域词典构建。

**追问防御：**
- Q: 有没有比 jieba 更好的选择？ → A: PKUSeg（北大分词）对专业文本支持更好，或者用基于 subword 的 tokenizer（如 sentencepiece）完全绕过中文分词问题。

---

### Q17：LlamaIndex 的 SentenceSplitter，chunk_size=512 是怎么选的？

**标准答案：**

chunk_size=512 是在检索质量和上下文完整性之间的权衡结果。选择依据：第一，BGE-M3 的最大输入长度是 8192 tokens，512 远小于上限，不会截断；第二，视频技术文档的段落结构，一个技术概念的完整描述通常在 300-600 字之间，512 tokens（约 300-400 中文字符）能包含一个相对完整的语义单元；第三，chunk 越小检索粒度越细（有利于 precision），但可能切断语义完整性（损害 recall），512 是常用的经验值。实际上做了简单对比：chunk_size=256 时 context_recall 下降（信息被切散），chunk_size=1024 时检索到的无关内容比例上升，512 在当前数据集上是较优解。chunk_overlap=50 用于相邻 chunk 的内容重叠，避免边界处的信息丢失。

**追问防御：**
- Q: 有没有做系统的消融实验？ → A: 做了简单的对比实验，但没有穷举所有参数组合，这是可以改进的地方。

---

### Q18：如果要支持 PDF 上传，当前系统需要什么改动？

**标准答案：**

需要在三个层面改动：第一，文档解析层——加 PDF 解析器，LlamaIndex 支持 `PDFReader`（基于 `pypdf`）或更强的 `LlamaParse`（处理表格、图片），解析出纯文本后接现有的 SentenceSplitter pipeline；第二，上传接口层——FastAPI 新增 `POST /upload` 接口，接收 `multipart/form-data`，把文件存到本地或对象存储，触发异步解析和索引任务（用 Celery 或 BackgroundTasks）；第三，增量索引——ChromaDB 支持增量 `add_documents`，但需要维护文档唯一 ID（用文件名+hash），避免重复索引；还需要加文档管理接口（查看、删除）。前端需要加上传 UI 和索引进度展示。这些改动不涉及核心检索和生成逻辑，架构扩展性是足够的。

**追问防御：**
- Q: PDF 中的表格和图片怎么处理？ → A: 当前方案只处理文本，表格可以转 markdown 表格，图片需要多模态模型（如 GPT-4V）提取描述，这是更复杂的扩展方向。

---

### Q19：项目如何保证 LLM 回答的准确性（不产生幻觉）？

**标准答案：**

从三个层面做了防幻觉设计：第一，Prompt Engineering——系统 prompt 明确要求 LLM"仅根据提供的上下文回答，如果上下文中没有相关信息，直接说不知道，不要编造"，并把检索到的上下文结构化拼接在 prompt 中；第二，Reranker 精排保证上下文质量——送给 LLM 的是经过两阶段筛选的 Top-3 高质量 chunk，减少噪声上下文对生成的干扰；第三，RAGAS 闭环评估——用 faithfulness 指标量化监控幻觉率，当前 0.985 意味着生成内容 98.5% 有依据，作为质量基线。潜在不足是 Prompt 约束对 LLM 的遵循程度依赖模型能力，GLM-4-Flash 在某些边界情况下仍可能超出上下文范围生成。

**追问防御：**
- Q: 能做到 100% 无幻觉吗？ → A: 不能，只要使用生成式 LLM 就无法从根本上消除，只能通过检索增强 + prompt 约束 + 评估监控来降低和及时发现。

---

### Q20：如果让你重做这个项目，你会改什么？

**标准答案：**

主要改三点：第一，评估体系前置——现在是先实现再评估，如果重来会先构建更完整的测试集（50+ QA 对，覆盖多种问题类型），建立评估 CI，每次改动都跑 RAGAS，而不是最后才补评估；第二，路由策略改进——当前 LLM 路由缺乏明确的 fallback 机制，如果 LLM 路由判断失误没有兜底，重做时会加规则前置过滤（关键词匹配判断是否是视频技术领域）+ 置信度阈值；第三，Embedding 缓存——当前每次启动都重新生成 embedding（虽然有 ChromaDB 持久化），但如果文档没变化应该直接复用，加文档内容 hash 对比来判断是否需要重新 index，减少冷启动时间。架构层面没有大的改动，整体设计是合理的。

**追问防御：**
- Q: 有没有考虑用更好的 LLM？ → A: GLM-4-Flash 是免费 API，性价比高，满足当前需求。如果要进一步提升生成质量，可以换 GPT-4o-mini 或 GLM-4-Plus，成本会上升。

---

## Part 3: 项目难点亮点

### 难点 1：BGE-Reranker 与 transformers 5.x 不兼容

**问题描述：** 使用 `FlagEmbedding` 库的 `FlagReranker` 加载 `BAAI/bge-reranker-base` 模型时，在 transformers 5.x 环境下报 `AttributeError: 'XLMRobertaTokenizerFast' object has no attribute 'xxx'`。

**排查过程：** 通过阅读 FlagEmbedding 的 GitHub Issues 发现，FlagReranker 内部依赖了 transformers 的私有 API，该 API 在 5.x 中被重命名或删除，但 FlagEmbedding 没有及时更新。

**解决方案：** 改用 `sentence-transformers` 库的 `CrossEncoder` 类：
```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('BAAI/bge-reranker-base')
scores = reranker.predict([(query, doc) for doc in candidates])
```
CrossEncoder 是 sentence-transformers 的标准接口，维护更活跃，向后兼容性更好。

---

### 难点 2：RAGAS 0.2.x 新版 API 不兼容

**问题描述：** 按照网上大部分教程使用 `LangchainLLMWrapper` 和旧版 metrics API，报 `ImportError` 和 `TypeError`，大量 API 已变更。

**排查过程：** 阅读 RAGAS 的 GitHub CHANGELOG（0.1.x → 0.2.x 是 breaking change），新版将 LLM 包装器、metrics 初始化方式全部重构，旧文档和博客已全部过时。

**解决方案：** 直接阅读 RAGAS 官方文档的 Migration Guide 和源码，按新版 API 重写评估代码：
```python
# 新版 0.2.x 写法
from ragas import evaluate
from ragas.metrics import faithfulness, context_precision, context_recall
from ragas.llms import LangchainLLMWrapper

llm_wrapper = LangchainLLMWrapper(langchain_llm=chat_model)
result = evaluate(dataset=eval_dataset, metrics=[faithfulness, ...], llm=llm_wrapper)
```

---

### 难点 3：HuggingFace XET 协议下载失败

**问题描述：** 在国内环境下载 BGE-M3 模型时，HuggingFace Hub 新版切换到 XET（基于 xethub 的传输协议），下载直接报连接错误，换镜像也没用（镜像站没有实现 XET 协议）。

**排查过程：** 查看 HuggingFace Hub 的 release notes 和 Issues，确认 XET 是新加的实验性传输协议，镜像站和部分环境不支持。

**解决方案：** 设置环境变量禁用 XET，回退到标准 HTTP 下载：
```bash
export HF_HUB_DISABLE_XET=1
```
或在代码中：
```python
import os
os.environ["HF_HUB_DISABLE_XET"] = "1"
```
配合 `HF_ENDPOINT=https://hf-mirror.com` 使用国内镜像站，下载成功。

---

## Part 4: 和面试官的差异化聊法

### AI 基础设施岗

重点聊 RAG 检索链路的工程实现：
- 两阶段检索（召回 → 精排）的设计动机和性能 trade-off
- BGE-M3 本地部署：显存占用、冷启动优化、batch 推理
- Reranker 的 CrossEncoder 架构 vs Bi-Encoder 的本质区别
- 如何扩展到更大数据量（ChromaDB → Milvus，本地 GPU → 分布式推理）
- **聊法示例：** "我做了一个两阶段检索，第一阶段 BM25 + 向量各召回 Top-10 做 RRF 融合，第二阶段 Reranker 精排到 Top-3，这个设计的核心考虑是 Reranker 的 O(n) 复杂度……"

### 搜推平台岗

重点聊检索召回和排序的工程细节：
- BM25 和向量检索的互补性（精确匹配 vs 语义匹配）
- RRF 融合为什么比加权融合更鲁棒（不依赖得分归一化）
- 召回/精排分离的工业界标准范式
- RAGAS 指标体系对应搜推的 NDCG/Precision/Recall
- **聊法示例：** "这套混合检索思路其实和搜推的多路召回 + 精排是一样的范式，只是规模小，我做的是 BM25 稀疏召回 + 向量密集召回，通过 RRF 无参数融合……"

### 大模型应用岗

重点聊 LLM 应用工程：
- LangGraph 状态机设计：节点、边、状态的定义
- Agent 路由策略：Function Calling 驱动的动态路由
- Prompt Engineering：防幻觉 prompt 设计
- RAGAS 评估闭环：如何量化 RAG 系统质量
- **聊法示例：** "LangGraph 的核心是把 Agent 的执行过程显式建模成有向图，我定义了 rewrite_query → router → tool_node → generate 四个节点，路由通过 LLM 的 Function Calling 实现……"

### 后端开发岗

重点聊系统设计和工程实现：
- FastAPI + SSE 的异步流式输出实现
- ChromaDB 的持久化和增量索引
- 系统的整体分层架构（接入层/检索层/生成层）
- 如果上生产需要做什么（鉴权、限流、监控、日志）
- **聊法示例：** "后端用 FastAPI + SSE 实现流式输出，StreamingResponse 包装 async generator，每次 LLM 吐出 token 就 yield 一个 SSE event，前端用 EventSource 消费……"

---

## Part 5: 简历描述

### 详细版（项目经历，3-4 条 bullet）

**视频技术 AI 问答助手** | Python / FastAPI / LangGraph / RAG | 2024

- 基于 LangGraph 构建四节点 Agent 状态机（Query 改写 → 路由 → 工具调用 → 生成），支持 RAG 知识库检索与 Web Search 动态路由，实现视频技术领域智能问答
- 实现 BM25（jieba 分词）+ BGE-M3 向量检索 + RRF 融合的混合检索链路，结合 BGE-Reranker 两阶段精排，相比纯向量检索将 RAGAS faithfulness 从 0.886 提升至 0.985（+11.2%）
- 引入 RAGAS 框架构建评估闭环，context_precision 0.986，context_recall 1.0；FastAPI + SSE 实现 LLM 流式输出，Next.js 14 前端展示
- 解决 BGE-Reranker/transformers 版本兼容、RAGAS 0.2.x API 迁移、HuggingFace XET 协议下载等工程问题

### 简短版（技能栏，1 条）

RAG 系统开发：LangGraph Agent、混合检索（BM25 + 向量 + RRF）、两阶段精排（BGE-Reranker）、RAGAS 评估；RAGAS faithfulness 0.985
