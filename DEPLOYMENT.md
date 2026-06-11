# 部署说明

## 后端（Render）

1. Fork/Push 到 GitHub
2. 在 [render.com](https://render.com) 新建 Web Service
3. 连接 GitHub 仓库
4. 配置环境变量：
   - `ZHIPU_API_KEY=your_zhipu_key`
   - `EMBEDDING_MODEL=api`（使用 Zhipu API embedding，无需下载本地模型）
   - `HF_HUB_DISABLE_XET=1`
5. Build Command: `pip install -r requirements.txt`
6. Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
7. 添加 Persistent Disk，挂载到 `/data`（用于 ChromaDB 持久化）

首次启动会自动加载 data/docs/ 下的内置文档到知识库。

## 前端（Vercel）

1. 在 [vercel.com](https://vercel.com) 导入 GitHub 仓库
2. Framework: Next.js，Root Directory: `frontend`
3. 环境变量：
   - `NEXT_PUBLIC_API_URL=https://your-render-service.onrender.com`
4. Deploy

## 本地开发

```bash
# 使用本地 BGE-M3（高质量，需 4.3GB 模型）
EMBEDDING_MODEL=local make dev

# 使用 Zhipu API（轻量级，无需下载模型）
EMBEDDING_MODEL=api make dev
```

## 环境差异

| 特性 | 本地 | 部署 |
|------|------|------|
| Embedding | BGE-M3（本地，高精度）| Zhipu API（零部署成本）|
| ChromaDB | 本地持久化 | Render Disk 持久化 |
| 知识库加载 | 手动上传 | 启动时自动加载 |
