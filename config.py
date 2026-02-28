"""Configuration constants for the GitHub Explosion analysis pipeline."""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
QUERIES_DIR = PROJECT_ROOT / "queries"
VIZ_DIR = PROJECT_ROOT / "visualizations"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
VIZ_DIR.mkdir(exist_ok=True)

# BigQuery settings
BQ_PROJECT = None  # Set via env var GOOGLE_CLOUD_PROJECT or override here
BQ_DATASET = "githubarchive.month"
BQ_FREE_TIER_BYTES = 1_000_000_000_000  # 1TB/month

# Time boundaries
ANALYSIS_START = "2020-01"
ANALYSIS_END = "2025-08"
CHATGPT_LAUNCH = "2022-11"  # The hypothesised inflection point
COPILOT_GA = "2022-06"  # Copilot general availability

# NLP settings
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE = 512
COMMIT_MESSAGE_SAMPLE_SIZE = 500_000

# Changepoint detection
CHANGEPOINT_PENALTY = 3  # Pelt algorithm penalty parameter
CHANGEPOINT_MODEL = "rbf"  # Radial basis function kernel

# Commit message AI-indicator keywords
AI_KEYWORDS = [
    "refactor", "implement", "add support for", "update dependencies",
    "fix typo", "improve", "optimize", "enhance", "restructure",
    "modularize", "streamline",
]

# Conventional commit prefixes
CONVENTIONAL_PREFIXES = [
    "feat", "fix", "chore", "docs", "style", "refactor",
    "perf", "test", "build", "ci", "revert",
]

# Top languages to analyse
TARGET_LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Java",
    "C++", "C", "Go", "Rust",
]

# Visualisation
FIGURE_DPI = 150
FIGURE_SIZE = (14, 8)
COLOR_PRE_AI = "#2196F3"   # Blue
COLOR_POST_AI = "#FF5722"  # Orange
COLOR_TRANSITION = "#9E9E9E"  # Grey
ANNOTATION_COLOR = "#E91E63"  # Pink for key date markers
