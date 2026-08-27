import ollama
import numpy as np

EMBED_MODEL = "nomic-embed-text"

# Predefined reference intents
INTENT_EXAMPLES = {
    "qwen2.5-coder:7b-instruct-q4_K_M": [
        "write a python script",
        "debug this code function",
        "calculate algorithm implementation in python",
        "execute script to calculate mathematical formula"
    ],
    "qwen2.5vl:7b": [
        "analyze this image diagram",
        "read the text in this scanned photo",
        "extract text from handwritten note picture",
        "inspect piping and instrument diagram drawing"
    ],
    "qwen2.5:7b-instruct-q4_K_M": [
        "summarize this inspection report into word document",
        "generate executive report document",
        "extract bullet points from maintenance log",
        "general conversational query and explanation"
    ]
}

# Cache anchor embeddings at module load
ANCHOR_EMBEDDINGS = {}

def _init_anchors():
    global ANCHOR_EMBEDDINGS
    if not ANCHOR_EMBEDDINGS:
        for model_tag, examples in INTENT_EXAMPLES.items():
            vectors = []
            for text in examples:
                res = ollama.embeddings(model=EMBED_MODEL, prompt=text)
                vectors.append(res["embedding"])
            # Compute centroid vector for each model category
            ANCHOR_EMBEDDINGS[model_tag] = np.mean(vectors, axis=0)

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_target_model(prompt: str) -> str:
    """Classifies user intent using vector similarity against anchor embeddings."""
    try:
        _init_anchors()
        res = ollama.embeddings(model=EMBED_MODEL, prompt=prompt)
        query_vec = np.array(res["embedding"])

        best_model = "qwen2.5:7b-instruct-q4_K_M"
        highest_score = -1.0

        for model_tag, anchor_vec in ANCHOR_EMBEDDINGS.items():
            score = cosine_similarity(query_vec, anchor_vec)
            if score > highest_score:
                highest_score = score
                best_model = model_tag

        return best_model
    except Exception as e:
        # Fallback to rule-based classification if embedding engine fails
        prompt_lower = prompt.lower()
        if any(w in prompt_lower for w in ["code", "python", "script"]):
            return "qwen2.5-coder:7b-instruct-q4_K_M"
        elif any(w in prompt_lower for w in ["image", "picture", "scan"]):
            return "qwen2.5vl:7b"
        return "qwen2.5:7b-instruct-q4_K_M"