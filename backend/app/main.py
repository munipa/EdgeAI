from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.services.espn_service import ESPNService
from app.database import engine, get_db
from app.models import Base
from app.models.nba import Team, Game, TeamStats, Injury
from app import scheduler as sched
from datetime import datetime, timedelta
import time


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    sched.start()
    yield
    sched.stop()


app = FastAPI(title="Sports Analytics API", lifespan=lifespan)

# Create an instance of our ESPN service
espn = ESPNService()

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Sports Analytics API!",
        "status": "running",
        "endpoints": [
            "/games/nba",
            "/games/nba/today",
            "/games/nba/history",
            "/standings/nba",
            "/teams/nba",
            "/teams/nba/{team_id}/games",
            "/teams/nba/{team_id}/stats",
            "/teams/nba/{team_id}/form",
            "/teams/nba/h2h",
            "/injuries/nba",
            "POST /admin/backfill/nba",
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


# Keep the old fake endpoint for reference
@app.get("/games/fake")
def get_fake_games():
    return {
        "games": [
            {"id": 1, "home_team": "Lakers", "away_team": "Warriors"},
            {"id": 2, "home_team": "Celtics", "away_team": "Heat"}
        ]
    }