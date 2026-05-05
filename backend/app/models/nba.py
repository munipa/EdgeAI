from sqlalchemy import Column, String, Integer, Float, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.base import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(String, primary_key=True)  # ESPN team ID
    name = Column(String, nullable=False)
    abbreviation = Column(String, nullable=False)
    logo = Column(String)

    home_games = relationship("Game", foreign_keys="Game.home_team_id", back_populates="home_team")
    away_games = relationship("Game", foreign_keys="Game.away_team_id", back_populates="away_team")
    stats = relationship("TeamStats", back_populates="team", uselist=False)
    injuries = relationship("Injury", back_populates="team")
    features = relationship("TeamFeatures", back_populates="team")
    players = relationship("NBAPlayer", back_populates="team")


class NBAPlayer(Base):
    __tablename__ = "nba_players"

    id = Column(String, primary_key=True)   # ESPN athlete ID
    name = Column(String, nullable=False)
    team_id = Column(String, ForeignKey("teams.id"), nullable=True)
    position = Column(String)
    jersey = Column(String)
    avg_points = Column(Float)   # PPG this season — used for injury importance weighting
    avg_minutes = Column(Float)  # MPG this season
    synced_at = Column(DateTime, nullable=False)

    team = relationship("Team", back_populates="players")


class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True)  # ESPN game ID
    date = Column(DateTime, nullable=False)
    name = Column(String)
    status = Column(String)

    home_team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)

    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_games")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_games")


class TeamStats(Base):
    __tablename__ = "team_stats"

    team_id = Column(String, ForeignKey("teams.id"), primary_key=True)
    synced_at = Column(DateTime, nullable=False)
    games_played = Column(Integer, default=0)
    # Offensive
    avg_points = Column(Float, default=0.0)
    field_goal_pct = Column(Float, default=0.0)
    three_point_pct = Column(Float, default=0.0)
    free_throw_pct = Column(Float, default=0.0)
    avg_assists = Column(Float, default=0.0)
    avg_turnovers = Column(Float, default=0.0)
    avg_offensive_rebounds = Column(Float, default=0.0)
    # Defensive
    avg_defensive_rebounds = Column(Float, default=0.0)
    avg_steals = Column(Float, default=0.0)
    avg_blocks = Column(Float, default=0.0)

    team = relationship("Team", back_populates="stats")


class Injury(Base):
    __tablename__ = "injuries"

    id = Column(String, primary_key=True)  # ESPN injury ID
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    player_name = Column(String, nullable=False)
    athlete_id = Column(String, nullable=True)   # ESPN athlete ID — links to NBAPlayer for importance weighting
    status = Column(String, nullable=False)  # Out, Questionable, Doubtful, etc.
    comment = Column(String)
    reported_at = Column(DateTime)
    updated_at = Column(DateTime)

    team = relationship("Team", back_populates="injuries")


class TeamFeatures(Base):
    __tablename__ = "team_features"
    __table_args__ = (UniqueConstraint("team_id", "date", name="uq_team_features_team_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    computed_at = Column(DateTime, nullable=False)

    # Form (exponentially weighted, decay=0.85, most recent = weight 1)
    form_score_5 = Column(Float)   # last 5 games
    form_score_10 = Column(Float)  # last 10 games

    # Scoring from actual game results (last 10 completed games)
    avg_points_scored = Column(Float)
    avg_points_allowed = Column(Float)

    # Season split win %
    win_pct_home = Column(Float)
    win_pct_away = Column(Float)

    # Composite ratings derived from TeamStats (0–1 normalised)
    off_rating = Column(Float)
    def_rating = Column(Float)

    # Injury-adjusted ratings: base rating scaled down by the PPG/MPG fraction
    # of players currently listed as Out. Falls back to base rating when no
    # injury data is available (e.g., historical snapshots).
    injury_adj_off_rating = Column(Float)
    injury_adj_def_rating = Column(Float)

    # 1 if any Out player averages >=25 PPG (superstar missing), else 0.
    superstar_out = Column(Float, default=0.0)

    # Injury impact: Out=3, Doubtful=2, Questionable=1, Day-To-Day=0.5
    injury_impact = Column(Float)

    team = relationship("Team", back_populates="features")
