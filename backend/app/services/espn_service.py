import requests
from datetime import datetime

class ESPNService:
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
    
    def get_nba_games(self, date=None):
        """
        Get NBA games for a specific date
        If no date provided, gets today's games
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        url = f"{self.BASE_URL}/basketball/nba/scoreboard"
        params = {"dates": date}
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Parse the response into a cleaner format
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
                        "name": home_team["team"]["displayName"],
                        "abbreviation": home_team["team"]["abbreviation"],
                        "score": home_team.get("score", "0"),
                        "logo": home_team["team"].get("logo", "")
                    },
                    "away_team": {
                        "name": away_team["team"]["displayName"],
                        "abbreviation": away_team["team"]["abbreviation"],
                        "score": away_team.get("score", "0"),
                        "logo": away_team["team"].get("logo", "")
                    }
                }
                games.append(game)
            
            return games
        
        except requests.exceptions.RequestException as e:
            print(f"Error fetching NBA games: {e}")
            return []
    
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