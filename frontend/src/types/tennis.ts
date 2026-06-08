export interface TennisPlayer {
  id: string
  name: string
  country: string
  ranking: number | null
}

export interface TennisMatch {
  id: string
  date: string
  tournament: string
  surface: string
  round: string
  status: string
  winner_id: string | null
  player1: TennisPlayer
  player2: TennisPlayer
  score: string | null
}

export interface TennisPredictionResult {
  player1_id: string
  player2_id: string
  player1_name: string
  player2_name: string
  surface: string
  as_of: string
  player1_win_probability: number
  player2_win_probability: number
  predicted_winner: string
  features_used: Record<string, number>
  model_metrics: {
    accuracy: number
    log_loss: number
    train_matches: number
    test_matches: number
  }
}
