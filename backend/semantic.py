"""Offline sentence embeddings. Never download models during a CV request."""
from pathlib import Path
from threading import Lock
import os

MODEL_PATH = Path(__file__).parent / 'models' / 'all-MiniLM-L6-v2'
_model = None
_lock = Lock()


def local_model():
    global _model
    path = Path(os.getenv('SEMANTIC_MODEL_PATH', str(MODEL_PATH)))
    if not path.is_dir():
        return None
    with _lock:
        if _model is None:
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
            import torch
            torch.set_num_threads(2)
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(str(path), device='cpu', local_files_only=True,
                                         trust_remote_code=False)
            _model.max_seq_length = 128
        return _model


def find_matches(skills, rows, model):
    """Bounded evidence windows retain original source line numbers."""
    from matching import NEGATIVE, UNCERTAIN, PROTECTED, PERSONAL
    windows = []
    for line, text in rows:
        if PERSONAL.match(text) or PROTECTED.search(text) or NEGATIVE.search(text) or UNCERTAIN.search(text):
            continue
        for start in range(0, len(text), 350):
            windows.append((line, text[start:start + 450]))
            if len(windows) >= 256:
                break
        if len(windows) >= 256:
            break
    if not windows or not skills:
        return {}
    # No vectors or CV text are cached or written to disk.
    with _lock:
        vectors = model.encode([f'Experience with {s}' for s in skills] + [t for _, t in windows],
                               normalize_embeddings=True, show_progress_bar=False, batch_size=32)
    matches = {}
    for i, skill in enumerate(skills):
        scores = vectors[len(skills):] @ vectors[i]
        best = int(scores.argmax())
        similarity = float(scores[best])
        if similarity >= 0.60:
            line, quote = windows[best]
            matches[skill] = {'similarity': round(similarity, 4), 'line': line, 'quote': quote}
    return matches
