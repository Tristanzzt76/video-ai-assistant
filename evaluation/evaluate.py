"""
RAGAS 评估脚本：对比 基础RAG vs 加Reranker 的效果。

运行方式：
  python evaluation/evaluate.py --mode baseline   # 无 Reranker
  python evaluation/evaluate.py --mode rerank     # 有 Reranker
  python evaluation/evaluate.py --mode compare    # 两者对比（默认）
"""
import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from src.config import get_settings
from src.rag.retriever import ChromaRetriever
from src.agent.graph import _get_llm

# ── 常量 ──────────────────────────────────────────────────────────────────────

DATASET_PATH = Path(__file__).parent / "dataset.json"
RESULTS_DIR = Path(__file__).parent

METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]
METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


# ── Judge LLM & Embeddings（用于 RAGAS 内部评估）────────────────────────────

def _get_judge_llm() -> LangchainLLMWrapper:
    return LangchainLLMWrapper(ChatOpenAI(
        model="glm-4-flash",
        api_key=os.getenv("ZHIPU_API_KEY"),
        base_url="https://open.bigmodel.cn/api/paas/v4/",
        temperature=0,
    ))


def _get_judge_embeddings() -> LangchainEmbeddingsWrapper:
    return LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model="embedding-3",
        api_key=os.getenv("ZHIPU_API_KEY"),
        base_url="https://open.bigmodel.cn/api/paas/v4/",
    ))


# ── 检索 + 生成 ───────────────────────────────────────────────────────────────

def build_retriever() -> ChromaRetriever:
    settings = get_settings()
    return ChromaRetriever(chroma_path=settings.chroma_path)


def retrieve_contexts(retriever: ChromaRetriever, question: str, rerank: bool) -> list[str]:
    """调用 ChromaRetriever.search()，返回检索到的文本列表。"""
    chunks = retriever.search(
        query=question,
        top_k=5,
        rerank=rerank,
        rerank_top_k=3,
    )
    return [chunk.text for chunk in chunks] if chunks else [""]


def generate_answer(question: str, contexts: list[str]) -> str:
    """用项目 LLM 生成回答。"""
    llm = _get_llm()
    context_text = "\n\n".join(contexts) if contexts else ""
    if context_text.strip():
        prompt = f"参考以下资料回答问题：\n\n{context_text}\n\n问题：{question}"
    else:
        prompt = question
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"  [警告] LLM 生成失败: {e}", file=sys.stderr)
        return ""


# ── 构建 RAGAS Dataset ────────────────────────────────────────────────────────

def build_ragas_dataset(
    samples: list[dict],
    retriever: ChromaRetriever,
    rerank: bool,
) -> Dataset:
    """
    对每个 sample 做检索 + 生成，返回 RAGAS 格式的 Dataset。
    """
    questions, answers, contexts_list, ground_truths = [], [], [], []

    for i, sample in enumerate(samples):
        q = sample["question"]
        gt = sample["ground_truth"]
        print(f"  [{i+1}/{len(samples)}] {q[:40]}...")

        ctxs = retrieve_contexts(retriever, q, rerank=rerank)
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


# ── 运行评估 ──────────────────────────────────────────────────────────────────

def run_evaluation(dataset: Dataset, label: str) -> dict:
    """运行 RAGAS evaluate，返回 {metric_name: score} 字典。"""
    print(f"\n正在运行 RAGAS 评估（{label}）...")
    judge_llm = _get_judge_llm()
    judge_emb = _get_judge_embeddings()

    result = evaluate(
        dataset=dataset,
        metrics=METRICS,
        llm=judge_llm,
        embeddings=judge_emb,
        raise_exceptions=False,
    )

    scores = {}
    for name in METRIC_NAMES:
        val = result.get(name)
        scores[name] = float(val) if val is not None else 0.0
    return scores


# ── 输出格式化 ────────────────────────────────────────────────────────────────

def print_single(label: str, scores: dict) -> None:
    print(f"\n=== RAGAS 评估结果（{label}）===\n")
    print(f"{'指标':<22} {'得分':>8}")
    print("-" * 32)
    for name in METRIC_NAMES:
        print(f"{name:<22} {scores[name]:>8.4f}")


def print_comparison(baseline: dict, rerank: dict) -> None:
    print("\n=== RAGAS 评估结果对比 ===\n")
    header = f"{'指标':<22} {'基础RAG':>10} {'加Reranker':>12} {'提升':>10}"
    print(header)
    print("-" * 58)
    for name in METRIC_NAMES:
        b = baseline[name]
        r = rerank[name]
        delta = ((r - b) / b * 100) if b > 0 else 0.0
        sign = "+" if delta >= 0 else ""
        print(f"{name:<22} {b:>10.4f} {r:>12.4f} {sign}{delta:>8.1f}%")


# ── 保存结果 ──────────────────────────────────────────────────────────────────

def save_results(data: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"results_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {out_path}")
    return out_path


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAGAS 评估：基础RAG vs 加Reranker")
    parser.add_argument(
        "--mode",
        choices=["baseline", "rerank", "compare"],
        default="compare",
        help="评估模式（默认: compare）",
    )
    args = parser.parse_args()

    # 加载数据集
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        samples = json.load(f)
    print(f"加载数据集: {len(samples)} 条问答对")

    retriever = build_retriever()
    results_to_save = {"mode": args.mode, "timestamp": datetime.now().isoformat()}

    if args.mode == "baseline":
        print("\n[基础RAG] 构建检索数据...")
        ds = build_ragas_dataset(samples, retriever, rerank=False)
        scores = run_evaluation(ds, "基础RAG")
        print_single("基础RAG", scores)
        results_to_save["baseline"] = scores

    elif args.mode == "rerank":
        print("\n[加Reranker] 构建检索数据...")
        ds = build_ragas_dataset(samples, retriever, rerank=True)
        scores = run_evaluation(ds, "加Reranker")
        print_single("加Reranker", scores)
        results_to_save["rerank"] = scores

    else:  # compare
        print("\n[基础RAG] 构建检索数据...")
        ds_baseline = build_ragas_dataset(samples, retriever, rerank=False)
        baseline_scores = run_evaluation(ds_baseline, "基础RAG")

        print("\n[加Reranker] 构建检索数据...")
        ds_rerank = build_ragas_dataset(samples, retriever, rerank=True)
        rerank_scores = run_evaluation(ds_rerank, "加Reranker")

        print_comparison(baseline_scores, rerank_scores)
        results_to_save["baseline"] = baseline_scores
        results_to_save["rerank"] = rerank_scores

    save_results(results_to_save)


if __name__ == "__main__":
    main()
