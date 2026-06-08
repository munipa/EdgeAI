import { getStandings } from "@/services/api"

export default async function StandingsPage() {
  let standings: Awaited<ReturnType<typeof getStandings>> | null = null
  try {
    standings = await getStandings()
  } catch {
    // backend offline
  }

  const conferences = standings
    ? [
        { label: "Eastern Conference", rows: standings.east },
        { label: "Western Conference", rows: standings.west },
      ]
    : []

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">NBA Standings</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">Current season standings</p>

      {!standings ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center">
          <p className="text-[var(--text-muted)]">Unable to load standings.</p>
        </div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-6">
          {conferences.map(({ label, rows }) => (
            <div
              key={label}
              className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden"
            >
              <div className="px-4 py-3 border-b border-[var(--border)]">
                <h2 className="text-sm font-semibold text-white">{label}</h2>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-left px-4 py-2 text-[var(--text-muted)] font-medium w-6">#</th>
                    <th className="text-left px-4 py-2 text-[var(--text-muted)] font-medium">Team</th>
                    <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">W</th>
                    <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">L</th>
                    <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">PCT</th>
                    <th className="text-right px-4 py-2 text-[var(--text-muted)] font-medium">GB</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr
                      key={row.team}
                      className={`border-b border-[var(--border)] last:border-0 ${
                        i < 6 ? "text-white" : "text-[var(--text-muted)]"
                      }`}
                    >
                      <td className="px-4 py-2">{i + 1}</td>
                      <td className="px-4 py-2 font-medium">{row.team}</td>
                      <td className="px-4 py-2 text-right">{row.wins}</td>
                      <td className="px-4 py-2 text-right">{row.losses}</td>
                      <td className="px-4 py-2 text-right">{row.pct?.toFixed(3)}</td>
                      <td className="px-4 py-2 text-right">{row.gb === 0 ? "—" : row.gb}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
