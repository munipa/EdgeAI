from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
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
