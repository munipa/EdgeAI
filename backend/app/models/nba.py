from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
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
    status = Column(String, nullable=False)  # Out, Questionable, Doubtful, etc.
    comment = Column(String)
    reported_at = Column(DateTime)
    updated_at = Column(DateTime)

    team = relationship("Team", back_populates="injuries")
