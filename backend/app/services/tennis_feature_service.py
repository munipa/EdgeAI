"""
Tennis player feature engineering.

Computes pre-computed features for each player as of a given date and stores
them in the tennis_player_features table.  These snapshots are used for model
training and fast prediction lookups.

Backfill strategy: for each distinct match date, only compute features for
players who appear in a match on that date — far more efficient than
all_players x all_dates.
"""

from datetime import date, datetime, timezone
from sqlalchemy.orm import Session

from app.models.tennis import TennisPlayer, TennisMatch, TennisPlayerStats, TennisPlayerFeatures

# Exponential decay for form score: most recent match has weight 1, each
# older match is multiplied by DECAY.
FORM_DECAY = 0.85

# Surfaces we track explicitly.
TRACKED_SURFACES = {"Hard", "Clay", "Grass"}


def _weighted_form(results: list[bool]) -> float:
    """
    Given a list of W/L booleans ordered most-recent-first, return the
    exponentially-weighted win rate.  Returns 0.0 if the list is empty.
    """
    if not results:
        return 0.0
    total_weight = 0.0
    weighted_wins = 0.0
    for i, won in enumerate(results):
        w = FORM_DECAY ** i
        total_weight += w
        if won:
            weighted_wins += w
    return round(weighted_wins / total_weight, 4)


def _compute_player_features(player_id: str, as_of: date, db: Session) -> dict:
    """Compute all features for *player_id* as of *as_of* (exclusive)."""

    # ------------------------------------------------------------------ #
    # 1. Fetch all completed matches before as_of.                        #
    # ------------------------------------------------------------------ #
    completed = (
        db.query(TennisMatch)
        .filter(
            (TennisMatch.player1_id == player_id) | (TennisMatch.player2_id == player_id),
            TennisMatch.status == "Final",
            TennisMatch.winner_id.isnot(None),
            TennisMatch.date < datetime.combine(as_of, datetime.min.time()),
        )
        .order_by(TennisMatch.date.desc())
        .all()
    )

    results_bool = [m.winner_id == player_id for m in completed]

    # ------------------------------------------------------------------ #
    # 2. Form scores (last 5 and last 10).                                #
    # ------------------------------------------------------------------ #
    form_score_5 = _weighted_form(results_bool[:5])
    form_score_10 = _weighted_form(results_bool[:10])

    # ------------------------------------------------------------------ #
    # 3. Overall and recent (last 20) win %.                              #
    # ------------------------------------------------------------------ #
    overall_win_pct = (
        round(sum(results_bool) / len(results_bool), 4) if results_bool else None
    )
    recent_20 = results_bool[:20]
    recent_win_pct = (
        round(sum(recent_20) / len(recent_20), 4) if recent_20 else None
    )

    # ------------------------------------------------------------------ #
    # 4. Surface win % and match counts.                                  #
    # ------------------------------------------------------------------ #
    surface_wins: dict[str, int] = {s: 0 for s in TRACKED_SURFACES}
    surface_total: dict[str, int] = {s: 0 for s in TRACKED_SURFACES}

    for m in completed:
        surface = m.surface
        if surface not in TRACKED_SURFACES:
            continue
        surface_total[surface] += 1
        if m.winner_id == player_id:
            surface_wins[surface] += 1

    def _surface_win_pct(surface: str) -> float | None:
        total = surface_total[surface]
        return round(surface_wins[surface] / total, 4) if total else None

    win_pct_hard = _surface_win_pct("Hard")
    win_pct_clay = _surface_win_pct("Clay")
    win_pct_grass = _surface_win_pct("Grass")

    # ------------------------------------------------------------------ #
    # 5. Composite serve / return ratings from TennisPlayerStats.        #
    #    Current-only snapshot — safe only for present-day predictions.  #
    # ------------------------------------------------------------------ #
    stats: TennisPlayerStats | None = db.get(TennisPlayerStats, player_id)

    serve_rating = None
    return_rating = None

    if stats:
        def _norm(val, lo, hi):
            if hi == lo:
                return 0.5
            return max(0.0, min(1.0, (val - lo) / (hi - lo)))

        # Typical tour ranges:
        #   first_serve_pct          [0.50, 0.72]
        #   first_serve_win_pct      [0.60, 0.82]
        #   service_games_won_pct    [0.70, 0.92]
        serve_components = [
            _norm(stats.first_serve_pct, 0.50, 0.72),
            _norm(stats.first_serve_win_pct, 0.60, 0.82),
            _norm(stats.service_games_won_pct, 0.70, 0.92),
        ]
        serve_rating = round(sum(serve_components) / len(serve_components), 4)

        #   return_games_won_pct         [0.18, 0.42]
        #   break_points_converted_pct   [0.30, 0.55]
        return_components = [
            _norm(stats.return_games_won_pct, 0.18, 0.42),
            _norm(stats.break_points_converted_pct, 0.30, 0.55),
        ]
        return_rating = round(sum(return_components) / len(return_components), 4)

    return {
        "player_id": player_id,
        "date": as_of,
        "form_score_5": form_score_5,
        "form_score_10": form_score_10,
        "overall_win_pct": overall_win_pct,
        "recent_win_pct": recent_win_pct,
        "win_pct_hard": win_pct_hard,
        "win_pct_clay": win_pct_clay,
        "win_pct_grass": win_pct_grass,
        "matches_hard": surface_total["Hard"],
        "matches_clay": surface_total["Clay"],
        "matches_grass": surface_total["Grass"],
        "serve_rating": serve_rating,
        "return_rating": return_rating,
    }


def upsert_player_features(player_id: str, as_of: date, db: Session) -> TennisPlayerFeatures:
    """Compute and persist features for a single player on a given date."""
    features = _compute_player_features(player_id, as_of, db)
    now = datetime.now(timezone.utc)

    existing = (
        db.query(TennisPlayerFeatures)
        .filter(TennisPlayerFeatures.player_id == player_id, TennisPlayerFeatures.date == as_of)
        .first()
    )
    if existing:
        for k, v in features.items():
            setattr(existing, k, v)
        existing.computed_at = now
        row = existing
    else:
        row = TennisPlayerFeatures(**features, computed_at=now)
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def compute_all_tennis_features(tour: str, as_of: date, db: Session):
    """Compute and persist features for every player in the given tour."""
    players = db.query(TennisPlayer).filter(TennisPlayer.tour == tour).all()
    errors = 0
    for player in players:
        try:
            upsert_player_features(player.id, as_of, db)
        except Exception as e:
            db.rollback()
            errors += 1
            print(f"Tennis feature error [{tour.upper()}] player {player.id}: {e}")
    print(
        f"Tennis feature engineering [{tour.upper()}]: {len(players)} players "
        f"as of {as_of} ({errors} errors)"
    )


def backfill_tennis_features(tour: str):
    """
    Compute feature snapshots for every distinct match date in the DB for
    the given tour.

    For each date, only computes features for the players who appear in a
    match on that date (not all players), which keeps the backfill tractable.
    Features for date D use all completed matches *before* D.
    """
    from app.database import SessionLocal
    import sqlalchemy

    db = SessionLocal()
    try:
        rows = db.execute(
            sqlalchemy.text(
                "SELECT DISTINCT DATE(date) AS match_date "
                "FROM tennis_matches WHERE tour = :tour ORDER BY match_date"
            ),
            {"tour": tour},
        ).fetchall()
        match_dates = [r[0] for r in rows]
    finally:
        db.close()

    print(f"Tennis feature backfill [{tour.upper()}]: {len(match_dates)} match dates to process")
    errors = 0

    for match_date in match_dates:
        db = SessionLocal()
        try:
            day_start = datetime.combine(match_date, datetime.min.time())
            day_end = datetime.combine(match_date, datetime.max.time())
            day_matches = (
                db.query(TennisMatch)
                .filter(
                    TennisMatch.tour == tour,
                    TennisMatch.date >= day_start,
                    TennisMatch.date <= day_end,
                )
                .all()
            )
            player_ids = set()
            for m in day_matches:
                player_ids.add(m.player1_id)
                player_ids.add(m.player2_id)

            for pid in player_ids:
                try:
                    upsert_player_features(pid, match_date, db)
                except Exception as e:
                    db.rollback()
                    errors += 1
                    print(
                        f"Tennis feature backfill error [{tour.upper()}] "
                        f"player {pid} on {match_date}: {e}"
                    )
        except Exception as e:
            db.rollback()
            errors += 1
            print(f"Tennis feature backfill error [{tour.upper()}] on {match_date}: {e}")
        finally:
            db.close()

    print(
        f"Tennis feature backfill [{tour.upper()}] complete: "
        f"{len(match_dates)} dates, {errors} errors"
    )
