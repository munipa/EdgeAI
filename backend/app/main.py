from fastapi import FastAPI

app = FastAPI(title="Sports Analytics API")

@app.get("/")
def read_root():
    return {"message": "Welcome to Sports Analytics API!", "status": "running"}

@app.get("/games")
def get_games():
    return {
        "games": [
            {"id": 1, "home_team": "Lakers", "away_team": "Warriors"},
            {"id": 2, "home_team": "Celtics", "away_team": "Heat"}
        ]
    }
