import type { NavCategory, VaultItem, User } from '../types'
import {
  ShieldIcon,
  StarIcon,
  KeyIcon,
  CreditCardIcon,
  UserIcon,
  NoteIcon,
  LogOutIcon,
} from './Icons'

interface NavEntry {
  key: NavCategory
  label: string
}

const TOP_NAV: NavEntry[] = [
  { key: 'all', label: 'All Items' },
  { key: 'favorites', label: 'Favorites' },
]

const TYPE_NAV: NavEntry[] = [
  { key: 'login', label: 'Logins' },
  { key: 'card', label: 'Payment Cards' },
  { key: 'identity', label: 'Identities' },
  { key: 'note', label: 'Secure Notes' },
]

function NavIcon({ cat }: { cat: NavCategory }) {
  const cls = 'w-4 h-4'
  if (cat === 'all') return <ShieldIcon className={cls} />
  if (cat === 'favorites') return <StarIcon className={cls} />
  if (cat === 'login') return <KeyIcon className={cls} />
  if (cat === 'card') return <CreditCardIcon className={cls} />
  if (cat === 'identity') return <UserIcon className={cls} />
  return <NoteIcon className={cls} />
}

function NavLink({
  entry,
  active,
  count,
  onClick,
}: {
  entry: NavEntry
  active: boolean
  count: number
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
        active
          ? 'bg-slate-700 text-white'
          : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
      }`}
    >
      <span className="opacity-75">
        <NavIcon cat={entry.key} />
      </span>
      <span className="flex-1 text-left">{entry.label}</span>
      <span
        className={`text-xs px-1.5 py-0.5 rounded-full tabular-nums ${
          active ? 'bg-slate-600 text-slate-200' : 'bg-slate-700 text-slate-400'
        }`}
      >
        {count}
      </span>
    </button>
  )
}

interface SidebarProps {
  category: NavCategory
  onSelect: (c: NavCategory) => void
  items: VaultItem[]
  user: User
  onLogout: () => void
}

function countFor(items: VaultItem[], cat: NavCategory): number {
  if (cat === 'all') return items.length
  if (cat === 'favorites') return items.filter(i => i.favorite).length
  return items.filter(i => i.type === cat).length
}

export default function Sidebar({ category, onSelect, items, user, onLogout }: SidebarProps) {
  return (
    <div className="w-60 bg-slate-800 flex flex-col h-full flex-shrink-0">
      <div className="px-4 py-5 border-b border-slate-700">
        <div className="flex items-center gap-2.5">
          <ShieldIcon className="w-6 h-6 text-blue-400" />
          <span className="font-bold text-white text-lg tracking-tight">Vaultwise</span>
        </div>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {TOP_NAV.map(entry => (
          <NavLink
            key={entry.key}
            entry={entry}
            active={category === entry.key}
            count={countFor(items, entry.key)}
            onClick={() => onSelect(entry.key)}
          />
        ))}

        <div className="px-4 pt-5 pb-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Types
        </div>

        {TYPE_NAV.map(entry => (
          <NavLink
            key={entry.key}
            entry={entry}
            active={category === entry.key}
            count={countFor(items, entry.key)}
            onClick={() => onSelect(entry.key)}
          />
        ))}
      </nav>

      <div className="border-t border-slate-700 p-4">
        <div className="text-sm font-medium text-slate-300 mb-2 truncate">{user.username}</div>
        <button
          onClick={onLogout}
          className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          <LogOutIcon />
          Log out
        </button>
      </div>
    </div>
  )
}
