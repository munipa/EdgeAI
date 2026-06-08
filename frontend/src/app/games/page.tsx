import { getTodaysGames } from "@/services/api"
import Link from "next/link"

export default async function GamesPage() {
  let games: Awaited<ReturnType<typeof getTodaysGames>> = []
  try {
    games = await getTodaysGames()
  } catch {
    // backend may be offline
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">{"Today's NBA Games"}</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        Live and scheduled games for today
      </p>

      {games.length === 0 ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center">
          <p className="text-[var(--text-muted)]">No games today or unable to reach the API.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {games.map((g) => (
            <div
              key={g.id}
              className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5"
            >
              <div className="flex items-center justify-between">
                {/* Away */}
                <div className="flex-1 text-center">
                  <p className="text-lg font-bold text-white">{g.away_team.score}</p>
                  <p className="text-sm text-[var(--text-muted)]">{g.away_team.name}</p>
                  <p className="text-xs text-[var(--text-muted)]">Away</p>
                </div>

                <div className="px-4 text-center">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      g.status === "Final"
                        ? "bg-[var(--surface-2)] text-[var(--text-muted)]"
                        : "bg-green-900/40 text-green-400"
                    }`}
                  >
                    {g.status}
                  </span>
                  <p className="text-[var(--text-muted)] text-xs mt-1">vs</p>
                </div>

                {/* Home */}
                <div className="flex-1 text-center">
                  <p className="text-lg font-bold text-white">{g.home_team.score}</p>
                  <p className="text-sm text-[var(--text-muted)]">{g.home_team.name}</p>
                  <p className="text-xs text-[var(--text-muted)]">Home</p>
                </div>

                <div className="ml-6">
                  <Link
                    href={`/predict?home=${g.home_team.id}&away=${g.away_team.id}`}
                    className="text-sm text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium"
                  >
                    Predict →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
