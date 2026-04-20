from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Depends, HTTPException, BackgroundTasks
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.espn_service import ESPNService
from app.services.tennis_service import TennisService
from app.services.feature_service import upsert_team_features, compute_all_nba_features, backfill_nba_features
from app.ml import nba_model, tennis_model
from app.services.tennis_feature_service import upsert_player_features, compute_all_tennis_features, backfill_tennis_features as backfill_tennis_feature_history
from app.database import engine, get_db
from app.models import Base
from app.models.nba import Team, Game, TeamStats, Injury, TeamFeatures, NBAPlayer
from app.models.tennis import TennisPlayer, TennisMatch, TennisPlayerFeatures
from app import scheduler as sched
from datetime import datetime, timedelta
import time


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    # Add athlete_id to injuries if it doesn't exist (safe on re-run via IF NOT EXISTS).
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE injuries ADD COLUMN IF NOT EXISTS athlete_id TEXT"))
        conn.commit()
    sched.start()
    yield
    sched.stop()


app = FastAPI(title="Sports Analytics API", lifespan=lifespan)

# Create an instance of our ESPN service
espn = ESPNService()
tennis = TennisService()

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Sports Analytics API!",
        "status": "running",
        "endpoints": [
            "/games/nba", "/games/nba/today", "/games/nba/history",
            "/standings/nba", "/teams/nba", "/teams/nba/{team_id}/games",
            "/teams/nba/{team_id}/stats", "/teams/nba/{team_id}/form",
            "/teams/nba/h2h", "/injuries/nba", "/teams/nba/{team_id}/features",
            "POST /admin/backfill/nba", "POST /admin/features/nba",
            "POST /admin/sync/rosters/nba", "GET /players/nba",
            "POST /admin/train/nba", "GET /predict/nba",
            "/matches/tennis", "/matches/tennis/today",
            "/matches/tennis/history",
            "/players/tennis",
            "/players/tennis/{player_id}/matches",
            "/players/tennis/{player_id}/form",
            "/players/tennis/{player_id}/surface",
            "/players/tennis/h2h",
            "POST /admin/backfill/tennis",
            "/players/tennis/{player_id}/features",
            "POST /admin/features/tennis",
            "POST /admin/backfill/features/tennis",
            "POST /admin/train/tennis", "GET /predict/tennis",
        ]
    }

@app.get("/games/nba")
def get_nba_games(date: str = Query(None, description="Date in YYYYMMDD format, e.g., 20260122"), db: Session = Depends(get_db)):
    """
    Get NBA games for a specific date
    If no date provided, returns today's games
    """
    games = espn.get_nba_games(date, db=db)
    return {
        "sport": "NBA",
        "date": date or datetime.now().strftime("%Y%m%d"),
        "count": len(games),
        "games": games
    }

@app.get("/games/nba/today")
def get_todays_nba_games(db: Session = Depends(get_db)):
    """Get today's NBA games"""
    games = espn.get_nba_games(db=db)
    return {
        "sport": "NBA",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "count": len(games),
        "games": games
    }

@app.get("/standings/nba")
def get_nba_standings():
    """Get current NBA standings"""
    standings = espn.get_nba_standings()
    return standings

@app.get("/games/nba/history")
def get_nba_game_history(
    start: str = Query(..., description="Start date in YYYYMMDD format"),
    end: str = Query(..., description="End date in YYYYMMDD format"),
    db: Session = Depends(get_db),
):
    """Get NBA games from the DB for a date range"""
    try:
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYYMMDD format")

    games = (
        db.query(Game)
        .filter(Game.date >= start_dt, Game.date <= end_dt)
        .order_by(Game.date)
        .all()
    )

    return {
        "sport": "NBA",
        "start": start,
        "end": end,
        "count": len(games),
        "games": [
            {
                "id": g.id,
                "name": g.name,
                "date": g.date.isoformat(),
                "status": g.status,
                "home_team": g.home_team.name,
                "away_team": g.away_team.name,
                "home_score": g.home_score,
                "away_score": g.away_score,
            }
            for g in games
        ],
    }


@app.get("/teams/nba")
def get_nba_teams(db: Session = Depends(get_db)):
    """List all NBA teams stored in the DB"""
    teams = db.query(Team).order_by(Team.name).all()
    return {
        "sport": "NBA",
        "count": len(teams),
        "teams": [
            {"id": t.id, "name": t.name, "abbreviation": t.abbreviation, "logo": t.logo}
            for t in teams
        ],
    }


@app.get("/teams/nba/{team_id}/games")
def get_team_games(
    team_id: str,
    db: Session = Depends(get_db),
):
    """Get all games for a specific NBA team from the DB"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    games = (
        db.query(Game)
        .filter((Game.home_team_id == team_id) | (Game.away_team_id == team_id))
        .order_by(Game.date)
        .all()
    )

    return {
        "team": {"id": team.id, "name": team.name, "abbreviation": team.abbreviation},
        "count": len(games),
        "games": [
            {
                "id": g.id,
                "name": g.name,
                "date": g.date.isoformat(),
                "status": g.status,
                "home_team": g.home_team.name,
                "away_team": g.away_team.name,
                "home_score": g.home_score,
                "away_score": g.away_score,
            }
            for g in games
        ],
    }


@app.get("/teams/nba/{team_id}/stats")
def get_team_stats(team_id: str, db: Session = Depends(get_db)):
    """Get offensive/defensive stats for a specific NBA team"""
    stats = db.get(TeamStats, team_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Stats not found for this team")
    return {
        "team_id": stats.team_id,
        "synced_at": stats.synced_at.isoformat(),
        "games_played": stats.games_played,
        "offensive": {
            "avg_points": stats.avg_points,
            "field_goal_pct": stats.field_goal_pct,
            "three_point_pct": stats.three_point_pct,
            "free_throw_pct": stats.free_throw_pct,
            "avg_assists": stats.avg_assists,
            "avg_turnovers": stats.avg_turnovers,
            "avg_offensive_rebounds": stats.avg_offensive_rebounds,
        },
        "defensive": {
            "avg_defensive_rebounds": stats.avg_defensive_rebounds,
            "avg_steals": stats.avg_steals,
            "avg_blocks": stats.avg_blocks,
        },
    }


@app.get("/injuries/nba")
def get_nba_injuries(db: Session = Depends(get_db)):
    """Get current NBA injury report from the DB"""
    injuries = db.query(Injury).order_by(Injury.team_id, Injury.reported_at.desc()).all()
    return {
        "count": len(injuries),
        "injuries": [
            {
                "id": i.id,
                "team_id": i.team_id,
                "player_name": i.player_name,
                "status": i.status,
                "comment": i.comment,
                "reported_at": i.reported_at.isoformat() if i.reported_at else None,
            }
            for i in injuries
        ],
    }


@app.get("/teams/nba/h2h")
def get_nba_h2h(
    team1: str = Query(..., description="First team ESPN ID"),
    team2: str = Query(..., description="Second team ESPN ID"),
    years: int = Query(3, description="How many years back to look", ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Get head-to-head record between two NBA teams over the last N years"""
    t1 = db.get(Team, team1)
    t2 = db.get(Team, team2)
    if not t1:
        raise HTTPException(status_code=404, detail=f"Team {team1} not found")
    if not t2:
        raise HTTPException(status_code=404, detail=f"Team {team2} not found")

    since = datetime.now() - timedelta(days=years * 365)

    matchups = (
        db.query(Game)
        .filter(
            (
                ((Game.home_team_id == team1) & (Game.away_team_id == team2)) |
                ((Game.home_team_id == team2) & (Game.away_team_id == team1))
            ),
            Game.status == "Final",
            Game.date >= since,
        )
        .order_by(Game.date.desc())
        .all()
    )

    t1_wins, t2_wins = 0, 0
    games_list = []
    for g in matchups:
        t1_is_home = g.home_team_id == team1
        t1_won = g.home_score > g.away_score if t1_is_home else g.away_score > g.home_score
        if t1_won:
            t1_wins += 1
        else:
            t2_wins += 1
        games_list.append({
            "date": g.date.isoformat(),
            "home_team": t1.name if t1_is_home else t2.name,
            "away_team": t2.name if t1_is_home else t1.name,
            "score": f"{g.home_score}-{g.away_score}",
            "winner": t1.name if t1_won else t2.name,
        })

    total = len(matchups)
    return {
        "team1": {"id": t1.id, "name": t1.name, "wins": t1_wins},
        "team2": {"id": t2.id, "name": t2.name, "wins": t2_wins},
        "total_games": total,
        "years_back": years,
        "games": games_list,
    }


@app.get("/teams/nba/{team_id}/form")
def get_team_form(
    team_id: str,
    games: int = Query(10, description="Number of recent games to evaluate", ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Get recent form for a specific NBA team (win/loss over last N games)"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    recent_games = (
        db.query(Game)
        .filter(
            ((Game.home_team_id == team_id) | (Game.away_team_id == team_id)),
            Game.status == "Final",
        )
        .order_by(Game.date.desc())
        .limit(games)
        .all()
    )

    results = []
    for g in recent_games:
        is_home = g.home_team_id == team_id
        won = g.home_score > g.away_score if is_home else g.away_score > g.home_score
        opponent_id = g.away_team_id if is_home else g.home_team_id
        opponent = db.get(Team, opponent_id)
        results.append({
            "date": g.date.isoformat(),
            "opponent": opponent.name if opponent else opponent_id,
            "home": is_home,
            "score": f"{g.home_score}-{g.away_score}",
            "result": "W" if won else "L",
        })

    wins = sum(1 for r in results if r["result"] == "W")
    losses = len(results) - wins

    # Current streak
    streak_char = results[0]["result"] if results else None
    streak_count = 0
    for r in results:
        if r["result"] == streak_char:
            streak_count += 1
        else:
            break

    return {
        "team_id": team_id,
        "team_name": team.name,
        "last_n_games": len(results),
        "wins": wins,
        "losses": losses,
        "win_pct": round(wins / len(results), 3) if results else 0,
        "streak": f"{streak_char}{streak_count}" if streak_char else None,
        "results": results,
    }


def _run_backfill(start: datetime, end: datetime):
    from app.database import SessionLocal
    current = start
    total_days = 0
    total_games = 0
    errors = 0
    while current <= end:
        date_str = current.strftime("%Y%m%d")
        db = SessionLocal()
        try:
            games = espn.get_nba_games(date=date_str, db=db)
            total_games += len(games)
            total_days += 1
            print(f"Backfill: {date_str} — {len(games)} games")
        except Exception as e:
            db.rollback()
            errors += 1
            print(f"Backfill error on {date_str}: {e}")
        finally:
            db.close()
        current += timedelta(days=1)
        time.sleep(0.3)  # be polite to ESPN API
    print(f"Backfill complete: {total_days} days, {total_games} games synced, {errors} errors")


@app.post("/admin/backfill/nba")
def backfill_nba_games(
    background_tasks: BackgroundTasks,
    start: str = Query(..., description="Start date YYYYMMDD"),
    end: str = Query(..., description="End date YYYYMMDD"),
):
    """
    Backfill NBA games from ESPN for a date range.
    Runs in the background — check server logs for progress.
    """
    try:
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYYMMDD format")

    if end_dt < start_dt:
        raise HTTPException(status_code=400, detail="end must be after start")

    days = (end_dt - start_dt).days + 1
    if days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

    background_tasks.add_task(_run_backfill, start_dt, end_dt)
    return {
        "status": "started",
        "start": start,
        "end": end,
        "days_to_sync": days,
        "message": "Backfill running in background. Check server logs for progress.",
    }


@app.get("/teams/nba/{team_id}/features")
def get_team_features(
    team_id: str,
    date: str = Query(None, description="Date in YYYYMMDD format. Defaults to today."),
    db: Session = Depends(get_db),
):
    """
    Get pre-computed feature snapshot for a team on a given date.
    If no date is provided, returns the most recent available snapshot.
    """
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if date:
        try:
            as_of = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYYMMDD format")
        row = (
            db.query(TeamFeatures)
            .filter(TeamFeatures.team_id == team_id, TeamFeatures.date == as_of)
            .first()
        )
    else:
        row = (
            db.query(TeamFeatures)
            .filter(TeamFeatures.team_id == team_id)
            .order_by(TeamFeatures.date.desc())
            .first()
        )

    if not row:
        raise HTTPException(status_code=404, detail="No feature snapshot found for this team/date")

    return {
        "team_id": row.team_id,
        "team_name": team.name,
        "date": row.date.isoformat(),
        "computed_at": row.computed_at.isoformat(),
        "form": {
            "form_score_5": row.form_score_5,
            "form_score_10": row.form_score_10,
        },
        "scoring": {
            "avg_points_scored": row.avg_points_scored,
            "avg_points_allowed": row.avg_points_allowed,
        },
        "splits": {
            "win_pct_home": row.win_pct_home,
            "win_pct_away": row.win_pct_away,
        },
        "ratings": {
            "off_rating": row.off_rating,
            "def_rating": row.def_rating,
        },
        "injury_impact": row.injury_impact,
    }


@app.post("/admin/features/nba")
def trigger_nba_features(
    background_tasks: BackgroundTasks,
    date: str = Query(None, description="Date in YYYYMMDD format. Defaults to today."),
):
    """
    Manually trigger NBA feature computation for all teams on a given date.
    Useful for backfilling features after the game data is loaded.
    """
    from datetime import date as date_type
    if date:
        try:
            as_of = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYYMMDD format")
    else:
        as_of = date_type.today()

    def _run(as_of):
        from app.database import SessionLocal
        db2 = SessionLocal()
        try:
            compute_all_nba_features(as_of, db2)
        finally:
            db2.close()

    background_tasks.add_task(_run, as_of)
    return {"status": "started", "date": as_of.isoformat(), "message": "Feature computation running in background."}


@app.post("/admin/train/nba")
def train_nba_model(background_tasks: BackgroundTasks):
    """
    Train (or retrain) the NBA prediction model on all available game + feature data.
    Runs in the background — check logs for accuracy and log-loss metrics.
    """
    def _run():
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            nba_model.train(db)
        except Exception as e:
            print(f"NBA model training error: {e}")
        finally:
            db.close()

    background_tasks.add_task(_run)
    return {"status": "started", "message": "NBA model training running in background. Check logs for metrics."}


@app.get("/predict/nba")
def predict_nba_game(
    home_team_id: str = Query(..., description="Home team ESPN ID"),
    away_team_id: str = Query(..., description="Away team ESPN ID"),
    date: str = Query(None, description="As-of date YYYYMMDD. Defaults to today."),
    db: Session = Depends(get_db),
):
    """
    Predict the outcome of an NBA game between two teams.
    Returns win probabilities for each side and the predicted winner.
    """
    from datetime import date as date_type
    if date:
        try:
            as_of = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYYMMDD format")
    else:
        as_of = date_type.today()

    home = db.get(Team, home_team_id)
    away = db.get(Team, away_team_id)
    if not home:
        raise HTTPException(status_code=404, detail=f"Team {home_team_id} not found")
    if not away:
        raise HTTPException(status_code=404, detail=f"Team {away_team_id} not found")

    try:
        result = nba_model.predict(home_team_id, away_team_id, as_of, db)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    result["home_team_name"] = home.name
    result["away_team_name"] = away.name
    return result


@app.post("/admin/backfill/features/nba")
def backfill_nba_feature_history(background_tasks: BackgroundTasks):
    """
    Backfill feature snapshots for every game date in the DB.
    One snapshot per team per game day — covers the full season history.
    Check server logs for progress.
    """
    background_tasks.add_task(backfill_nba_features)
    return {
        "status": "started",
        "message": "NBA feature backfill running in background. Check server logs for progress.",
    }


@app.post("/admin/sync/rosters/nba")
def sync_nba_rosters(background_tasks: BackgroundTasks):
    """
    Sync current NBA rosters for all 30 teams from ESPN.
    Populates the nba_players table with player info and PPG/MPG stats,
    which are used to weight injury impact by player importance.
    Run this once (or at the start of a new season) before retraining the model.
    """
    def _run():
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            total = espn.sync_all_rosters(db)
            print(f"Roster sync complete: {total} players saved")
        except Exception as e:
            print(f"Roster sync error: {e}")
        finally:
            db.close()

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": "NBA roster sync running in background. Check server logs for progress.",
    }


@app.get("/players/nba")
def get_nba_players(
    team_id: str = Query(None, description="Filter by team ESPN ID"),
    db: Session = Depends(get_db),
):
    """List NBA players stored in the DB, optionally filtered by team."""
    query = db.query(NBAPlayer)
    if team_id:
        query = query.filter(NBAPlayer.team_id == team_id)
    players = query.order_by(NBAPlayer.avg_points.desc().nullslast()).all()
    return {
        "count": len(players),
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "team_id": p.team_id,
                "position": p.position,
                "jersey": p.jersey,
                "avg_points": p.avg_points,
                "avg_minutes": p.avg_minutes,
            }
            for p in players
        ],
    }


# Keep the old fake endpoint for reference
@app.get("/games/fake")
def get_fake_games():
    return {
        "games": [
            {"id": 1, "home_team": "Lakers", "away_team": "Warriors"},
            {"id": 2, "home_team": "Celtics", "away_team": "Heat"}
        ]
    }


# =============================================================================
# Tennis endpoints
# =============================================================================

VALID_TOURS = {"atp", "wta"}


def _validate_tour(tour: str):
    if tour not in VALID_TOURS:
        raise HTTPException(status_code=400, detail="tour must be 'atp' or 'wta'")


@app.get("/matches/tennis")
def get_tennis_matches(
    tour: str = Query(..., description="'atp' or 'wta'"),
    date: str = Query(None, description="Date in YYYYMMDD format"),
    db: Session = Depends(get_db),
):
    """Get ATP or WTA matches for a specific date (live from ESPN + persisted)."""
    _validate_tour(tour)
    matches = tennis.get_matches(tour, date=date, db=db)
    return {
        "tour": tour.upper(),
        "date": date or datetime.now().strftime("%Y%m%d"),
        "count": len(matches),
        "matches": matches,
    }


@app.get("/matches/tennis/today")
def get_todays_tennis_matches(
    tour: str = Query(..., description="'atp' or 'wta'"),
    db: Session = Depends(get_db),
):
    """Get today's ATP or WTA matches."""
    _validate_tour(tour)
    matches = tennis.get_matches(tour, db=db)
    return {
        "tour": tour.upper(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "count": len(matches),
        "matches": matches,
    }


@app.get("/matches/tennis/history")
def get_tennis_match_history(
    tour: str = Query(..., description="'atp' or 'wta'"),
    start: str = Query(..., description="Start date YYYYMMDD"),
    end: str = Query(..., description="End date YYYYMMDD"),
    db: Session = Depends(get_db),
):
    """Get stored tennis matches for a date range."""
    _validate_tour(tour)
    try:
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYYMMDD format")

    matches = (
        db.query(TennisMatch)
        .filter(
            TennisMatch.tour == tour,
            TennisMatch.date >= start_dt,
            TennisMatch.date <= end_dt,
        )
        .order_by(TennisMatch.date)
        .all()
    )

    return {
        "tour": tour.upper(),
        "start": start,
        "end": end,
        "count": len(matches),
        "matches": [_serialize_match(m, db) for m in matches],
    }


@app.get("/players/tennis")
def get_tennis_players(
    tour: str = Query(..., description="'atp' or 'wta'"),
    db: Session = Depends(get_db),
):
    """List all stored tennis players for a tour, ordered by ranking."""
    _validate_tour(tour)
    players = (
        db.query(TennisPlayer)
        .filter(TennisPlayer.tour == tour)
        .order_by(TennisPlayer.ranking.asc().nullslast())
        .all()
    )
    return {
        "tour": tour.upper(),
        "count": len(players),
        "players": [_serialize_player(p) for p in players],
    }


@app.get("/players/tennis/{player_id}/matches")
def get_player_matches(
    player_id: str,
    db: Session = Depends(get_db),
):
    """Get all stored matches for a specific player."""
    player = db.get(TennisPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    matches = (
        db.query(TennisMatch)
        .filter(
            (TennisMatch.player1_id == player_id) | (TennisMatch.player2_id == player_id)
        )
        .order_by(TennisMatch.date.desc())
        .all()
    )

    return {
        "player": _serialize_player(player),
        "count": len(matches),
        "matches": [_serialize_match(m, db) for m in matches],
    }


@app.get("/players/tennis/{player_id}/form")
def get_player_form(
    player_id: str,
    matches: int = Query(10, description="Number of recent matches to evaluate", ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Recent form for a player — win/loss over last N completed matches."""
    player = db.get(TennisPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    recent = (
        db.query(TennisMatch)
        .filter(
            ((TennisMatch.player1_id == player_id) | (TennisMatch.player2_id == player_id)),
            TennisMatch.status == "Final",
            TennisMatch.winner_id.isnot(None),
        )
        .order_by(TennisMatch.date.desc())
        .limit(matches)
        .all()
    )

    results = []
    for m in recent:
        won = m.winner_id == player_id
        opp_id = m.player2_id if m.player1_id == player_id else m.player1_id
        opp = db.get(TennisPlayer, opp_id)
        results.append({
            "date": m.date.isoformat(),
            "opponent": opp.name if opp else opp_id,
            "opponent_ranking": opp.ranking if opp else None,
            "surface": m.surface,
            "round": m.round,
            "score": m.score,
            "result": "W" if won else "L",
        })

    wins = sum(1 for r in results if r["result"] == "W")
    losses = len(results) - wins

    streak_char = results[0]["result"] if results else None
    streak_count = 0
    for r in results:
        if r["result"] == streak_char:
            streak_count += 1
        else:
            break

    return {
        "player_id": player_id,
        "player_name": player.name,
        "ranking": player.ranking,
        "last_n_matches": len(results),
        "wins": wins,
        "losses": losses,
        "win_pct": round(wins / len(results), 3) if results else 0,
        "streak": f"{streak_char}{streak_count}" if streak_char else None,
        "results": results,
    }


@app.get("/players/tennis/{player_id}/surface")
def get_player_surface_stats(
    player_id: str,
    db: Session = Depends(get_db),
):
    """Win % broken down by surface for a player."""
    player = db.get(TennisPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    matches = (
        db.query(TennisMatch)
        .filter(
            ((TennisMatch.player1_id == player_id) | (TennisMatch.player2_id == player_id)),
            TennisMatch.status == "Final",
            TennisMatch.winner_id.isnot(None),
            TennisMatch.surface.isnot(None),
        )
        .all()
    )

    surface_stats: dict[str, dict] = {}
    for m in matches:
        surface = m.surface
        if surface not in surface_stats:
            surface_stats[surface] = {"wins": 0, "losses": 0}
        if m.winner_id == player_id:
            surface_stats[surface]["wins"] += 1
        else:
            surface_stats[surface]["losses"] += 1

    breakdown = {}
    for surface, s in surface_stats.items():
        total = s["wins"] + s["losses"]
        breakdown[surface] = {
            "wins": s["wins"],
            "losses": s["losses"],
            "matches": total,
            "win_pct": round(s["wins"] / total, 3) if total else 0,
        }

    return {
        "player_id": player_id,
        "player_name": player.name,
        "ranking": player.ranking,
        "surface_breakdown": breakdown,
    }


@app.get("/players/tennis/h2h")
def get_tennis_h2h(
    player1: str = Query(..., description="First player ESPN ID"),
    player2: str = Query(..., description="Second player ESPN ID"),
    surface: str = Query(None, description="Filter by surface: Hard, Clay, Grass"),
    db: Session = Depends(get_db),
):
    """Head-to-head record between two players, optionally filtered by surface."""
    p1 = db.get(TennisPlayer, player1)
    p2 = db.get(TennisPlayer, player2)
    if not p1:
        raise HTTPException(status_code=404, detail=f"Player {player1} not found")
    if not p2:
        raise HTTPException(status_code=404, detail=f"Player {player2} not found")

    query = db.query(TennisMatch).filter(
        (
            ((TennisMatch.player1_id == player1) & (TennisMatch.player2_id == player2)) |
            ((TennisMatch.player1_id == player2) & (TennisMatch.player2_id == player1))
        ),
        TennisMatch.status == "Final",
        TennisMatch.winner_id.isnot(None),
    )
    if surface:
        query = query.filter(TennisMatch.surface == surface)

    matchups = query.order_by(TennisMatch.date.desc()).all()

    p1_wins, p2_wins = 0, 0
    games_list = []
    for m in matchups:
        p1_won = m.winner_id == player1
        if p1_won:
            p1_wins += 1
        else:
            p2_wins += 1
        games_list.append({
            "date": m.date.isoformat(),
            "surface": m.surface,
            "round": m.round,
            "score": m.score,
            "winner": p1.name if p1_won else p2.name,
        })

    return {
        "player1": {"id": p1.id, "name": p1.name, "ranking": p1.ranking, "wins": p1_wins},
        "player2": {"id": p2.id, "name": p2.name, "ranking": p2.ranking, "wins": p2_wins},
        "surface_filter": surface,
        "total_matches": len(matchups),
        "matches": games_list,
    }


def _serialize_player(p: TennisPlayer) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "nationality": p.nationality,
        "tour": p.tour,
        "ranking": p.ranking,
        "logo": p.logo,
    }


def _serialize_match(m: TennisMatch, db: Session) -> dict:
    p1 = db.get(TennisPlayer, m.player1_id)
    p2 = db.get(TennisPlayer, m.player2_id)
    winner = db.get(TennisPlayer, m.winner_id) if m.winner_id else None
    return {
        "id": m.id,
        "date": m.date.isoformat(),
        "tour": m.tour,
        "round": m.round,
        "surface": m.surface,
        "status": m.status,
        "player1": p1.name if p1 else m.player1_id,
        "player2": p2.name if p2 else m.player2_id,
        "winner": winner.name if winner else None,
        "score": m.score,
    }


@app.get("/players/tennis/{player_id}/features")
def get_player_features(
    player_id: str,
    date: str = Query(None, description="Date in YYYYMMDD format. Defaults to most recent snapshot."),
    db: Session = Depends(get_db),
):
    """Get pre-computed feature snapshot for a player on a given date."""
    player = db.get(TennisPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if date:
        try:
            as_of = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYYMMDD format")
        row = (
            db.query(TennisPlayerFeatures)
            .filter(TennisPlayerFeatures.player_id == player_id, TennisPlayerFeatures.date == as_of)
            .first()
        )
    else:
        row = (
            db.query(TennisPlayerFeatures)
            .filter(TennisPlayerFeatures.player_id == player_id)
            .order_by(TennisPlayerFeatures.date.desc())
            .first()
        )

    if not row:
        raise HTTPException(status_code=404, detail="No feature snapshot found for this player/date")

    return {
        "player_id": row.player_id,
        "player_name": player.name,
        "ranking": player.ranking,
        "date": row.date.isoformat(),
        "computed_at": row.computed_at.isoformat(),
        "form": {
            "form_score_5": row.form_score_5,
            "form_score_10": row.form_score_10,
        },
        "win_pct": {
            "overall": row.overall_win_pct,
            "recent_20": row.recent_win_pct,
            "hard": row.win_pct_hard,
            "clay": row.win_pct_clay,
            "grass": row.win_pct_grass,
        },
        "surface_matches": {
            "hard": row.matches_hard,
            "clay": row.matches_clay,
            "grass": row.matches_grass,
        },
        "ratings": {
            "serve_rating": row.serve_rating,
            "return_rating": row.return_rating,
        },
    }


@app.post("/admin/features/tennis")
def trigger_tennis_features(
    background_tasks: BackgroundTasks,
    tour: str = Query(..., description="'atp' or 'wta'"),
    date: str = Query(None, description="Date in YYYYMMDD format. Defaults to today."),
):
    """Manually trigger tennis feature computation for all players in a tour."""
    _validate_tour(tour)
    from datetime import date as date_type
    if date:
        try:
            as_of = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYYMMDD format")
    else:
        as_of = date_type.today()

    def _run(tour, as_of):
        from app.database import SessionLocal
        db2 = SessionLocal()
        try:
            compute_all_tennis_features(tour, as_of, db2)
        finally:
            db2.close()

    background_tasks.add_task(_run, tour, as_of)
    return {"status": "started", "tour": tour.upper(), "date": as_of.isoformat(),
            "message": "Feature computation running in background."}


@app.post("/admin/backfill/features/tennis")
def backfill_tennis_feature_snapshots(
    background_tasks: BackgroundTasks,
    tour: str = Query(..., description="'atp' or 'wta'"),
):
    """
    Backfill feature snapshots for every match date in the DB for a tour.
    Only computes for players active on each date. Check logs for progress.
    """
    _validate_tour(tour)
    background_tasks.add_task(backfill_tennis_feature_history, tour)
    return {
        "status": "started",
        "tour": tour.upper(),
        "message": "Tennis feature backfill running in background. Check server logs for progress.",
    }


@app.post("/admin/train/tennis")
def train_tennis_model(
    background_tasks: BackgroundTasks,
    tour: str = Query(..., description="'atp' or 'wta'"),
):
    """Train (or retrain) the tennis prediction model for a given tour."""
    _validate_tour(tour)

    def _run(tour):
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            tennis_model.train(tour, db)
        except Exception as e:
            print(f"Tennis model training error [{tour.upper()}]: {e}")
        finally:
            db.close()

    background_tasks.add_task(_run, tour)
    return {"status": "started", "tour": tour.upper(), "message": "Tennis model training running in background. Check logs for metrics."}


VALID_SURFACES = {"Hard", "Clay", "Grass"}


@app.get("/predict/tennis")
def predict_tennis_match(
    player1_id: str = Query(..., description="First player ESPN ID"),
    player2_id: str = Query(..., description="Second player ESPN ID"),
    surface: str = Query(..., description="Match surface: Hard, Clay, or Grass"),
    tour: str = Query(..., description="'atp' or 'wta'"),
    date: str = Query(None, description="As-of date YYYYMMDD. Defaults to today."),
    db: Session = Depends(get_db),
):
    """
    Predict the outcome of a tennis match between two players on a given surface.
    Returns win probabilities and the predicted winner.
    """
    _validate_tour(tour)
    if surface not in VALID_SURFACES:
        raise HTTPException(status_code=400, detail="surface must be Hard, Clay, or Grass")

    from datetime import date as date_type
    if date:
        try:
            as_of = datetime.strptime(date, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYYMMDD format")
    else:
        as_of = date_type.today()

    p1 = db.get(TennisPlayer, player1_id)
    p2 = db.get(TennisPlayer, player2_id)
    if not p1:
        raise HTTPException(status_code=404, detail=f"Player {player1_id} not found")
    if not p2:
        raise HTTPException(status_code=404, detail=f"Player {player2_id} not found")

    try:
        result = tennis_model.predict(player1_id, player2_id, surface, tour, as_of, db)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return result


def _run_tennis_backfill(tour: str, start: datetime, end: datetime):
    from app.database import SessionLocal
    current = start
    total_days = 0
    total_matches = 0
    errors = 0
    while current <= end:
        date_str = current.strftime("%Y%m%d")
        db = SessionLocal()
        try:
            matches = tennis.get_matches(tour, date=date_str, db=db)
            total_matches += len(matches)
            total_days += 1
            print(f"Tennis backfill [{tour.upper()}]: {date_str} — {len(matches)} matches")
        except Exception as e:
            db.rollback()
            errors += 1
            print(f"Tennis backfill error on {date_str}: {e}")
        finally:
            db.close()
        current += timedelta(days=1)
        time.sleep(0.3)
    print(f"Tennis backfill complete [{tour.upper()}]: {total_days} days, {total_matches} matches, {errors} errors")


@app.post("/admin/backfill/tennis")
def backfill_tennis_matches(
    background_tasks: BackgroundTasks,
    tour: str = Query(..., description="'atp' or 'wta'"),
    start: str = Query(..., description="Start date YYYYMMDD"),
    end: str = Query(..., description="End date YYYYMMDD"),
):
    """
    Backfill tennis matches from ESPN for a date range.
    Runs in the background — check server logs for progress.
    """
    _validate_tour(tour)
    try:
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYYMMDD format")

    if end_dt < start_dt:
        raise HTTPException(status_code=400, detail="end must be after start")

    days = (end_dt - start_dt).days + 1
    if days > 400:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 400 days")

    background_tasks.add_task(_run_tennis_backfill, tour, start_dt, end_dt)
    return {
        "status": "started",
        "tour": tour.upper(),
        "start": start,
        "end": end,
        "days_to_sync": days,
        "message": "Tennis backfill running in background. Check server logs for progress.",
    }