"""Configuration module for Datasheet Q&A Tool."""

from dotenv import load_dotenv
load_dotenv()

import json
import os
from pathlib import Path

import platformdirs

# LLM Configuration
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model selection
LLM_MODELS = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}
DEFAULT_MODEL_KEY = "sonnet"

# Pricing (USD per 1K tokens)
# Sonnet: $3/MTok input, $15/MTok output = $0.003/1K in, $0.015/1K out
# Haiku: $1/MTok input, $5/MTok output = $0.001/1K in, $0.005/1K out
PRICING = {
    "sonnet": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "haiku": {"input_per_1k": 0.001, "output_per_1k": 0.005},
}

# Project directory
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Data directory
DATA_DIR = Path(platformdirs.user_data_dir("datasheet-qa"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Logging configuration
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "datasheet-qa.log"
LOG_MAX_BACKUPS = 7

# Chunking configuration
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150

# Embedding configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Retrieval configuration
RETRIEVAL_K = 8

# Input validation
MAX_QUESTION_LENGTH = 5000

# Upload configuration
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_DIR = PROJECT_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Model config persistence
MODEL_CONFIG_FILE = DATA_DIR / "model_config.json"


def _load_model_config() -> str:
    """Load persisted model key, or return default if file missing."""
    if MODEL_CONFIG_FILE.exists():
        try:
            with open(MODEL_CONFIG_FILE) as f:
                data = json.load(f)
            key = data.get("model_key", DEFAULT_MODEL_KEY)
            if key in LLM_MODELS:
                return key
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_MODEL_KEY


def save_model_config(model_key: str) -> None:
    """Persist model key selection to DATA_DIR."""
    if model_key not in LLM_MODELS:
        raise ValueError(f"Unknown model key: {model_key}")
    with open(MODEL_CONFIG_FILE, "w") as f:
        json.dump({"model_key": model_key}, f)


def compute_cost_usd(model_key: str, input_tokens: int, output_tokens: int) -> float:
    """Compute estimated cost in USD for given token counts and model key."""
    rates = PRICING.get(model_key, PRICING[DEFAULT_MODEL_KEY])
    input_cost = (input_tokens / 1000) * rates["input_per_1k"]
    output_cost = (output_tokens / 1000) * rates["output_per_1k"]
    return input_cost + output_cost


# Load persisted model selection at import time
LLM_MODEL_KEY = _load_model_config()
LLM_MODEL = LLM_MODELS[LLM_MODEL_KEY]