"use client"

import { useEffect, useState, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { getTeams, predictNBA } from "@/services/api"
import type { Team, PredictionResult } from "@/types/nba"

function ProbBar({ homeProb, homeName, awayName }: { homeProb: number; homeName: string; awayName: string }) {
  const homePct = Math.round(homeProb * 100)
  const awayPct = 100 - homePct
  return (
    <div className="mt-6">
      <div className="flex justify-between text-sm font-semibold text-white mb-2">
        <span>{awayName}</span>
        <span>{homeName}</span>
      </div>
      <div className="flex h-4 rounded-full overflow-hidden">
        <div
          className="bg-[var(--red)] transition-all duration-500"
          style={{ width: `${awayPct}%` }}
        />
        <div
          className="bg-[var(--green)] transition-all duration-500"
          style={{ width: `${homePct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-[var(--text-muted)] mt-1">
        <span>{awayPct}%</span>
        <span>{homePct}%</span>
      </div>
    </div>
  )
}

function PredictContent() {
  const params = useSearchParams()
  const [teams, setTeams] = useState<Team[]>([])
  const [homeId, setHomeId] = useState(params.get("home") ?? "")
  const [awayId, setAwayId] = useState(params.get("away") ?? "")
  const [result, setResult] = useState<PredictionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTeams().then((r) => setTeams(r.teams)).catch(() => {})
  }, [])

  async function handlePredict() {
    if (!homeId || !awayId) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await predictNBA(homeId, awayId)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prediction failed")
    } finally {
      setLoading(false)
    }
  }

  const winner = result
    ? result.predicted_winner === "home"
      ? result.home_team_name
      : result.away_team_name
    : null

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">NBA Game Predictor</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        Select two teams to get win probabilities from our ML model.
      </p>

      {/* Team selectors */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 mb-6">
        <div className="grid sm:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1.5 font-medium uppercase tracking-wide">
              Away Team
            </label>
            <select
              value={awayId}
              onChange={(e) => setAwayId(e.target.value)}
              className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="">Select team...</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--text-muted)] mb-1.5 font-medium uppercase tracking-wide">
              Home Team
            </label>
            <select
              value={homeId}
              onChange={(e) => setHomeId(e.target.value)}
              className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="">Select team...</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          onClick={handlePredict}
          disabled={!homeId || !awayId || loading}
          className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
        >
          {loading ? "Predicting..." : "Predict"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded-xl p-4 mb-6 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide font-medium">
              Predicted winner
            </p>
            <span className="text-sm font-bold text-[var(--green)]">{winner}</span>
          </div>

          <ProbBar
            homeProb={result.home_win_probability}
            homeName={result.home_team_name}
            awayName={result.away_team_name}
          />

          {/* Feature breakdown */}
          <div className="mt-6 border-t border-[var(--border)] pt-4">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide font-medium mb-3">
              Model features
            </p>
            <div className="grid gap-1.5">
              {Object.entries(result.features_used).map(([key, val]) => (
                <div key={key} className="flex items-center justify-between text-xs">
                  <span className="text-[var(--text-muted)] font-mono">{key}</span>
                  <span
                    className={`font-semibold tabular-nums ${
                      val > 0 ? "text-[var(--green)]" : val < 0 ? "text-[var(--red)]" : "text-white"
                    }`}
                  >
                    {val > 0 ? "+" : ""}
                    {val.toFixed(4)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-[var(--border)] flex justify-between text-xs text-[var(--text-muted)]">
            <span>Model accuracy: {(result.model_metrics.accuracy * 100).toFixed(1)}%</span>
            <span>Trained on {result.model_metrics.train_games} games</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default function PredictPage() {
  return (
    <Suspense>
      <PredictContent />
    </Suspense>
  )
}
