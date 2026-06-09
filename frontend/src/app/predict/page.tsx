"use client"

import { useEffect, useState, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { getTeams, predictNBA, getInjuries } from "@/services/api"
import type { Team, PredictionResult, Injury } from "@/types/nba"

const FEATURE_LABELS: Record<string, string> = {
  form_5_diff: "Form (last 5 games)",
  form_10_diff: "Form (last 10 games)",
  pts_scored_diff: "Avg points scored diff",
  pts_allowed_diff: "Avg points allowed diff",
  home_win_pct_home: "Home team win % at home",
  away_win_pct_away: "Away team win % on road",
  injury_adj_off_rating_diff: "Injury-adj offensive rating diff",
  injury_adj_def_rating_diff: "Injury-adj defensive rating diff",
  injury_impact_diff: "Injury impact diff",
  superstar_out_diff: "Superstar out diff",
}

const STATUS_STYLES: Record<string, string> = {
  Out: "bg-red-900/40 text-red-400",
  Doubtful: "bg-orange-900/40 text-orange-400",
  Questionable: "bg-yellow-900/40 text-yellow-400",
  "Day-To-Day": "bg-yellow-900/40 text-yellow-400",
  Suspension: "bg-purple-900/40 text-purple-400",
}

function ProbBar({
  homeProb,
  homeName,
  awayName,
}: {
  homeProb: number
  homeName: string
  awayName: string
}) {
  const homePct = Math.round(homeProb * 100)
  const awayPct = 100 - homePct
  const homeWins = homeProb >= 0.5

  return (
    <div className="mt-2">
      <div className="flex justify-between text-sm font-semibold mb-2">
        <span className={!homeWins ? "text-[var(--green)]" : "text-[var(--text-muted)]"}>
          {awayName}
          {!homeWins && " ✓"}
        </span>
        <span className={homeWins ? "text-[var(--green)]" : "text-[var(--text-muted)]"}>
          {homeWins && "✓ "}
          {homeName}
        </span>
      </div>
      <div className="flex h-5 rounded-full overflow-hidden">
        <div
          className="bg-[var(--red)] transition-all duration-700 flex items-center justify-end pr-2"
          style={{ width: `${awayPct}%` }}
        >
          {awayPct > 15 && (
            <span className="text-white text-xs font-bold">{awayPct}%</span>
          )}
        </div>
        <div
          className="bg-[var(--green)] transition-all duration-700 flex items-center justify-start pl-2"
          style={{ width: `${homePct}%` }}
        >
          {homePct > 15 && (
            <span className="text-white text-xs font-bold">{homePct}%</span>
          )}
        </div>
      </div>
      <div className="flex justify-between text-xs text-[var(--text-muted)] mt-1">
        <span>Away</span>
        <span>Home</span>
      </div>
    </div>
  )
}

function TeamSelect({
  label,
  value,
  teams,
  onChange,
  exclude,
}: {
  label: string
  value: string
  teams: Team[]
  onChange: (id: string) => void
  exclude: string
}) {
  const selected = teams.find((t) => t.id === value)

  return (
    <div>
      <label className="block text-xs text-[var(--text-muted)] mb-1.5 font-medium uppercase tracking-wide">
        {label}
      </label>
      <div className="relative">
        {selected?.logo && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={selected.logo}
            alt=""
            className="absolute left-3 top-1/2 -translate-y-1/2 w-6 h-6 object-contain pointer-events-none"
          />
        )}
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={`w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg py-2.5 pr-3 text-sm text-white focus:outline-none focus:border-[var(--accent)] appearance-none ${
            selected?.logo ? "pl-11" : "pl-3"
          }`}
        >
          <option value="">Select team...</option>
          {teams
            .filter((t) => t.id !== exclude)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
        </select>
      </div>
    </div>
  )
}

function InjuryList({ teamId, injuries }: { teamId: string; injuries: Injury[] }) {
  const teamInjuries = injuries.filter((i) => i.team_id === teamId)
  if (teamInjuries.length === 0) return <p className="text-xs text-[var(--text-muted)]">No active injuries</p>

  return (
    <div className="space-y-1.5">
      {teamInjuries.map((inj, i) => (
        <div key={i} className="flex items-center justify-between gap-2">
          <span className="text-xs text-white truncate">{inj.player_name}</span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${
              STATUS_STYLES[inj.status] ?? "bg-[var(--surface-2)] text-[var(--text-muted)]"
            }`}
          >
            {inj.status}
          </span>
        </div>
      ))}
    </div>
  )
}

function PredictContent() {
  const params = useSearchParams()
  const [teams, setTeams] = useState<Team[]>([])
  const [injuries, setInjuries] = useState<Injury[]>([])
  const [homeId, setHomeId] = useState(params.get("home") ?? "")
  const [awayId, setAwayId] = useState(params.get("away") ?? "")
  const [result, setResult] = useState<PredictionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTeams().then((r) => setTeams(r.teams)).catch(() => {})
    getInjuries().then((r) => setInjuries(r.injuries)).catch(() => {})
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

  const homeTeam = teams.find((t) => t.id === homeId)
  const awayTeam = teams.find((t) => t.id === awayId)

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">NBA Game Predictor</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        Select two teams to get win probabilities from our ML model.
      </p>

      {/* Team selectors */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 mb-4">
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <TeamSelect
            label="Away Team"
            value={awayId}
            teams={teams}
            onChange={(id) => { setAwayId(id); setResult(null) }}
            exclude={homeId}
          />
          <TeamSelect
            label="Home Team"
            value={homeId}
            teams={teams}
            onChange={(id) => { setHomeId(id); setResult(null) }}
            exclude={awayId}
          />
        </div>

        <button
          onClick={handlePredict}
          disabled={!homeId || !awayId || loading}
          className="w-full bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
        >
          {loading ? "Predicting..." : "Predict"}
        </button>
      </div>

      {/* Injury context for selected teams */}
      {(homeId || awayId) && injuries.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-3 mb-6">
          {awayId && awayTeam && (
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
                {awayTeam.name} injuries
              </p>
              <InjuryList teamId={awayId} injuries={injuries} />
            </div>
          )}
          {homeId && homeTeam && (
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
                {homeTeam.name} injuries
              </p>
              <InjuryList teamId={homeId} injuries={injuries} />
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded-xl p-4 mb-6 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide font-medium mb-4">
            Prediction
          </p>

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
            <div className="grid gap-2">
              {Object.entries(result.features_used).map(([key, val]) => (
                <div key={key} className="flex items-center justify-between gap-4">
                  <span className="text-xs text-[var(--text-muted)]">
                    {FEATURE_LABELS[key] ?? key}
                  </span>
                  <span
                    className={`text-xs font-semibold tabular-nums shrink-0 ${
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
