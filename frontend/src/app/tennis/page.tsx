import { getTodaysTennisMatches } from "@/services/api"

export default async function TennisPage() {
  let matches: Awaited<ReturnType<typeof getTodaysTennisMatches>> = []
  try {
    matches = await getTodaysTennisMatches()
  } catch {
    // backend offline
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">{"Today's Tennis"}</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        ATP/WTA matches scheduled today
      </p>

      {matches.length === 0 ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center">
          <p className="text-[var(--text-muted)]">No matches today or unable to reach the API.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {matches.map((m) => (
            <div
              key={m.id}
              className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-[var(--text-muted)] uppercase tracking-wide">
                  {m.tournament} · {m.surface} · {m.round}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    m.status === "Final"
                      ? "bg-[var(--surface-2)] text-[var(--text-muted)]"
                      : "bg-green-900/40 text-green-400"
                  }`}
                >
                  {m.status}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-sm font-semibold text-white">{m.player1.name}</p>
                  <p className="text-xs text-[var(--text-muted)]">{m.player1.country}</p>
                </div>
                <span className="text-[var(--text-muted)] px-4">vs</span>
                <div className="flex-1 text-right">
                  <p className="text-sm font-semibold text-white">{m.player2.name}</p>
                  <p className="text-xs text-[var(--text-muted)]">{m.player2.country}</p>
                </div>
              </div>
              {m.score && (
                <p className="text-xs text-[var(--text-muted)] mt-2 text-center">{m.score}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
