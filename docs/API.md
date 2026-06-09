# API Reference

Base URL: `http://localhost:8000/api/v1`

All request and response bodies are JSON. All endpoints accept and return `Content-Type: application/json` unless noted.

---

## POST /api/v1/upload

Upload a document (PDF, Markdown, or plain text) to the knowledge base. The file is chunked, embedded with BGE-M3, and written to ChromaDB.

### Request

`Content-Type: multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | The document to upload. Allowed extensions: `.pdf`, `.md`, `.txt`. Maximum practical size: ~50 MB. |

### Response `200 OK`

```json
{
  "doc_id": "a3f7c912",
  "filename": "hls-spec.pdf",
  "chunk_count": 47,
  "message": "成功处理 47 个 chunk"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | string | 8-character UUID prefix, uniquely identifies the document in the vector store. Use this to reference or delete the document later. |
| `filename` | string | Original filename as provided in the upload. |
| `chunk_count` | integer | Number of text chunks written to ChromaDB after splitting. |
| `message` | string | Human-readable confirmation. |

### Error Codes

| Code | Condition |
|------|-----------|
| `400 Bad Request` | File extension not in `.pdf / .md / .txt`. Body: `{"detail": "不支持的文件类型: .docx，支持 {'.pdf', '.md', '.txt'}"}` |
| `500 Internal Server Error` | File save failed or document parsing/embedding failed. Body: `{"detail": "文档处理失败: <error message>"}` |

---

## POST /api/v1/chat

Submit a question to the LangGraph Agent. The agent classifies the query, optionally retrieves context from ChromaDB or the web, then generates an answer with Claude.

### Request

```json
{
  "query": "HLS 的分片时长如何影响直播延迟？",
  "session_id": "user-abc-session-01",
  "stream": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | The question. Length: 1–2000 characters. |
| `session_id` | string | No | Session identifier for multi-turn context. Defaults to `"default"`. Use a unique value per conversation to maintain history isolation. |
| `stream` | boolean | No | Reserved for streaming support. Currently ignored; always returns full response. Default `false`. |

### Response `200 OK`

```json
{
  "answer": "HLS 分片时长（`targetduration`）直接决定直播端到端延迟的下限。\n\n- 分片越短（如 2 s）：播放器能更快拿到新内容，延迟可降至 6–10 s（3 个分片缓冲），但 CDN 回源频率和 manifest 刷新压力成倍增加。\n- 分片越长（如 10 s）：CDN 压力小，但延迟随之升高至 30 s 以上。\n\nApple 推荐直播场景使用 2–4 s 分片，点播使用 6 s。Low-Latency HLS（LLHLS）通过部分分片（`EXT-X-PART`）将延迟进一步压缩至 2–3 s。",
  "sources": ["rag"],
  "route": "rag",
  "session_id": "user-abc-session-01"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | Generated answer from Claude. May contain Markdown formatting. |
| `sources` | array of string | Which tools were invoked: `["rag"]`, `["web"]`, or `[]` (direct generation). |
| `route` | string | Routing decision made by the router node: `"rag"`, `"web"`, or `"direct"`. |
| `session_id` | string | Echo of the request session_id. |

### Error Codes

| Code | Condition |
|------|-----------|
| `422 Unprocessable Entity` | `query` is empty, exceeds 2000 characters, or request body is malformed. |
| `500 Internal Server Error` | LangGraph Agent execution failed (Claude API error, retriever error, etc.). Body: `{"detail": "处理失败: <error message>"}` |

---

## GET /api/v1/docs-list

List all documents that have been uploaded and indexed in the current process. Note: the registry is in-memory and resets on server restart.

### Request

No parameters.

### Response `200 OK`

```json
{
  "docs": [
    {
      "doc_id": "a3f7c912",
      "filename": "hls-spec.pdf",
      "chunk_count": 47
    },
    {
      "doc_id": "b81e2f04",
      "filename": "h265-encoding-guide.md",
      "chunk_count": 23
    }
  ],
  "total": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `docs` | array | List of uploaded document metadata. Empty array `[]` if no documents have been uploaded. |
| `docs[].doc_id` | string | Document identifier (same as returned by `/upload`). |
| `docs[].filename` | string | Original upload filename. |
| `docs[].chunk_count` | integer | Number of chunks in the vector store for this document. |
| `total` | integer | Total number of documents. |

### Error Codes

This endpoint does not return errors under normal conditions.

---

## GET /api/v1/health

Service health check. Reports whether the embedding model is loaded and how many chunks are in the vector store.

### Request

No parameters.

### Response `200 OK` — healthy

```json
{
  "status": "ok",
  "vector_store_count": 70,
  "embedding_model_loaded": true
}
```

### Response `200 OK` — degraded (vector store unreachable)

```json
{
  "status": "ok",
  "vector_store_count": -1,
  "embedding_model_loaded": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Always `"ok"` when the server is reachable. |
| `vector_store_count` | integer | Number of chunks in ChromaDB collection `video_tech_docs`. `-1` indicates ChromaDB could not be queried. |
| `embedding_model_loaded` | boolean | Whether `BGEEmbedder._model` is non-null (i.e., BGE-M3 has been loaded into memory). `false` means the first upload or chat request will trigger a cold load (~20 s). |

### Error Codes

| Code | Condition |
|------|-----------|
| `500 Internal Server Error` | Unexpected server-side exception (should not occur in normal operation). |
