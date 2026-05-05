"""
NBA game outcome prediction model.

Uses gradient boosting trained on pre-computed TeamFeatures snapshots.
For each completed game, features are the difference between the home and
away team's snapshot on that game date (home - away), so a positive value
always favours the home team.

Safe features (computed from historical match data):
    form_score_5, form_score_10, avg_points_scored, avg_points_allowed,
    win_pct_home, win_pct_away, off_rating, def_rating

Current-snapshot features (minor leakage risk — stable season-over-season):
    injury_impact (importance-weighted by player PPG tier; only injuries
    active within the last 48 hours per the ESPN feed)

Split: time-ordered 80/20 to avoid leaking future results into training.
"""

import joblib
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline

from app.models.nba import Game, TeamFeatures

MODEL_PATH = Path(__file__).parent / "nba_model.pkl"

FEATURES = [
    "form_5_diff",
    "form_10_diff",
    "pts_scored_diff",
    "pts_allowed_diff",
    "home_win_pct_home",
    "away_win_pct_away",
    "injury_adj_off_rating_diff",  # off_rating scaled by PPG% of Out players
    "injury_adj_def_rating_diff",  # def_rating scaled by MPG% of Out players
    "injury_impact_diff",
    "superstar_out_diff",           # away - home: positive = away star missing (good for home)
]


def _feature_row(home: TeamFeatures, away: TeamFeatures) -> dict | None:
    """
    Build a feature dict from a home/away TeamFeatures pair.
    Returns None if any required field is missing.
    Adjusted ratings fall back to base ratings when injury data is absent
    (e.g., historical snapshots before roster sync was introduced).
    injury_impact_diff / superstar_out_diff = away - home so positive favours home.
    """
    required = [
        home.form_score_5, home.form_score_10,
        home.avg_points_scored, home.avg_points_allowed, home.win_pct_home,
        away.form_score_5, away.form_score_10,
        away.avg_points_scored, away.avg_points_allowed, away.win_pct_away,
    ]
    if any(v is None for v in required):
        return None

    # Injury-adjusted ratings fall back to base ratings when not computed.
    home_adj_off = home.injury_adj_off_rating if home.injury_adj_off_rating is not None else (home.off_rating if home.off_rating is not None else 0.5)
    away_adj_off = away.injury_adj_off_rating if away.injury_adj_off_rating is not None else (away.off_rating if away.off_rating is not None else 0.5)
    home_adj_def = home.injury_adj_def_rating if home.injury_adj_def_rating is not None else (home.def_rating if home.def_rating is not None else 0.5)
    away_adj_def = away.injury_adj_def_rating if away.injury_adj_def_rating is not None else (away.def_rating if away.def_rating is not None else 0.5)
    home_inj = home.injury_impact if home.injury_impact is not None else 0.0
    away_inj = away.injury_impact if away.injury_impact is not None else 0.0
    home_star_out = home.superstar_out if home.superstar_out is not None else 0.0
    away_star_out = away.superstar_out if away.superstar_out is not None else 0.0

    return {
        "form_5_diff": home.form_score_5 - away.form_score_5,
        "form_10_diff": home.form_score_10 - away.form_score_10,
        "pts_scored_diff": home.avg_points_scored - away.avg_points_scored,
        "pts_allowed_diff": home.avg_points_allowed - away.avg_points_allowed,
        "home_win_pct_home": home.win_pct_home,
        "away_win_pct_away": away.win_pct_away,
        "injury_adj_off_rating_diff": home_adj_off - away_adj_off,
        "injury_adj_def_rating_diff": home_adj_def - away_adj_def,
        "injury_impact_diff": away_inj - home_inj,
        "superstar_out_diff": away_star_out - home_star_out,
    }


def build_training_data(db: Session) -> tuple[list[dict], list[int]]:
    """
    Join completed games with TeamFeatures snapshots.
    Returns (X_rows, y) where y=1 means home team won.
    Games are ordered by date (oldest first) for time-ordered splitting.
    """
    games = (
        db.query(Game)
        .filter(Game.status == "Final")
        .order_by(Game.date.asc())
        .all()
    )

    X_rows, y = [], []
    skipped = 0

    for g in games:
        game_date = g.date.date() if isinstance(g.date, datetime) else g.date

        home_feat = (
            db.query(TeamFeatures)
            .filter(TeamFeatures.team_id == g.home_team_id, TeamFeatures.date == game_date)
            .first()
        )
        away_feat = (
            db.query(TeamFeatures)
            .filter(TeamFeatures.team_id == g.away_team_id, TeamFeatures.date == game_date)
            .first()
        )

        if not home_feat or not away_feat:
            skipped += 1
            continue

        row = _feature_row(home_feat, away_feat)
        if row is None:
            skipped += 1
            continue

        X_rows.append(row)
        y.append(1 if g.home_score > g.away_score else 0)

    print(f"Training data: {len(X_rows)} games used, {skipped} skipped (missing features)")
    return X_rows, y


def train(db: Session) -> dict:
    """
    Train a logistic regression model on all available NBA game data.
    Saves the trained pipeline to MODEL_PATH.
    Returns evaluation metrics.
    """
    X_rows, y = build_training_data(db)

    if len(X_rows) < 50:
        raise ValueError(f"Not enough training data: only {len(X_rows)} games available")

    # Time-ordered 80/20 split — no shuffling to avoid future leakage.
    split = int(len(X_rows) * 0.8)
    X_train_rows, X_test_rows = X_rows[:split], X_rows[split:]
    y_train, y_test = y[:split], y[split:]

    # Convert to plain lists for sklearn.
    X_train = [[row[f] for f in FEATURES] for row in X_train_rows]
    X_test = [[row[f] for f in FEATURES] for row in X_test_rows]

    pipeline = Pipeline([
        ("clf", GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
        )),
    ])
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)

    importances = pipeline.named_steps["clf"].feature_importances_
    feature_importance = {f: round(float(v), 4) for f, v in zip(FEATURES, importances)}

    metrics = {
        "train_games": len(X_train),
        "test_games": len(X_test),
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "log_loss": round(log_loss(y_test, y_prob), 4),
        "home_win_rate_train": round(sum(y_train) / len(y_train), 4),
        "home_win_rate_test": round(sum(y_test) / len(y_test), 4),
        "feature_importance": feature_importance,
    }

    joblib.dump({"pipeline": pipeline, "features": FEATURES, "metrics": metrics}, MODEL_PATH)
    print(f"NBA model trained — accuracy: {metrics['accuracy']}, log_loss: {metrics['log_loss']}")
    print(f"Model saved to {MODEL_PATH}")
    return metrics


def predict(home_team_id: str, away_team_id: str, as_of: date, db: Session) -> dict:
    """
    Predict the outcome of a game between home_team_id and away_team_id.
    Uses the most recent TeamFeatures snapshot on or before as_of for each team.
    """
    if not MODEL_PATH.exists():
        raise FileNotFoundError("NBA model has not been trained yet. POST /admin/train/nba first.")

    artifact = joblib.load(MODEL_PATH)
    pipeline = artifact["pipeline"]

    home_feat = (
        db.query(TeamFeatures)
        .filter(TeamFeatures.team_id == home_team_id, TeamFeatures.date <= as_of)
        .order_by(TeamFeatures.date.desc())
        .first()
    )
    away_feat = (
        db.query(TeamFeatures)
        .filter(TeamFeatures.team_id == away_team_id, TeamFeatures.date <= as_of)
        .order_by(TeamFeatures.date.desc())
        .first()
    )

    if not home_feat:
        raise ValueError(f"No feature snapshot found for home team {home_team_id}")
    if not away_feat:
        raise ValueError(f"No feature snapshot found for away team {away_team_id}")

    row = _feature_row(home_feat, away_feat)
    if row is None:
        raise ValueError("Insufficient feature data for one or both teams (some values are null)")

    X = [[row[f] for f in FEATURES]]
    prob_home_win = float(pipeline.predict_proba(X)[0][1])

    return {
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "as_of": as_of.isoformat(),
        "home_win_probability": round(prob_home_win, 4),
        "away_win_probability": round(1 - prob_home_win, 4),
        "predicted_winner": "home" if prob_home_win >= 0.5 else "away",
        "features_used": {k: round(v, 4) for k, v in row.items()},
        "home_features_date": home_feat.date.isoformat(),
        "away_features_date": away_feat.date.isoformat(),
        "model_metrics": artifact["metrics"],
    }
