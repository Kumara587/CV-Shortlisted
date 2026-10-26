"""Explicit model download; does not read candidate data."""
from sentence_transformers import SentenceTransformer
from semantic import MODEL_PATH

if __name__ == '__main__':
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu',
                                trust_remote_code=False)
    model.save(str(MODEL_PATH))
    print(f'Local semantic model ready: {MODEL_PATH}')
