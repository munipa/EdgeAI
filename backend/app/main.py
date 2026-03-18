from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.espn_service import ESPNService
from app.database import engine, get_db
from app.models import Base
from app.models.nba import Team, Game
from app import scheduler as sched
from datetime import datetime


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


# Keep the old fake endpoint for reference
@app.get("/games/fake")
def get_fake_games():
    return {
        "games": [
            {"id": 1, "home_team": "Lakers", "away_team": "Warriors"},
            {"id": 2, "home_team": "Celtics", "away_team": "Heat"}
        ]
    }