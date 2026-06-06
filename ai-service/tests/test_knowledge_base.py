import pytest
from unittest.mock import patch, MagicMock

from app.services.knowledge_base import KnowledgeBase


class TestKnowledgeBase:
    @pytest.fixture
    def mock_collection(self):
        coll = MagicMock()
        coll.count.return_value = 0
        coll.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        coll.get.return_value = {"documents": [], "metadatas": []}
        coll.upsert.return_value = None
        return coll

    @pytest.fixture
    def kb(self, mock_collection):
        with patch("chromadb.PersistentClient") as mock_client:
            mock_client.return_value.get_or_create_collection.return_value = mock_collection
            kb = KnowledgeBase(persist_path="./test_chroma", collection_name="test")
            kb.collection = mock_collection
            yield kb

    def test_init(self, kb):
        assert kb.persist_path == "./test_chroma"
        assert kb.collection_name == "test"

    def test_add_documents(self, kb, mock_collection):
        kb.add_documents(["text1", "text2"], [{"s": "a"}, {"s": "b"}], ["id1", "id2"])
        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args.kwargs
        assert call_kwargs["documents"] == ["text1", "text2"]
        assert call_kwargs["ids"] == ["id1", "id2"]

    def test_add_documents_auto_ids(self, kb, mock_collection):
        kb.add_documents(["text1"])
        call_kwargs = mock_collection.upsert.call_args.kwargs
        assert call_kwargs["ids"] == ["doc_0"]

    def test_search_empty_collection(self, kb):
        results = kb.search("query")
        assert results == []

    def test_search_with_results(self, kb, mock_collection):
        mock_collection.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"s": "a"}, {"s": "b"}]],
            "distances": [[0.1, 0.2]],
        }
        results = kb.search("query", top_k=2)
        assert len(results) == 2
        assert results[0]["content"] == "doc1"
        assert results[0]["metadata"] == {"s": "a"}
        assert results[0]["score"] == 0.1

    def test_format_context_empty(self, kb):
        ctx = kb.format_context("query")
        assert ctx == ""

    def test_format_context_with_docs(self, kb, mock_collection):
        mock_collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"s": "a"}]],
            "distances": [[0.1]],
        }
        ctx = kb.format_context("query")
        assert "【参考知识库内容】" in ctx
        assert "[1] doc1" in ctx

    def test_is_empty_true(self, kb, mock_collection):
        mock_collection.count.return_value = 0
        assert kb.is_empty() is True

    def test_is_empty_false(self, kb, mock_collection):
        mock_collection.count.return_value = 5
        assert kb.is_empty() is False

    def test_keyword_fallback(self, kb, mock_collection):
        mock_collection.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        mock_collection.get.return_value = {
            "documents": ["hello world", "foo bar"],
            "metadatas": [{}, {}],
        }
        results = kb.search("hello")
        assert len(results) > 0
        assert results[0]["content"] == "hello world"

    def test_keyword_fallback_no_docs(self, kb, mock_collection):
        mock_collection.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        mock_collection.get.return_value = {"documents": [], "metadatas": []}
        results = kb.search("query")
        assert results == []
