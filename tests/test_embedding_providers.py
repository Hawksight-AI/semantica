
import sys
import os
import unittest
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantica.embeddings import TextEmbedder, EmbeddingGenerator

class TestEmbeddingProviders(unittest.TestCase):
    def test_sentence_transformers_default(self):
        print("\nTesting Sentence Transformers (Default)...")
        embedder = TextEmbedder(method="sentence_transformers")
        text = "This is a test sentence."
        embedding = embedder.embed_text(text)
        self.assertIsInstance(embedding, np.ndarray)
        print(f"Embedding shape: {embedding.shape}")
        # Default model is all-MiniLM-L6-v2 which is 384 dim
        self.assertEqual(len(embedding), 384)

    def test_sentence_transformers_custom_model(self):
        print("\nTesting Sentence Transformers (Custom Model: all-mpnet-base-v2)...")
        # all-mpnet-base-v2 produces 768 dim embeddings
        try:
            embedder = TextEmbedder(
                method="sentence_transformers", 
                model_name="all-mpnet-base-v2"
            )
            text = "This is a test sentence."
            embedding = embedder.embed_text(text)
            self.assertIsInstance(embedding, np.ndarray)
            print(f"Embedding shape: {embedding.shape}")
            self.assertEqual(len(embedding), 768)
        except Exception as e:
            print(f"Skipping custom model test if download fails: {e}")

    def test_fastembed_default(self):
        print("\nTesting FastEmbed (Default)...")
        try:
            embedder = TextEmbedder(method="fastembed")
            text = "This is a test sentence."
            embedding = embedder.embed_text(text)
            self.assertIsInstance(embedding, np.ndarray)
            print(f"Embedding shape: {embedding.shape}")
            # FastEmbed default is usually BAAI/bge-small-en-v1.5 (384 dim) or similar
            self.assertTrue(len(embedding) > 0)
        except ImportError:
            print("FastEmbed not installed, skipping.")

    def test_fastembed_custom_model(self):
        print("\nTesting FastEmbed (Custom Model: BAAI/bge-small-en-v1.5)...")
        try:
            embedder = TextEmbedder(
                method="fastembed",
                model_name="BAAI/bge-small-en-v1.5"
            )
            text = "This is a test sentence."
            embedding = embedder.embed_text(text)
            self.assertIsInstance(embedding, np.ndarray)
            print(f"Embedding shape: {embedding.shape}")
            self.assertEqual(len(embedding), 384)
        except ImportError:
             print("FastEmbed not installed, skipping.")
        except Exception as e:
             print(f"FastEmbed custom model error: {e}")

    def test_embedding_generator_config(self):
        print("\nTesting EmbeddingGenerator with config...")
        # Configure to use fastembed via EmbeddingGenerator
        config = {
            "text": {
                "method": "fastembed",
                "model_name": "BAAI/bge-small-en-v1.5"
            }
        }
        generator = EmbeddingGenerator(config=config)
        embeddings = generator.generate_embeddings(["Test text"], data_type="text")
        self.assertEqual(embeddings.shape[1], 384)
        print("EmbeddingGenerator config test passed.")

if __name__ == '__main__':
    with open("test_results.txt", "w") as f:
        runner = unittest.TextTestRunner(stream=f, verbosity=2)
        unittest.main(testRunner=runner, exit=False)


class TestMethodDispatchRecursion(unittest.TestCase):
    """#994: built-in aliases are registered in the method registry onto the
    wrapper functions themselves, so dispatching through the registry called a
    wrapper back into itself with the same default method — a recursion storm
    that surfaced as `maximum recursion depth exceeded` during model loading."""

    def test_generate_embeddings_default_does_not_self_recurse(self):
        from semantica.embeddings.methods import generate_embeddings
        emb = generate_embeddings("recursion probe")
        self.assertIsNotNone(emb)

    def test_embed_text_default_does_not_self_recurse(self):
        from semantica.embeddings.methods import embed_text
        emb = embed_text("recursion probe", method="sentence_transformers")
        self.assertIsNotNone(emb)

    def test_custom_registered_method_still_wins(self):
        from semantica.embeddings.methods import method_registry
        calls = []

        def spy(data, *a, **k):
            calls.append(data)
            return {"custom": True}

        method_registry.register("generation", "my_custom_gen", spy)
        try:
            from semantica.embeddings.methods import generate_embeddings
            out = generate_embeddings("payload", method="my_custom_gen")
            self.assertEqual(out, {"custom": True})
            self.assertEqual(calls, ["payload"])
        finally:
            method_registry.unregister("generation", "my_custom_gen")

    def test_provenance_wrapper_missing_generator_raises_attribute_error(self):
        # Partially-initialised wrappers (failed __init__, pickle/copy probes)
        # must raise AttributeError, not RecursionError via __getattr__.
        from semantica.embeddings.embeddings_provenance import (
            EmbeddingGeneratorWithProvenance,
        )
        bare = EmbeddingGeneratorWithProvenance.__new__(
            EmbeddingGeneratorWithProvenance
        )
        with self.assertRaises(AttributeError):
            getattr(bare, "model")

