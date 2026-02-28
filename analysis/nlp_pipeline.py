"""
Step 3: Commit message NLP pipeline.

Embeds commit messages using SentenceTransformers (GPU-accelerated),
detects centroid drift between pre- and post-AI eras, and optionally
trains a classifier to distinguish AI-assisted from human-written commits.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    AI_KEYWORDS,
    CONVENTIONAL_PREFIXES,
    DATA_DIR,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    VIZ_DIR,
)


def load_commit_messages(era: str, filepath: Path | None = None) -> pd.DataFrame:
    """Load sampled commit messages for a given era (pre_ai / post_ai)."""
    if filepath is None:
        filepath = DATA_DIR / f"commit_messages_{era}.csv"
    return pd.read_csv(filepath)


def compute_text_features(messages: pd.Series) -> pd.DataFrame:
    """
    Extract lightweight text features from commit messages
    without requiring GPU embeddings.
    """
    conventional_pattern = r"^(" + "|".join(CONVENTIONAL_PREFIXES) + r")(\(.+\))?:"
    ai_keyword_pattern = r"\b(" + "|".join(AI_KEYWORDS) + r")\b"

    features = pd.DataFrame()
    features["message_length"] = messages.str.len()
    features["word_count"] = messages.str.split().str.len()
    features["avg_word_length"] = features["message_length"] / features["word_count"].clip(lower=1)
    features["is_conventional"] = messages.str.match(conventional_pattern, case=False).astype(int)
    features["has_ai_keywords"] = messages.str.contains(ai_keyword_pattern, case=False).astype(int)
    features["line_count"] = messages.str.count(r"\n") + 1
    features["has_issue_ref"] = messages.str.contains(r"#\d+", na=False).astype(int)
    features["starts_with_verb"] = messages.str.match(
        r"^(add|fix|update|remove|refactor|implement|create|delete|move|rename|improve|change|set|use|handle)\b",
        case=False,
    ).astype(int)
    features["capitalized"] = messages.str.match(r"^[A-Z]").astype(int)
    features["ends_with_period"] = messages.str.strip().str.endswith(".").astype(int)

    return features


def embed_messages(messages: list[str], device: str = "cuda") -> np.ndarray:
    """
    Embed commit messages using SentenceTransformers.
    Falls back to CPU if CUDA is unavailable.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers not installed. Run: pip install sentence-transformers")
        raise

    try:
        import torch
        if not torch.cuda.is_available():
            device = "cpu"
            print("CUDA not available, falling back to CPU")
    except ImportError:
        device = "cpu"

    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode(
        messages,
        batch_size=EMBEDDING_BATCH_SIZE,
        device=device,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return embeddings


def compute_centroid_drift(
    embeddings_pre: np.ndarray,
    embeddings_post: np.ndarray,
) -> dict:
    """
    Measure how the "average commit message" changed between eras.

    Returns cosine distance, L2 distance, and per-dimension statistics.
    """
    centroid_pre = embeddings_pre.mean(axis=0)
    centroid_post = embeddings_post.mean(axis=0)

    # L2 distance
    l2_dist = float(np.linalg.norm(centroid_post - centroid_pre))

    # Cosine similarity (embeddings are normalised, so dot product = cosine sim)
    cosine_sim = float(np.dot(centroid_pre, centroid_post))
    cosine_dist = 1.0 - cosine_sim

    # Per-dimension drift (which embedding dimensions shifted most?)
    dim_drift = centroid_post - centroid_pre
    top_drift_dims = np.argsort(np.abs(dim_drift))[-10:][::-1]

    return {
        "l2_distance": l2_dist,
        "cosine_distance": cosine_dist,
        "cosine_similarity": cosine_sim,
        "top_drift_dimensions": top_drift_dims.tolist(),
        "top_drift_magnitudes": dim_drift[top_drift_dims].tolist(),
    }


def train_era_classifier(
    embeddings_pre: np.ndarray,
    embeddings_post: np.ndarray,
) -> dict:
    """
    Train a logistic regression to distinguish pre-AI from post-AI commit messages.

    If the classifier achieves high AUC, the message distributions are
    meaningfully different — supporting the AI-adoption hypothesis.
    """
    X = np.vstack([embeddings_pre, embeddings_post])
    y = np.array([0] * len(embeddings_pre) + [1] * len(embeddings_post))

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    clf = LogisticRegression(max_iter=1000, random_state=42)
    clf.fit(X_train_scaled, y_train)

    y_pred = clf.predict(X_test_scaled)
    y_proba = clf.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_proba)
    report = classification_report(y_test, y_pred, output_dict=True)

    return {
        "auc_roc": float(auc),
        "accuracy": float(report["accuracy"]),
        "precision_post_ai": float(report["1"]["precision"]),
        "recall_post_ai": float(report["1"]["recall"]),
        "f1_post_ai": float(report["1"]["f1-score"]),
        "interpretation": (
            "HIGH separability (AUC > 0.8): commit messages changed significantly"
            if auc > 0.8 else
            "MODERATE separability (0.6-0.8): some detectable change in messages"
            if auc > 0.6 else
            "LOW separability (AUC < 0.6): messages haven't changed much"
        ),
    }


def analyse_text_features(filepath_pre: Path | None = None, filepath_post: Path | None = None) -> dict:
    """
    Run text feature analysis (no GPU required).
    Compares distributions of hand-crafted features between eras.
    """
    df_pre = load_commit_messages("pre_ai", filepath_pre)
    df_post = load_commit_messages("post_ai", filepath_post)

    feat_pre = compute_text_features(df_pre["commit_message"].fillna(""))
    feat_post = compute_text_features(df_post["commit_message"].fillna(""))

    results = {}
    for col in feat_pre.columns:
        from scipy.stats import mannwhitneyu
        stat, pval = mannwhitneyu(
            feat_pre[col].dropna(), feat_post[col].dropna(), alternative="two-sided",
        )
        results[col] = {
            "pre_mean": float(feat_pre[col].mean()),
            "post_mean": float(feat_post[col].mean()),
            "percent_change": float(
                (feat_post[col].mean() - feat_pre[col].mean())
                / max(feat_pre[col].mean(), 1e-10) * 100
            ),
            "mann_whitney_u": float(stat),
            "p_value": float(pval),
            "significant": pval < 0.05,
        }

    return results


def analyse_embeddings(
    filepath_pre: Path | None = None,
    filepath_post: Path | None = None,
    device: str = "cuda",
) -> dict:
    """
    Full embedding-based NLP analysis (requires GPU for speed).
    """
    df_pre = load_commit_messages("pre_ai", filepath_pre)
    df_post = load_commit_messages("post_ai", filepath_post)

    messages_pre = df_pre["commit_message"].fillna("").tolist()
    messages_post = df_post["commit_message"].fillna("").tolist()

    print(f"Embedding {len(messages_pre)} pre-AI messages...")
    emb_pre = embed_messages(messages_pre, device=device)

    print(f"Embedding {len(messages_post)} post-AI messages...")
    emb_post = embed_messages(messages_post, device=device)

    print("Computing centroid drift...")
    drift = compute_centroid_drift(emb_pre, emb_post)

    print("Training era classifier...")
    classifier = train_era_classifier(emb_pre, emb_post)

    return {
        "centroid_drift": drift,
        "era_classifier": classifier,
        "n_pre": len(messages_pre),
        "n_post": len(messages_post),
    }


def print_report(results: dict, mode: str = "text_features") -> None:
    """Print analysis report."""
    print("=" * 60)
    print(f"NLP ANALYSIS REPORT ({mode})")
    print("=" * 60)

    if mode == "text_features":
        for feature, stats in results.items():
            sig = "*" if stats["significant"] else " "
            print(
                f"  {sig} {feature:25s}: "
                f"pre={stats['pre_mean']:.2f} → post={stats['post_mean']:.2f} "
                f"({stats['percent_change']:+.1f}%, p={stats['p_value']:.4f})"
            )
    elif mode == "embeddings":
        drift = results["centroid_drift"]
        clf = results["era_classifier"]
        print(f"  Messages: {results['n_pre']} pre-AI, {results['n_post']} post-AI")
        print(f"  Centroid L2 drift:      {drift['l2_distance']:.4f}")
        print(f"  Centroid cosine dist:   {drift['cosine_distance']:.4f}")
        print(f"  Era classifier AUC:     {clf['auc_roc']:.3f}")
        print(f"  Interpretation:         {clf['interpretation']}")

    print("=" * 60)


if __name__ == "__main__":
    # Generate synthetic commit messages for demonstration
    pre_file = DATA_DIR / "commit_messages_pre_ai.csv"
    post_file = DATA_DIR / "commit_messages_post_ai.csv"

    if not pre_file.exists() or not post_file.exists():
        print("Generating synthetic commit message data for demonstration...")
        np.random.seed(42)
        n = 10_000

        # Pre-AI: shorter, less conventional, more terse
        pre_templates = [
            "fix bug", "update code", "changes", "wip", "stuff",
            "fixed issue", "updated file", "minor fix", "cleanup",
            "bugfix", "added feature", "removed unused code",
            "Merge branch 'main'", "initial commit", "v1.0",
        ]
        pre_messages = [
            pre_templates[i % len(pre_templates)] + f" #{np.random.randint(1, 500)}"
            for i in range(n)
        ]

        # Post-AI: longer, more conventional, more descriptive
        post_templates = [
            "feat: add user authentication with JWT tokens",
            "fix: resolve null pointer exception in payment processing",
            "refactor: extract validation logic into separate module",
            "docs: update API documentation with new endpoints",
            "chore: update dependencies to latest versions",
            "fix: handle edge case in date parsing for timezone-aware inputs",
            "feat: implement rate limiting middleware with Redis backend",
            "refactor: simplify error handling across API routes",
            "test: add integration tests for user registration flow",
            "perf: optimize database queries with proper indexing",
        ]
        post_messages = [
            post_templates[i % len(post_templates)]
            for i in range(n)
        ]

        pd.DataFrame({
            "commit_message": pre_messages,
            "era": "pre_ai",
        }).to_csv(pre_file, index=False)

        pd.DataFrame({
            "commit_message": post_messages,
            "era": "post_ai",
        }).to_csv(post_file, index=False)

        print(f"Synthetic data written to {pre_file} and {post_file}")

    # Text feature analysis (no GPU needed)
    results = analyse_text_features()
    print_report(results, mode="text_features")
