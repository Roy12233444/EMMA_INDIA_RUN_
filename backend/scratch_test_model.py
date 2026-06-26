import sys
import logging

logging.basicConfig(level=logging.INFO)
print("Python Version:", sys.version)

try:
    print("Importing sentence_transformers...")
    from sentence_transformers import SentenceTransformer
    print("Successfully imported!")
    
    print("Loading all-MiniLM-L6-v2 model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Successfully loaded model!")
    
    print("Testing embedding computation...")
    vector = model.encode("Test string", normalize_embeddings=True)
    print("Embedding vector dimensions:", len(vector))
    print("Success!")
except Exception as exc:
    print("FAILED with exception:", exc)
    import traceback
    traceback.print_exc()
