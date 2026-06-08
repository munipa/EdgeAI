import type {
  Game,
  Team,
  TeamStats,
  Injury,
  Standings,
  PredictionResult,
  TeamFeatures,
} from "@/types/nba"
import type { TennisMatch, TennisPlayer, TennisPredictionResult } from "@/types/tennis"

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }
  const res = await fetch(url.toString(), { cache: "no-store" })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

// ── NBA ──────────────────────────────────────────────────────────────────────

export async function getTodaysGames(): Promise<Game[]> {
  const r = await get<{ games: Game[]; count: number }>("/games/nba/today")
  return r.games ?? []
}

export async function getGames(date?: string): Promise<Game[]> {
  const r = await get<{ games: Game[]; count: number }>("/games/nba", date ? { date } : undefined)
  return r.games ?? []
}

export function getGameHistory(params?: {
  team_id?: string
  limit?: string
  offset?: string
}): Promise<{ games: Game[]; total: number }> {
  return get("/games/nba/history", params as Record<string, string>)
}

export function getTeams(): Promise<{ teams: Team[]; count: number }> {
  return get("/teams/nba")
}

export function getTeamStats(teamId: string): Promise<TeamStats> {
  return get(`/teams/nba/${teamId}/stats`)
}

export function getTeamForm(teamId: string): Promise<{ team_id: string; games: unknown[] }> {
  return get(`/teams/nba/${teamId}/form`)
}

export function getTeamFeatures(teamId: string): Promise<TeamFeatures> {
  return get(`/teams/nba/${teamId}/features`)
}

export function getStandings(): Promise<Standings> {
  return get("/standings/nba")
}

export function getInjuries(): Promise<{ injuries: Injury[]; count: number }> {
  return get("/injuries/nba")
}

export function predictNBA(
  homeTeamId: string,
  awayTeamId: string,
  date?: string
): Promise<PredictionResult> {
  const params: Record<string, string> = {
    home_team_id: homeTeamId,
    away_team_id: awayTeamId,
  }
  if (date) params.date = date
  return get("/predict/nba", params)
}

// ── Tennis ───────────────────────────────────────────────────────────────────

export function getTodaysTennisMatches(): Promise<TennisMatch[]> {
  return get("/matches/tennis/today")
}

export function getTennisPlayers(): Promise<{ players: TennisPlayer[]; count: number }> {
  return get("/players/tennis")
}

export function predictTennis(
  player1Id: string,
  player2Id: string,
  surface: string,
  date?: string
): Promise<TennisPredictionResult> {
  const params: Record<string, string> = {
    player1_id: player1Id,
    player2_id: player2Id,
    surface,
  }
  if (date) params.date = date
  return get("/predict/tennis", params)
}
