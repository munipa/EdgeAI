from fastapi import FastAPI, Query, Depends
from sqlalchemy.orm import Session
from app.services.espn_service import ESPNService
from app.database import engine, get_db
from app.models import Base
from datetime import datetime

app = FastAPI(title="Sports Analytics API")

Base.metadata.create_all(bind=engine)

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
            "/standings/nba"
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

# Keep the old fake endpoint for reference
@app.get("/games/fake")
def get_fake_games():
    return {
        "games": [
            {"id": 1, "home_team": "Lakers", "away_team": "Warriors"},
            {"id": 2, "home_team": "Celtics", "away_team": "Heat"}
        ]
    }