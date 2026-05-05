"""
NBA team feature engineering.

Computes pre-computed features for each team as of a given date and stores
them in the team_features table. These snapshots are used for model training
and fast prediction lookups.
"""

from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.nba import Team, Game, TeamStats, Injury, TeamFeatures, NBAPlayer

# Exponential decay for form score: most recent game has weight 1, each
# older game is multiplied by DECAY.
FORM_DECAY = 0.85

# Injury severity weights — baseline for an average player.
INJURY_WEIGHTS = {
    "out": 3.0,
    "doubtful": 2.0,
    "questionable": 1.0,
    "day-to-day": 0.5,
}


def _player_importance_multiplier(avg_points: float | None) -> float:
    """
    Scale injury weight by the player's offensive importance.
    Uses PPG tiers: star (>=20) → 2×, key player (>=12) → 1.5×,
    starter (>=6) → 1×, bench (<6) → 0.5×.
    Returns 1.0 (neutral) when PPG is unknown.
    """
    if avg_points is None:
        return 1.0
    if avg_points >= 20:
        return 2.0
    elif avg_points >= 12:
        return 1.5
    elif avg_points >= 6:
        return 1.0
    else:
        return 0.5


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


def _compute_features(team_id: str, as_of: date, db: Session) -> dict:
    """Compute all features for *team_id* as of *as_of* (exclusive)."""

    # ------------------------------------------------------------------ #
    # 1. Fetch all completed games up to (but not including) as_of date.  #
    # ------------------------------------------------------------------ #
    completed = (
        db.query(Game)
        .filter(
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            Game.status == "Final",
            Game.date < datetime.combine(as_of, datetime.min.time()),
        )
        .order_by(Game.date.desc())
        .all()
    )

    # ------------------------------------------------------------------ #
    # 2. Form scores (last 5 and last 10).                                #
    # ------------------------------------------------------------------ #
    def _won(g: Game) -> bool:
        is_home = g.home_team_id == team_id
        return g.home_score > g.away_score if is_home else g.away_score > g.home_score

    results_bool = [_won(g) for g in completed]
    form_score_5 = _weighted_form(results_bool[:5])
    form_score_10 = _weighted_form(results_bool[:10])

    # ------------------------------------------------------------------ #
    # 3. Avg points scored / allowed (last 10).                           #
    # ------------------------------------------------------------------ #
    recent_10 = completed[:10]
    if recent_10:
        scored = []
        allowed = []
        for g in recent_10:
            if g.home_team_id == team_id:
                scored.append(g.home_score)
                allowed.append(g.away_score)
            else:
                scored.append(g.away_score)
                allowed.append(g.home_score)
        avg_points_scored = round(sum(scored) / len(scored), 2)
        avg_points_allowed = round(sum(allowed) / len(allowed), 2)
    else:
        avg_points_scored = None
        avg_points_allowed = None

    # ------------------------------------------------------------------ #
    # 4. Home / away win %.                                               #
    # ------------------------------------------------------------------ #
    home_games = [g for g in completed if g.home_team_id == team_id]
    away_games = [g for g in completed if g.away_team_id == team_id]

    win_pct_home = (
        round(sum(1 for g in home_games if g.home_score > g.away_score) / len(home_games), 4)
        if home_games else None
    )
    win_pct_away = (
        round(sum(1 for g in away_games if g.away_score > g.home_score) / len(away_games), 4)
        if away_games else None
    )

    # ------------------------------------------------------------------ #
    # 5. Composite offensive / defensive ratings from TeamStats.          #
    #    Each sub-component is scaled to roughly [0, 1] using typical     #
    #    NBA season ranges before averaging.                               #
    # ------------------------------------------------------------------ #
    stats: TeamStats | None = db.get(TeamStats, team_id)

    off_rating = None
    def_rating = None

    if stats:
        # Offensive: higher is better for all except turnovers.
        # Approximate season ranges (used for min-max normalisation):
        #   avg_points       [95, 125]
        #   field_goal_pct   [0.40, 0.52]
        #   three_point_pct  [0.30, 0.42]
        #   avg_assists      [20, 32]
        #   avg_turnovers    [10, 18]  — inverted (fewer is better)
        def _norm(val, lo, hi):
            if hi == lo:
                return 0.5
            return max(0.0, min(1.0, (val - lo) / (hi - lo)))

        off_components = [
            _norm(stats.avg_points, 95, 125),
            _norm(stats.field_goal_pct, 0.40, 0.52),
            _norm(stats.three_point_pct, 0.30, 0.42),
            _norm(stats.avg_assists, 20, 32),
            1.0 - _norm(stats.avg_turnovers, 10, 18),  # fewer turnovers = better
        ]
        off_rating = round(sum(off_components) / len(off_components), 4)

        # Defensive: higher is better for all.
        #   avg_defensive_rebounds  [25, 40]
        #   avg_steals              [5, 11]
        #   avg_blocks              [3, 8]
        def_components = [
            _norm(stats.avg_defensive_rebounds, 25, 40),
            _norm(stats.avg_steals, 5, 11),
            _norm(stats.avg_blocks, 3, 8),
        ]
        def_rating = round(sum(def_components) / len(def_components), 4)

    # ------------------------------------------------------------------ #
    # 6. Injury impact score — weighted by player importance.            #
    # Only counts injuries reported in the last 30 days, deduplicated   #
    # per player (most recent record wins) to avoid stacking season-    #
    # long history for the same player.                                 #
    # Severity weight × importance multiplier (star=2×, bench=0.5×).   #
    # ------------------------------------------------------------------ #
    # Use reported_at (when ESPN created the entry) rather than updated_at
    # (which we used to refresh on every sync, making it useless as a staleness
    # signal). A 14-day window covers ongoing playoff injuries while naturally
    # excluding old per-game "Out" entries for players who have since returned.
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    recent_injuries = (
        db.query(Injury)
        .filter(
            Injury.team_id == team_id,
            Injury.reported_at >= cutoff,
        )
        .order_by(Injury.reported_at.desc())
        .all()
    )

    # Deduplicate: keep only the most recent entry per player.
    seen_players: set[str] = set()
    injuries = []
    for inj in recent_injuries:
        if inj.player_name not in seen_players:
            seen_players.add(inj.player_name)
            injuries.append(inj)

    injury_impact = 0.0
    out_ppg = 0.0      # PPG of confirmed-Out players (for off rating adjustment)
    out_mpg = 0.0      # MPG of confirmed-Out players (for def rating adjustment)
    superstar_out = 0.0

    for inj in injuries:
        status_weight = INJURY_WEIGHTS.get(inj.status.lower(), 0.0)
        if status_weight == 0.0:
            continue

        # Look up the player: prefer athlete_id (ESPN ID), fall back to name.
        player: NBAPlayer | None = None
        if inj.athlete_id:
            player = db.get(NBAPlayer, inj.athlete_id)
        if player is None:
            player = (
                db.query(NBAPlayer)
                .filter(NBAPlayer.name == inj.player_name, NBAPlayer.team_id == team_id)
                .first()
            )

        importance = _player_importance_multiplier(player.avg_points if player else None)
        injury_impact += status_weight * importance

        # Accumulate Out-only stats for rating adjustments.
        if inj.status.lower() == "out" and player:
            if player.avg_points:
                out_ppg += player.avg_points
                if player.avg_points >= 25.0:
                    superstar_out = 1.0
            if player.avg_minutes:
                out_mpg += player.avg_minutes

    injury_impact = round(injury_impact, 2)

    # ------------------------------------------------------------------ #
    # 7. Injury-adjusted ratings.                                          #
    # Scale off_rating by the fraction of PPG still available, and        #
    # def_rating by the fraction of MPG still available. When roster      #
    # data is absent (no NBAPlayer rows), fall back to the base rating.   #
    # ------------------------------------------------------------------ #
    team_players = (
        db.query(NBAPlayer).filter(NBAPlayer.team_id == team_id).all()
    )
    total_ppg = sum(p.avg_points for p in team_players if p.avg_points is not None)
    total_mpg = sum(p.avg_minutes for p in team_players if p.avg_minutes is not None)

    if off_rating is not None:
        off_avail = max(0.0, 1.0 - out_ppg / total_ppg) if total_ppg > 0 else 1.0
        injury_adj_off_rating = round(off_rating * off_avail, 4)
    else:
        injury_adj_off_rating = None

    if def_rating is not None:
        def_avail = max(0.0, 1.0 - out_mpg / total_mpg) if total_mpg > 0 else 1.0
        injury_adj_def_rating = round(def_rating * def_avail, 4)
    else:
        injury_adj_def_rating = None

    return {
        "team_id": team_id,
        "date": as_of,
        "form_score_5": form_score_5,
        "form_score_10": form_score_10,
        "avg_points_scored": avg_points_scored,
        "avg_points_allowed": avg_points_allowed,
        "win_pct_home": win_pct_home,
        "win_pct_away": win_pct_away,
        "off_rating": off_rating,
        "def_rating": def_rating,
        "injury_adj_off_rating": injury_adj_off_rating,
        "injury_adj_def_rating": injury_adj_def_rating,
        "superstar_out": superstar_out,
        "injury_impact": injury_impact,
    }


def upsert_team_features(team_id: str, as_of: date, db: Session) -> TeamFeatures:
    """Compute and persist features for a single team on a given date."""
    features = _compute_features(team_id, as_of, db)
    now = datetime.now(timezone.utc)

    existing = (
        db.query(TeamFeatures)
        .filter(TeamFeatures.team_id == team_id, TeamFeatures.date == as_of)
        .first()
    )
    if existing:
        for k, v in features.items():
            setattr(existing, k, v)
        existing.computed_at = now
        row = existing
    else:
        row = TeamFeatures(**features, computed_at=now)
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def compute_all_nba_features(as_of: date, db: Session):
    """Compute and persist features for every team in the DB."""
    teams = db.query(Team).all()
    for team in teams:
        try:
            upsert_team_features(team.id, as_of, db)
        except Exception as e:
            db.rollback()
            print(f"Feature engineering error for team {team.id}: {e}")
    print(f"Feature engineering: computed features for {len(teams)} teams as of {as_of}")


def backfill_nba_features():
    """
    Compute feature snapshots for every distinct game date in the DB.
    Runs in a background thread with its own DB sessions (one per game date).
    Features for date D use all completed games *before* D, so each snapshot
    represents what was known going into that day's games.
    """
    from app.database import SessionLocal

    # Fetch all distinct game dates using a fresh session.
    db = SessionLocal()
    try:
        rows = db.execute(
            __import__("sqlalchemy").text(
                "SELECT DISTINCT DATE(date) AS game_date FROM games ORDER BY game_date"
            )
        ).fetchall()
        game_dates = [r[0] for r in rows]
    finally:
        db.close()

    print(f"Feature backfill: {len(game_dates)} game dates to process")
    errors = 0

    for game_date in game_dates:
        db = SessionLocal()
        try:
            compute_all_nba_features(game_date, db)
        except Exception as e:
            db.rollback()
            errors += 1
            print(f"Feature backfill error on {game_date}: {e}")
        finally:
            db.close()

    print(f"Feature backfill complete: {len(game_dates)} dates, {errors} errors")
