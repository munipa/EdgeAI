import requests
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.tennis import TennisPlayer, TennisTournament, TennisMatch, TennisPlayerStats


class TennisService:
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis"

    # -------------------------------------------------------------------------
    # Matches / Scoreboard
    # -------------------------------------------------------------------------

    def get_matches(self, tour: str, date: str = None, db: Session = None):
        """
        Get ATP or WTA matches for a given date (YYYYMMDD).
        tour must be 'atp' or 'wta'.
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        url = f"{self.BASE_URL}/{tour}/scoreboard"
        params = {"dates": date}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {tour.upper()} matches for {date}: {e}")
            return []

        matches = []
        for event in data.get("events", []):
            match = self._parse_event(event, tour)
            if match is None:
                continue
            matches.append(match)
            if db:
                self._save_match(db, match)

        return matches

    def _parse_event(self, event: dict, tour: str) -> dict | None:
        try:
            competition = event["competitions"][0]
            competitors = competition.get("competitors", [])
            if len(competitors) < 2:
                return None

            p1_raw = competitors[0]
            p2_raw = competitors[1]

            p1 = self._parse_player(p1_raw, tour)
            p2 = self._parse_player(p2_raw, tour)

            winner_id = None
            if p1_raw.get("winner"):
                winner_id = p1["id"]
            elif p2_raw.get("winner"):
                winner_id = p2["id"]

            score = self._parse_score(competition)

            # Tournament info lives in season/notes
            notes = competition.get("notes", [])
            round_name = notes[0].get("headline", "") if notes else competition.get("type", {}).get("text", "")
            surface = self._extract_surface(competition, event)
            tournament_id, tournament_name = self._extract_tournament(event)

            return {
                "id": event["id"],
                "tour": tour,
                "date": event["date"],
                "name": event.get("name", ""),
                "status": event["status"]["type"]["description"],
                "round": round_name,
                "surface": surface,
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "player1": p1,
                "player2": p2,
                "winner_id": winner_id,
                "score": score,
            }
        except (KeyError, IndexError) as e:
            print(f"Error parsing tennis event {event.get('id')}: {e}")
            return None

    def _parse_player(self, competitor: dict, tour: str) -> dict:
        athlete = competitor.get("athlete", {})
        rank = competitor.get("curatedRank", {}).get("current") or competitor.get("rank")
        return {
            "id": competitor["id"],
            "name": athlete.get("displayName", competitor.get("displayName", "Unknown")),
            "nationality": athlete.get("flag", {}).get("alt", ""),
            "ranking": int(rank) if rank else None,
            "logo": athlete.get("headshot", {}).get("href", ""),
            "tour": tour,
        }

    def _parse_score(self, competition: dict) -> str:
        """Build a set-score string like '6-4 7-5 6-3' from linescores."""
        try:
            comps = competition.get("competitors", [])
            if len(comps) < 2:
                return ""
            p1_lines = comps[0].get("linescores", [])
            p2_lines = comps[1].get("linescores", [])
            sets = []
            for i in range(min(len(p1_lines), len(p2_lines))):
                s1 = p1_lines[i].get("value", "0")
                s2 = p2_lines[i].get("value", "0")
                sets.append(f"{s1}-{s2}")
            return " ".join(sets)
        except Exception:
            return ""

    def _extract_surface(self, competition: dict, event: dict) -> str | None:
        # ESPN sometimes puts surface in the venue or notes
        venue = competition.get("venue", {})
        grass_hints = ["wimbledon", "grass"]
        clay_hints = ["roland garros", "clay", "terra"]
        hard_hints = ["hard", "us open", "australian open"]
        name = event.get("name", "").lower()
        for hint in grass_hints:
            if hint in name:
                return "Grass"
        for hint in clay_hints:
            if hint in name:
                return "Clay"
        for hint in hard_hints:
            if hint in name:
                return "Hard"
        return None

    def _extract_tournament(self, event: dict) -> tuple[str | None, str]:
        season = event.get("season", {})
        tid = season.get("slug") or season.get("year")
        tname = season.get("displayName") or event.get("name", "")
        # Use the league/tournament slug if available
        leagues = event.get("leagues", [])
        if leagues:
            tid = leagues[0].get("slug") or tid
            tname = leagues[0].get("name") or tname
        return (str(tid) if tid else None, tname)

    # -------------------------------------------------------------------------
    # Persist helpers
    # -------------------------------------------------------------------------

    def _save_match(self, db: Session, match: dict):
        # Upsert players
        for side in ("player1", "player2"):
            p = match[side]
            player = db.get(TennisPlayer, p["id"])
            if not player:
                player = TennisPlayer(
                    id=p["id"],
                    name=p["name"],
                    nationality=p["nationality"],
                    tour=match["tour"],
                    ranking=p["ranking"],
                    logo=p["logo"],
                )
                db.add(player)
            else:
                if p["ranking"] is not None:
                    player.ranking = p["ranking"]

        # Upsert tournament stub
        if match["tournament_id"]:
            tournament = db.get(TennisTournament, match["tournament_id"])
            if not tournament:
                match_date = datetime.fromisoformat(match["date"].replace("Z", "+00:00"))
                tournament = TennisTournament(
                    id=match["tournament_id"],
                    name=match["tournament_name"],
                    tour=match["tour"],
                    surface=match["surface"],
                    start_date=match_date,
                )
                db.add(tournament)

        # Upsert match
        match_date = datetime.fromisoformat(match["date"].replace("Z", "+00:00"))
        db_match = db.get(TennisMatch, match["id"])
        if db_match:
            db_match.status = match["status"]
            db_match.score = match["score"]
            db_match.winner_id = match["winner_id"]
        else:
            db_match = TennisMatch(
                id=match["id"],
                tournament_id=match["tournament_id"],
                date=match_date,
                tour=match["tour"],
                round=match["round"],
                surface=match["surface"],
                status=match["status"],
                player1_id=match["player1"]["id"],
                player2_id=match["player2"]["id"],
                winner_id=match["winner_id"],
                score=match["score"],
            )
            db.add(db_match)

        db.commit()

    # -------------------------------------------------------------------------
    # Player rankings list
    # -------------------------------------------------------------------------

    def get_players(self, tour: str, limit: int = 100):
        """Get top-ranked players for a tour."""
        url = f"{self.BASE_URL}/{tour}/athletes"
        try:
            response = requests.get(url, params={"limit": limit})
            response.raise_for_status()
            data = response.json()
            return data.get("athletes", [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {tour.upper()} players: {e}")
            return []
