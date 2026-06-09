import { getGames } from "@/services/api"
import type { Game } from "@/types/nba"
import Link from "next/link"

function formatTipoff(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  })
}

function dateLabel(offsetDays: number): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  if (offsetDays === 0) return "Today"
  if (offsetDays === 1) return "Tomorrow"
  return d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })
}

function yyyymmdd(offsetDays: number): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10).replace(/-/g, "")
}

function StatusBadge({ status }: { status: string }) {
  const live = !["Final", "Scheduled", "Postponed", "Canceled"].includes(status)
  if (status === "Final") {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-[var(--surface-2)] text-[var(--text-muted)]">
        Final
      </span>
    )
  }
  if (live) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-green-900/40 text-green-400 flex items-center gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
        {status}
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-[var(--surface-2)] text-[var(--text-muted)]">
      {status}
    </span>
  )
}

function GameCard({ game }: { game: Game }) {
  const isScheduled = game.status === "Scheduled"
  const isFinal = game.status === "Final"
  const homeWon = isFinal && Number(game.home_team.score) > Number(game.away_team.score)
  const awayWon = isFinal && Number(game.away_team.score) > Number(game.home_team.score)

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)]/40 transition-colors">
      <div className="flex items-center gap-4">
        {/* Away team */}
        <div className="flex-1 flex items-center gap-3">
          {game.away_team.logo && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={game.away_team.logo} alt="" className="w-10 h-10 object-contain shrink-0" />
          )}
          <div>
            <p className={`text-sm font-semibold ${awayWon ? "text-white" : isFinal ? "text-[var(--text-muted)]" : "text-white"}`}>
              {game.away_team.name}
            </p>
            <p className="text-xs text-[var(--text-muted)]">Away</p>
          </div>
        </div>

        {/* Score / time */}
        <div className="text-center shrink-0 min-w-[90px]">
          {isScheduled ? (
            <p className="text-sm font-medium text-[var(--text-muted)]">
              {formatTipoff(game.date)}
            </p>
          ) : (
            <p className="text-xl font-bold text-white tabular-nums">
              {game.away_team.score} – {game.home_team.score}
            </p>
          )}
          <div className="mt-1 flex justify-center">
            <StatusBadge status={game.status} />
          </div>
        </div>

        {/* Home team */}
        <div className="flex-1 flex items-center gap-3 justify-end">
          <div className="text-right">
            <p className={`text-sm font-semibold ${homeWon ? "text-white" : isFinal ? "text-[var(--text-muted)]" : "text-white"}`}>
              {game.home_team.name}
            </p>
            <p className="text-xs text-[var(--text-muted)]">Home</p>
          </div>
          {game.home_team.logo && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={game.home_team.logo} alt="" className="w-10 h-10 object-contain shrink-0" />
          )}
        </div>
      </div>

      {/* Predict link */}
      <div className="mt-3 pt-3 border-t border-[var(--border)] flex justify-end">
        <Link
          href={`/predict?home=${game.home_team.id}&away=${game.away_team.id}`}
          className="text-xs text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium"
        >
          Get prediction →
        </Link>
      </div>
    </div>
  )
}

function DaySection({ label, games }: { label: string; games: Game[] }) {
  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-white mb-3">{label}</h2>
      {games.length === 0 ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 text-center">
          <p className="text-[var(--text-muted)] text-sm">No games scheduled.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {games.map((g) => (
            <GameCard key={g.id} game={g} />
          ))}
        </div>
      )}
    </section>
  )
}

export default async function GamesPage() {
  const [todayGames, tomorrowGames] = await Promise.all([
    getGames(yyyymmdd(0)).catch(() => [] as Game[]),
    getGames(yyyymmdd(1)).catch(() => [] as Game[]),
  ])

  const total = todayGames.length + tomorrowGames.length

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">NBA Games</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        {total === 0 ? "No games in the next 2 days." : `${total} game${total !== 1 ? "s" : ""} scheduled`}
      </p>

      <DaySection label={dateLabel(0)} games={todayGames} />
      <DaySection label={dateLabel(1)} games={tomorrowGames} />
    </div>
  )
}
