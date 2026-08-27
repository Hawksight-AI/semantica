import unittest
from unittest.mock import MagicMock, patch
from semantica.split.splitter import TextSplitter
from semantica.split.semantic_chunker import SemanticChunker, Chunk

class TestSplitter(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()
        self.logger_patcher = patch('semantica.split.splitter.get_logger', return_value=self.mock_logger)
        self.logger_patcher_sc = patch('semantica.split.semantic_chunker.get_logger', return_value=self.mock_logger)
        self.tracker_patcher = patch('semantica.split.semantic_chunker.get_progress_tracker', return_value=MagicMock())
        
        self.logger_patcher.start()
        self.logger_patcher_sc.start()
        self.tracker_patcher.start()

    def tearDown(self):
        self.logger_patcher.stop()
        self.logger_patcher_sc.stop()
        self.tracker_patcher.stop()

    def test_text_splitter_initialization(self):
        splitter = TextSplitter(method="recursive", chunk_size=500, chunk_overlap=50)
        self.assertEqual(splitter.chunk_size, 500)
        self.assertEqual(splitter.chunk_overlap, 50)
        self.assertEqual(splitter.methods, ["recursive"])

    def test_text_splitter_list_methods(self):
        splitter = TextSplitter(method=["recursive", "token"])
        self.assertEqual(splitter.methods, ["recursive", "token"])

    @patch('semantica.semantic_extract.methods.spacy')
    def test_semantic_chunker_initialization(self, mock_spacy):
        # SemanticChunker now loads spaCy through the centralized
        # load_spacy_model() in semantic_extract.methods, so we patch
        # methods.spacy rather than the removed semantic_chunker.spacy binding.
        mock_nlp = MagicMock()
        mock_spacy.load.return_value = mock_nlp

        with patch('semantica.split.semantic_chunker.SPACY_AVAILABLE', True):
            chunker = SemanticChunker(chunk_size=100)
        self.assertEqual(chunker.chunk_size, 100)

    def test_chunk_dataclass(self):
        chunk = Chunk(text="test", start_index=0, end_index=4, metadata={"key": "value"})
        self.assertEqual(chunk.text, "test")
        self.assertEqual(chunk.metadata["key"], "value")

if __name__ == '__main__':
    unittest.main()
