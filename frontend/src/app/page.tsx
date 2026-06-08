import { getTodaysGames, getInjuries } from "@/services/api"
import StatCard from "@/components/StatCard"
import Link from "next/link"

export default async function DashboardPage() {
  const [games, injuriesRes] = await Promise.allSettled([
    getTodaysGames(),
    getInjuries(),
  ])

  const todaysGames = games.status === "fulfilled" ? games.value : []
  const injuryCount =
    injuriesRes.status === "fulfilled" ? injuriesRes.value.count : 0

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-1">Dashboard</h1>
      <p className="text-[var(--text-muted)] text-sm mb-8">
        {new Date().toLocaleDateString("en-US", {
          weekday: "long",
          month: "long",
          day: "numeric",
          year: "numeric",
        })}
      </p>

      {/* Stat row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <StatCard label="Games Today" value={todaysGames.length} />
        <StatCard label="Active Injuries" value={injuryCount} />
        <StatCard label="Model Accuracy" value="73.6%" accent />
        <StatCard label="Sports" value="NBA + Tennis" />
      </div>

      {/* Today's games */}
      <section className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-white">{"Today's Games"}</h2>
          <Link
            href="/games"
            className="text-xs text-[var(--accent)] hover:text-[var(--accent-hover)]"
          >
            See all →
          </Link>
        </div>

        {todaysGames.length === 0 ? (
          <p className="text-[var(--text-muted)] text-sm">No games scheduled today.</p>
        ) : (
          <div className="grid gap-3">
            {todaysGames.map((g) => (
              <div
                key={g.id}
                className="bg-[var(--surface)] border border-[var(--border)] rounded-xl px-5 py-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-white">{g.away_team.name}</span>
                  <span className="text-xs text-[var(--text-muted)]">@</span>
                  <span className="text-sm font-medium text-white">{g.home_team.name}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      g.status === "Final"
                        ? "bg-[var(--surface-2)] text-[var(--text-muted)]"
                        : "bg-green-900/40 text-green-400"
                    }`}
                  >
                    {g.status}
                  </span>
                  <Link
                    href={`/predict?home=${g.home_team.id}&away=${g.away_team.id}`}
                    className="text-xs text-[var(--accent)] hover:text-[var(--accent-hover)]"
                  >
                    Predict →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Quick links */}
      <section>
        <h2 className="text-base font-semibold text-white mb-4">Quick links</h2>
        <div className="grid sm:grid-cols-3 gap-3">
          {[
            { href: "/predict", label: "Predict a game", icon: "🎯", sub: "Pick any two teams" },
            { href: "/standings", label: "Standings", icon: "📊", sub: "Full conference tables" },
            { href: "/injuries", label: "Injury report", icon: "🩹", sub: `${injuryCount} active reports` },
          ].map(({ href, label, icon, sub }) => (
            <Link
              key={href}
              href={href}
              className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--accent)] rounded-xl p-4 transition-colors"
            >
              <span className="text-xl">{icon}</span>
              <p className="text-sm font-semibold text-white mt-2">{label}</p>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">{sub}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
