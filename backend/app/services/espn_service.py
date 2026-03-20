import requests
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.nba import Team, Game, TeamStats, Injury


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

    def get_all_nba_teams(self):
        """Get all NBA teams from ESPN."""
        url = f"{self.BASE_URL}/basketball/nba/teams"
        try:
            response = requests.get(url, params={"limit": 32})
            response.raise_for_status()
            data = response.json()
            return [t["team"] for t in data["sports"][0]["leagues"][0]["teams"]]
        except requests.exceptions.RequestException as e:
            print(f"Error fetching NBA team list: {e}")
            return []

    def get_team_stats(self, team_id: str, db: Session = None):
        """Get offensive/defensive stats for a single team."""
        url = f"{self.BASE_URL}/basketball/nba/teams/{team_id}/statistics"
        try:
            response = requests.get(url)
            response.raise_for_status()
            stats = self._parse_team_stats(team_id, response.json())
            if db:
                self._save_team_stats(db, stats)
            return stats
        except requests.exceptions.RequestException as e:
            print(f"Error fetching stats for team {team_id}: {e}")
            return None

    def _parse_team_stats(self, team_id: str, data: dict) -> dict:
        flat = {}
        for category in data.get("results", {}).get("stats", {}).get("categories", []):
            for stat in category.get("stats", []):
                flat[stat["name"]] = stat.get("value", 0.0)
        return {
            "team_id": team_id,
            "games_played": int(flat.get("gamesPlayed", 0)),
            "avg_points": flat.get("avgPoints", 0.0),
            "field_goal_pct": flat.get("fieldGoalPct", 0.0),
            "three_point_pct": flat.get("threePointFieldGoalPct", 0.0),
            "free_throw_pct": flat.get("freeThrowPct", 0.0),
            "avg_assists": flat.get("avgAssists", 0.0),
            "avg_turnovers": flat.get("avgTurnovers", 0.0),
            "avg_offensive_rebounds": flat.get("avgOffensiveRebounds", 0.0),
            "avg_defensive_rebounds": flat.get("avgDefensiveRebounds", 0.0),
            "avg_steals": flat.get("avgSteals", 0.0),
            "avg_blocks": flat.get("avgBlocks", 0.0),
        }

    def _save_team_stats(self, db: Session, stats: dict):
        existing = db.get(TeamStats, stats["team_id"])
        now = datetime.now(timezone.utc)
        if existing:
            for k, v in stats.items():
                setattr(existing, k, v)
            existing.synced_at = now
        else:
            db.add(TeamStats(**stats, synced_at=now))
        db.commit()

    def sync_all_team_stats(self, db: Session):
        """Sync stats for all 30 NBA teams."""
        teams = self.get_all_nba_teams()
        for team in teams:
            self.get_team_stats(team["id"], db=db)
        print(f"Scheduler: synced stats for {len(teams)} teams")

    def get_nba_injuries(self, db: Session = None):
        """Get current NBA injury report."""
        url = f"{self.BASE_URL}/basketball/nba/injuries"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            all_injuries = []
            for team_entry in data.get("injuries", []):
                team_id = team_entry["id"]
                for inj in team_entry.get("injuries", []):
                    injury = {
                        "id": inj["id"],
                        "team_id": team_id,
                        "player_name": inj["athlete"]["displayName"],
                        "status": inj["status"],
                        "comment": inj.get("shortComment", ""),
                        "reported_at": inj.get("date"),
                    }
                    all_injuries.append(injury)
                    if db:
                        self._save_injury(db, injury)

            return all_injuries
        except requests.exceptions.RequestException as e:
            print(f"Error fetching NBA injuries: {e}")
            return []

    def _save_injury(self, db: Session, injury: dict):
        reported_at = None
        if injury["reported_at"]:
            reported_at = datetime.fromisoformat(injury["reported_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        existing = db.get(Injury, injury["id"])
        if existing:
            existing.status = injury["status"]
            existing.comment = injury["comment"]
            existing.updated_at = now
        else:
            db.add(Injury(
                id=injury["id"],
                team_id=injury["team_id"],
                player_name=injury["player_name"],
                status=injury["status"],
                comment=injury["comment"],
                reported_at=reported_at,
                updated_at=now,
            ))
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
