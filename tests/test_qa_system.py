import unittest

from video_ai_assistant import VideoChunk, VideoKnowledgeBase, VideoRAGLangGraphAgent


class VideoQASystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kb = VideoKnowledgeBase()
        self.kb.add_chunks(
            [
                VideoChunk(
                    video_id="intro-transformers",
                    timestamp="00:00:25",
                    text="Transformers use self-attention to model long-range dependencies.",
                ),
                VideoChunk(
                    video_id="retrieval-basics",
                    timestamp="00:01:10",
                    text="Retrieval augmented generation combines search with language models.",
                ),
            ]
        )

    def test_retrieve_returns_relevant_chunk_for_query(self):
        results = self.kb.retrieve("What is self-attention?", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].video_id, "intro-transformers")

    def test_agent_generates_answer_with_source_citation(self):
        agent = VideoRAGLangGraphAgent(self.kb)
        response = agent.ask("How does retrieval augmented generation work?", top_k=2)

        self.assertIn("retrieval-basics@00:01:10", response["answer"])
        self.assertEqual(response["question"], "How does retrieval augmented generation work?")
        self.assertGreaterEqual(len(response["context"]), 1)

    def test_agent_handles_missing_context(self):
        agent = VideoRAGLangGraphAgent(VideoKnowledgeBase())
        response = agent.ask("Question with no data")
        self.assertEqual(
            response["answer"],
            "I could not find relevant video context for this question.",
        )
        self.assertEqual(response["context"], [])


if __name__ == "__main__":
    unittest.main()
