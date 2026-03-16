import requests
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.nba import Team, Game


class ESPNService:
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

    def get_nba_games(self, date=None, db: Session = None):
        """
        Get NBA games for a specific date.
        If no date provided, gets today's games.
        If db is provided, persists teams and games to the database.
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        url = f"{self.BASE_URL}/basketball/nba/scoreboard"
        params = {"dates": date}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            games = []
            for event in data.get("events", []):
                competition = event["competitions"][0]
                home_team = competition["competitors"][0] if competition["competitors"][0]["homeAway"] == "home" else competition["competitors"][1]
                away_team = competition["competitors"][1] if competition["competitors"][1]["homeAway"] == "away" else competition["competitors"][0]

                game = {
                    "id": event["id"],
                    "date": event["date"],
                    "name": event["name"],
                    "status": event["status"]["type"]["description"],
                    "home_team": {
                        "id": home_team["team"]["id"],
                        "name": home_team["team"]["displayName"],
                        "abbreviation": home_team["team"]["abbreviation"],
                        "score": home_team.get("score", "0"),
                        "logo": home_team["team"].get("logo", "")
                    },
                    "away_team": {
                        "id": away_team["team"]["id"],
                        "name": away_team["team"]["displayName"],
                        "abbreviation": away_team["team"]["abbreviation"],
                        "score": away_team.get("score", "0"),
                        "logo": away_team["team"].get("logo", "")
                    }
                }
                games.append(game)

                if db:
                    self._save_game(db, game)

            return games

        except requests.exceptions.RequestException as e:
            print(f"Error fetching NBA games: {e}")
            return []

    def _save_game(self, db: Session, game: dict):
        """Persist a game and its teams to the database."""
        for side in ("home_team", "away_team"):
            t = game[side]
            team = db.get(Team, t["id"])
            if not team:
                team = Team(
                    id=t["id"],
                    name=t["name"],
                    abbreviation=t["abbreviation"],
                    logo=t["logo"]
                )
                db.add(team)

        game_date = datetime.fromisoformat(game["date"].replace("Z", "+00:00"))
        db_game = db.get(Game, game["id"])
        if db_game:
            db_game.status = game["status"]
            db_game.home_score = int(game["home_team"]["score"] or 0)
            db_game.away_score = int(game["away_team"]["score"] or 0)
        else:
            db_game = Game(
                id=game["id"],
                date=game_date,
                name=game["name"],
                status=game["status"],
                home_team_id=game["home_team"]["id"],
                away_team_id=game["away_team"]["id"],
                home_score=int(game["home_team"]["score"] or 0),
                away_score=int(game["away_team"]["score"] or 0)
            )
            db.add(db_game)

        db.commit()

    def get_nba_standings(self):
        """Get current NBA standings"""
        url = f"{self.BASE_URL}/basketball/nba/standings"

        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching standings: {e}")
            return None
