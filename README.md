# video-ai-assistant

A minimal **Video technology RAG + LangGraph Agent Q&A system**.

## What is included

- `VideoKnowledgeBase`: in-memory video chunk store + retrieval
- `VideoRAGLangGraphAgent`: two-step LangGraph flow
  1. retrieve relevant video context
  2. generate answer with source citations
- graceful fallback execution when `langgraph` is not installed

## Quick usage

```python
from video_ai_assistant import VideoChunk, VideoKnowledgeBase, VideoRAGLangGraphAgent

kb = VideoKnowledgeBase()
kb.add_chunk(VideoChunk(video_id="video-1", timestamp="00:02:10", text="RAG uses retrieval before generation."))

agent = VideoRAGLangGraphAgent(kb)
print(agent.ask("How does RAG work?"))
```

## Run tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
