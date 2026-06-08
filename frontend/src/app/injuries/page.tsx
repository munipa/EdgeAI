import { getInjuries } from "@/services/api"

const STATUS_STYLES: Record<string, string> = {
  Out: "bg-red-900/40 text-red-400",
  Doubtful: "bg-orange-900/40 text-orange-400",
  Questionable: "bg-yellow-900/40 text-yellow-400",
  "Day-To-Day": "bg-yellow-900/40 text-yellow-400",
  Suspension: "bg-purple-900/40 text-purple-400",
}

export default async function InjuriesPage() {
  let injuries: Awaited<ReturnType<typeof getInjuries>> | null = null
  try {
    injuries = await getInjuries()
  } catch {
    // backend offline
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">NBA Injury Report</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        {injuries ? `${injuries.count} active reports` : "Loading..."}
      </p>

      {!injuries ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center">
          <p className="text-[var(--text-muted)]">Unable to load injury data.</p>
        </div>
      ) : (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="text-left px-4 py-3 text-[var(--text-muted)] font-medium">Player</th>
                <th className="text-left px-4 py-3 text-[var(--text-muted)] font-medium">Status</th>
                <th className="text-left px-4 py-3 text-[var(--text-muted)] font-medium hidden md:table-cell">
                  Notes
                </th>
              </tr>
            </thead>
            <tbody>
              {injuries.injuries.map((inj, i) => (
                <tr
                  key={i}
                  className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-2)] transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-white">{inj.player_name}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        STATUS_STYLES[inj.status] ?? "bg-[var(--surface-2)] text-[var(--text-muted)]"
                      }`}
                    >
                      {inj.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--text-muted)] hidden md:table-cell max-w-xs truncate">
                    {inj.comment ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
