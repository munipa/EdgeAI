export interface Team {
  id: string
  name: string
  abbreviation: string
  logo: string
}

export interface GameTeam {
  id: string
  name: string
  abbreviation: string
  score: string
  logo: string
}

export interface Game {
  id: string
  date: string
  name: string
  status: string
  home_team: GameTeam
  away_team: GameTeam
}

export interface TeamStats {
  team_id: string
  games_played: number
  avg_points: number
  field_goal_pct: number
  three_point_pct: number
  free_throw_pct: number
  avg_assists: number
  avg_turnovers: number
  avg_offensive_rebounds: number
  avg_defensive_rebounds: number
  avg_steals: number
  avg_blocks: number
}

export interface Injury {
  player_name: string
  team_id: string
  status: string
  comment: string
  reported_at: string
}

export interface StandingEntry {
  team: string
  abbreviation: string
  wins: number
  losses: number
  pct: number
  gb: number
  home: string
  away: string
  streak: string
}

export interface Standings {
  east: StandingEntry[]
  west: StandingEntry[]
}

export interface PredictionResult {
  home_team_id: string
  away_team_id: string
  home_team_name: string
  away_team_name: string
  as_of: string
  home_win_probability: number
  away_win_probability: number
  predicted_winner: "home" | "away"
  features_used: Record<string, number>
  home_features_date: string
  away_features_date: string
  model_metrics: {
    accuracy: number
    log_loss: number
    train_games: number
    test_games: number
    feature_importance: Record<string, number>
  }
}

export interface FormEntry {
  date: string
  opponent: string
  result: "W" | "L"
  score: string
  home: boolean
}

export interface TeamFeatures {
  team_id: string
  date: string
  form_score_5: number
  form_score_10: number
  avg_points_scored: number
  avg_points_allowed: number
  win_pct_home: number
  win_pct_away: number
  off_rating: number | null
  def_rating: number | null
  injury_impact: number
}
