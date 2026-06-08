"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const NAV = [
  { href: "/", label: "Dashboard", icon: "⚡" },
  { href: "/games", label: "Games", icon: "🏀" },
  { href: "/predict", label: "Predict", icon: "🎯" },
  { href: "/standings", label: "Standings", icon: "📊" },
  { href: "/teams", label: "Teams", icon: "🏆" },
  { href: "/injuries", label: "Injuries", icon: "🩹" },
  { href: "/tennis", label: "Tennis", icon: "🎾" },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-[var(--border)] bg-[var(--surface)] min-h-screen">
      <div className="px-5 py-6 border-b border-[var(--border)]">
        <span className="text-lg font-bold tracking-tight text-white">EdgeAI</span>
        <p className="text-xs text-[var(--text-muted)] mt-0.5">Sports Predictions</p>
      </div>

      <nav className="flex-1 py-4 px-3 space-y-1">
        {NAV.map(({ href, label, icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-white"
              }`}
            >
              <span>{icon}</span>
              {label}
            </Link>
          )
        })}
      </nav>

      <div className="px-5 py-4 border-t border-[var(--border)]">
        <p className="text-xs text-[var(--text-muted)]">Model accuracy</p>
        <p className="text-sm font-semibold text-white">73.6%</p>
      </div>
    </aside>
  )
}
