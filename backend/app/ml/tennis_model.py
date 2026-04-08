"""
Tennis match outcome prediction model.

Uses logistic regression trained on pre-computed TennisPlayerFeatures snapshots.
Surface-aware: the surface win % feature is selected based on the actual match surface.

Key design decision: tennis has no home/away advantage, so during training we
randomly assign which player is p1/p2 to prevent the model from learning a
positional bias from how ESPN orders competitors.

Safe features (computed from historical match data):
    form_score_5, form_score_10, overall_win_pct, recent_win_pct,
    win_pct_{surface}, matches_{surface}, ranking

Split: time-ordered 80/20 to avoid leaking future results into training.
"""

import random
import joblib
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from app.models.tennis import TennisMatch, TennisPlayer, TennisPlayerFeatures

MODEL_PATH = Path(__file__).parent / "tennis_model.pkl"

SURFACE_WIN_PCT = {"Hard": "win_pct_hard", "Clay": "win_pct_clay", "Grass": "win_pct_grass"}
SURFACE_MATCHES = {"Hard": "matches_hard", "Clay": "matches_clay", "Grass": "matches_grass"}

FEATURES = [
    "form_5_diff",
    "form_10_diff",
    "overall_win_pct_diff",
    "recent_win_pct_diff",
    "surface_win_pct_diff",
    "surface_matches_diff",
    "ranking_diff",
]


def _feature_row(
    p1: TennisPlayerFeatures,
    p2: TennisPlayerFeatures,
    p1_player: TennisPlayer,
    p2_player: TennisPlayer,
    surface: str,
) -> dict | None:
    """
    Build a feature dict from a p1/p2 TennisPlayerFeatures pair.
    All diffs are p1 - p2, so positive values favour p1.
    Returns None if any required field is missing.
    """
    surface_pct_field = SURFACE_WIN_PCT.get(surface)
    surface_cnt_field = SURFACE_MATCHES.get(surface)

    required = [
        p1.form_score_5, p1.form_score_10, p1.overall_win_pct, p1.recent_win_pct,
        p2.form_score_5, p2.form_score_10, p2.overall_win_pct, p2.recent_win_pct,
    ]
    if any(v is None for v in required):
        return None

    # Surface win % — fall back to overall_win_pct if no surface data yet.
    p1_surface_pct = (getattr(p1, surface_pct_field) if surface_pct_field else None) or p1.overall_win_pct
    p2_surface_pct = (getattr(p2, surface_pct_field) if surface_pct_field else None) or p2.overall_win_pct
    p1_surface_cnt = (getattr(p1, surface_cnt_field) if surface_cnt_field else None) or 0
    p2_surface_cnt = (getattr(p2, surface_cnt_field) if surface_cnt_field else None) or 0

    # Ranking: lower is better, so p2.ranking - p1.ranking is positive when p1 is better ranked.
    # Default to 500 (unranked) if missing.
    p1_rank = p1_player.ranking or 500
    p2_rank = p2_player.ranking or 500

    return {
        "form_5_diff": p1.form_score_5 - p2.form_score_5,
        "form_10_diff": p1.form_score_10 - p2.form_score_10,
        "overall_win_pct_diff": p1.overall_win_pct - p2.overall_win_pct,
        "recent_win_pct_diff": p1.recent_win_pct - p2.recent_win_pct,
        "surface_win_pct_diff": p1_surface_pct - p2_surface_pct,
        "surface_matches_diff": p1_surface_cnt - p2_surface_cnt,
        "ranking_diff": p2_rank - p1_rank,
    }


def build_training_data(tour: str, db: Session) -> tuple[list[dict], list[int]]:
    """
    Join completed matches with TennisPlayerFeatures snapshots.
    Randomly assigns p1/p2 each match to avoid positional bias.
    Returns (X_rows, y) ordered by date for time-ordered splitting.
    """
    matches = (
        db.query(TennisMatch)
        .filter(
            TennisMatch.tour == tour,
            TennisMatch.status == "Final",
            TennisMatch.winner_id.isnot(None),
            TennisMatch.surface.isnot(None),
        )
        .order_by(TennisMatch.date.asc())
        .all()
    )

    X_rows, y = [], []
    skipped = 0
    rng = random.Random(42)

    for m in matches:
        match_date = m.date.date() if isinstance(m.date, datetime) else m.date

        # Randomly assign p1/p2 to remove positional bias.
        if rng.random() < 0.5:
            pid1, pid2 = m.player1_id, m.player2_id
        else:
            pid1, pid2 = m.player2_id, m.player1_id

        p1_feat = (
            db.query(TennisPlayerFeatures)
            .filter(TennisPlayerFeatures.player_id == pid1, TennisPlayerFeatures.date == match_date)
            .first()
        )
        p2_feat = (
            db.query(TennisPlayerFeatures)
            .filter(TennisPlayerFeatures.player_id == pid2, TennisPlayerFeatures.date == match_date)
            .first()
        )

        if not p1_feat or not p2_feat:
            skipped += 1
            continue

        p1_player = db.get(TennisPlayer, pid1)
        p2_player = db.get(TennisPlayer, pid2)
        if not p1_player or not p2_player:
            skipped += 1
            continue

        row = _feature_row(p1_feat, p2_feat, p1_player, p2_player, m.surface)
        if row is None:
            skipped += 1
            continue

        X_rows.append(row)
        y.append(1 if m.winner_id == pid1 else 0)

    print(f"Tennis training data [{tour.upper()}]: {len(X_rows)} matches used, {skipped} skipped")
    return X_rows, y


def train(tour: str, db: Session) -> dict:
    """
    Train a logistic regression model for a given tour.
    Saves the pipeline to MODEL_PATH (keyed by tour).
    """
    X_rows, y = build_training_data(tour, db)

    if len(X_rows) < 50:
        raise ValueError(f"Not enough training data: only {len(X_rows)} matches for {tour.upper()}")

    split = int(len(X_rows) * 0.8)
    X_train_rows, X_test_rows = X_rows[:split], X_rows[split:]
    y_train, y_test = y[:split], y[split:]

    X_train = [[row[f] for f in FEATURES] for row in X_train_rows]
    X_test = [[row[f] for f in FEATURES] for row in X_test_rows]

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, random_state=42)),
    ])
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)

    metrics = {
        "tour": tour.upper(),
        "train_matches": len(X_train),
        "test_matches": len(X_test),
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "log_loss": round(log_loss(y_test, y_prob), 4),
    }

    # Load existing artifact (other tour's model) if present, then update.
    artifact = {}
    if MODEL_PATH.exists():
        artifact = joblib.load(MODEL_PATH)

    artifact[tour] = {"pipeline": pipeline, "features": FEATURES, "metrics": metrics}
    joblib.dump(artifact, MODEL_PATH)

    print(f"Tennis model [{tour.upper()}] trained — accuracy: {metrics['accuracy']}, log_loss: {metrics['log_loss']}")
    print(f"Model saved to {MODEL_PATH}")
    return metrics


def predict(
    player1_id: str,
    player2_id: str,
    surface: str,
    tour: str,
    as_of: date,
    db: Session,
) -> dict:
    """
    Predict the outcome of a tennis match between player1 and player2 on a given surface.
    Returns win probability for each player.
    """
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Tennis model has not been trained yet. POST /admin/train/tennis first.")

    artifact = joblib.load(MODEL_PATH)
    if tour not in artifact:
        raise FileNotFoundError(f"No trained model for {tour.upper()}. POST /admin/train/tennis?tour={tour} first.")

    pipeline = artifact[tour]["pipeline"]

    p1_feat = (
        db.query(TennisPlayerFeatures)
        .filter(TennisPlayerFeatures.player_id == player1_id, TennisPlayerFeatures.date <= as_of)
        .order_by(TennisPlayerFeatures.date.desc())
        .first()
    )
    p2_feat = (
        db.query(TennisPlayerFeatures)
        .filter(TennisPlayerFeatures.player_id == player2_id, TennisPlayerFeatures.date <= as_of)
        .order_by(TennisPlayerFeatures.date.desc())
        .first()
    )

    if not p1_feat:
        raise ValueError(f"No feature snapshot found for player {player1_id}")
    if not p2_feat:
        raise ValueError(f"No feature snapshot found for player {player2_id}")

    p1_player = db.get(TennisPlayer, player1_id)
    p2_player = db.get(TennisPlayer, player2_id)

    row = _feature_row(p1_feat, p2_feat, p1_player, p2_player, surface)
    if row is None:
        raise ValueError("Insufficient feature data for one or both players")

    X = [[row[f] for f in FEATURES]]
    prob_p1_win = float(pipeline.predict_proba(X)[0][1])

    return {
        "player1_id": player1_id,
        "player1_name": p1_player.name,
        "player1_ranking": p1_player.ranking,
        "player2_id": player2_id,
        "player2_name": p2_player.name,
        "player2_ranking": p2_player.ranking,
        "surface": surface,
        "tour": tour.upper(),
        "as_of": as_of.isoformat(),
        "player1_win_probability": round(prob_p1_win, 4),
        "player2_win_probability": round(1 - prob_p1_win, 4),
        "predicted_winner": p1_player.name if prob_p1_win >= 0.5 else p2_player.name,
        "features_used": {k: round(v, 4) for k, v in row.items()},
        "player1_features_date": p1_feat.date.isoformat(),
        "player2_features_date": p2_feat.date.isoformat(),
        "model_metrics": artifact[tour]["metrics"],
    }
