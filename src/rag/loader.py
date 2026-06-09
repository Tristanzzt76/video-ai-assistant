import logging
from pathlib import Path
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document

logger = logging.getLogger(__name__)

class DocumentLoader:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def load_file(self, file_path: str) -> list[Document]:
        """加载单个 PDF 或 Markdown 文件，返回切片后的 Document 列表。"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        reader = SimpleDirectoryReader(input_files=[str(path)])
        docs = reader.load_data()
        nodes = self.splitter.get_nodes_from_documents(docs)
        # 把 node 转成 Document（保留 text 和 metadata）
        result = [
            Document(text=n.text, metadata={**n.metadata, "source": str(path.name)})
            for n in nodes
        ]
        logger.info(f"加载 {path.name}：{len(result)} 个 chunk")
        return result

    def load_directory(self, dir_path: str) -> list[Document]:
        """加载目录下所有 PDF 和 Markdown 文件。"""
        path = Path(dir_path)
        if not path.exists():
            logger.warning(f"目录不存在: {dir_path}，返回空列表")
            return []
        reader = SimpleDirectoryReader(
            input_dir=str(path),
            required_exts=[".pdf", ".md", ".txt"],
            recursive=True,
        )
        try:
            docs = reader.load_data()
        except Exception as e:
            logger.error(f"加载目录失败: {e}")
            return []
        nodes = self.splitter.get_nodes_from_documents(docs)
        result = [
            Document(text=n.text, metadata={**n.metadata, "source": n.metadata.get("file_name", "unknown")})
            for n in nodes
        ]
        logger.info(f"加载目录 {dir_path}：{len(result)} 个 chunk，来自 {len(docs)} 个文件")
        return result
