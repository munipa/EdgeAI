import { getTeams } from "@/services/api"
import Link from "next/link"

export default async function TeamsPage() {
  let result: Awaited<ReturnType<typeof getTeams>> | null = null
  try {
    result = await getTeams()
  } catch {
    // backend offline
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">NBA Teams</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        {result ? `${result.count} teams` : "Loading..."}
      </p>

      {!result ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center">
          <p className="text-[var(--text-muted)]">Unable to load teams.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {result.teams.map((team) => (
            <div
              key={team.id}
              className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 flex items-center gap-3 hover:border-[var(--accent)] transition-colors"
            >
              {team.logo && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={team.logo} alt={team.name} className="w-10 h-10 object-contain" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-white truncate">{team.name}</p>
                <p className="text-xs text-[var(--text-muted)]">{team.abbreviation}</p>
              </div>
              <Link
                href={`/predict?home=${team.id}`}
                className="text-xs text-[var(--accent)] hover:text-[var(--accent-hover)] shrink-0"
              >
                Predict →
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
