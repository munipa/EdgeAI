from sqlalchemy import Column, String, Integer, Float, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.base import Base


class TennisTournament(Base):
    __tablename__ = "tennis_tournaments"

    id = Column(String, primary_key=True)   # ESPN event/tournament ID
    name = Column(String, nullable=False)
    tour = Column(String, nullable=False)   # "atp" or "wta"
    surface = Column(String)               # Hard, Clay, Grass
    category = Column(String)              # Grand Slam, Masters 1000, etc.
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    location = Column(String)

    matches = relationship("TennisMatch", back_populates="tournament")


class TennisPlayer(Base):
    __tablename__ = "tennis_players"

    id = Column(String, primary_key=True)   # ESPN athlete ID
    name = Column(String, nullable=False)
    nationality = Column(String)
    tour = Column(String, nullable=False)   # "atp" or "wta"
    ranking = Column(Integer)
    ranking_points = Column(Integer)
    hand = Column(String)                   # Left, Right
    logo = Column(String)                   # headshot/flag URL

    stats = relationship("TennisPlayerStats", back_populates="player", uselist=False)
    features = relationship("TennisPlayerFeatures", back_populates="player")
    matches_as_p1 = relationship("TennisMatch", foreign_keys="TennisMatch.player1_id", back_populates="player1")
    matches_as_p2 = relationship("TennisMatch", foreign_keys="TennisMatch.player2_id", back_populates="player2")


class TennisMatch(Base):
    __tablename__ = "tennis_matches"

    id = Column(String, primary_key=True)   # ESPN event ID
    tournament_id = Column(String, ForeignKey("tennis_tournaments.id"), nullable=True)
    date = Column(DateTime, nullable=False)
    tour = Column(String, nullable=False)   # "atp" or "wta"
    round = Column(String)                  # R128, R64, QF, SF, F, etc.
    surface = Column(String)
    status = Column(String)                 # Final, In Progress, Scheduled

    player1_id = Column(String, ForeignKey("tennis_players.id"), nullable=False)
    player2_id = Column(String, ForeignKey("tennis_players.id"), nullable=False)
    winner_id = Column(String, ForeignKey("tennis_players.id"), nullable=True)
    score = Column(String)                  # e.g. "6-4 7-5 6-3"

    tournament = relationship("TennisTournament", back_populates="matches")
    player1 = relationship("TennisPlayer", foreign_keys=[player1_id], back_populates="matches_as_p1")
    player2 = relationship("TennisPlayer", foreign_keys=[player2_id], back_populates="matches_as_p2")
    winner = relationship("TennisPlayer", foreign_keys=[winner_id])


class TennisPlayerStats(Base):
    __tablename__ = "tennis_player_stats"

    player_id = Column(String, ForeignKey("tennis_players.id"), primary_key=True)
    synced_at = Column(DateTime, nullable=False)
    matches_played = Column(Integer, default=0)
    matches_won = Column(Integer, default=0)
    # Serve
    aces_per_match = Column(Float, default=0.0)
    double_faults_per_match = Column(Float, default=0.0)
    first_serve_pct = Column(Float, default=0.0)
    first_serve_win_pct = Column(Float, default=0.0)
    second_serve_win_pct = Column(Float, default=0.0)
    service_games_won_pct = Column(Float, default=0.0)
    # Return
    return_games_won_pct = Column(Float, default=0.0)
    break_points_converted_pct = Column(Float, default=0.0)
    # Overall
    win_pct = Column(Float, default=0.0)
    titles = Column(Integer, default=0)

    player = relationship("TennisPlayer", back_populates="stats")


class TennisPlayerFeatures(Base):
    __tablename__ = "tennis_player_features"
    __table_args__ = (UniqueConstraint("player_id", "date", name="uq_tennis_player_features_player_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("tennis_players.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    computed_at = Column(DateTime, nullable=False)

    # Form (exponentially weighted, decay=0.85, most-recent = weight 1)
    form_score_5 = Column(Float)   # last 5 matches
    form_score_10 = Column(Float)  # last 10 matches

    # Win % over all completed matches up to date
    overall_win_pct = Column(Float)

    # Win % over the last 20 completed matches (recent trend)
    recent_win_pct = Column(Float)

    # Surface-specific win % (all completed matches up to date)
    win_pct_hard = Column(Float)
    win_pct_clay = Column(Float)
    win_pct_grass = Column(Float)

    # Match counts per surface (confidence signal)
    matches_hard = Column(Integer)
    matches_clay = Column(Integer)
    matches_grass = Column(Integer)

    # Composite serve / return ratings derived from TennisPlayerStats (0–1, current-only snapshot)
    serve_rating = Column(Float)
    return_rating = Column(Float)

    player = relationship("TennisPlayer", back_populates="features")
