import type { VaultItem, NavCategory } from '../types'
import { SearchIcon, StarIcon, CreditCardIcon, UserIcon, KeyIcon, NoteIcon } from './Icons'

const CATEGORY_TITLES: Record<NavCategory, string> = {
  all: 'All Items',
  favorites: 'Favorites',
  login: 'Logins',
  card: 'Payment Cards',
  identity: 'Identities',
  note: 'Secure Notes',
}

function itemSubtitle(item: VaultItem): string {
  if (item.type === 'card' && item.card) {
    return `${item.card.brand} • ••••${item.card.number.slice(-4)}`
  }
  if (item.type === 'identity' && item.identity) {
    return [item.identity.firstName, item.identity.lastName].filter(Boolean).join(' ')
  }
  if (item.type === 'login' && item.login) {
    return item.login.username
  }
  return 'Secure note'
}

function ItemIcon({ item }: { item: VaultItem }) {
  const base = 'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0'
  if (item.type === 'card')
    return (
      <div className={`${base} bg-blue-100 text-blue-600`}>
        <CreditCardIcon className="w-4 h-4" />
      </div>
    )
  if (item.type === 'identity')
    return (
      <div className={`${base} bg-violet-100 text-violet-600`}>
        <UserIcon className="w-4 h-4" />
      </div>
    )
  if (item.type === 'login')
    return (
      <div className={`${base} bg-amber-100 text-amber-600`}>
        <KeyIcon className="w-4 h-4" />
      </div>
    )
  return (
    <div className={`${base} bg-slate-100 text-slate-500`}>
      <NoteIcon className="w-4 h-4" />
    </div>
  )
}

interface ItemListProps {
  items: VaultItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  search: string
  onSearch: (s: string) => void
  loading: boolean
  category: NavCategory
}

export default function ItemList({
  items,
  selectedId,
  onSelect,
  search,
  onSearch,
  loading,
  category,
}: ItemListProps) {
  return (
    <div className="w-80 bg-slate-50 border-r border-slate-200 flex flex-col flex-shrink-0">
      <div className="p-3 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 mb-2.5">
          <h2 className="font-semibold text-slate-800 text-sm flex-1">
            {CATEGORY_TITLES[category]}
          </h2>
          <span className="text-xs text-slate-400 tabular-nums">
            {items.length} item{items.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="relative">
          <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 w-3.5 h-3.5" />
          <input
            type="text"
            value={search}
            onChange={e => onSearch(e.target.value)}
            placeholder="Search..."
            className="w-full pl-8 pr-3 py-2 text-sm bg-slate-100 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-colors"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-slate-400 text-sm">
            Loading...
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-slate-400 text-sm">
            No items found
          </div>
        ) : (
          <ul>
            {items.map(item => (
              <li key={item.id}>
                <button
                  onClick={() => onSelect(item.id)}
                  className={`w-full text-left px-4 py-3 border-b border-slate-200 flex items-center gap-3 transition-colors ${
                    selectedId === item.id
                      ? 'bg-blue-50 border-l-2 border-l-blue-600 pl-3'
                      : 'hover:bg-white'
                  }`}
                >
                  <ItemIcon item={item} />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-slate-800 text-sm truncate">{item.name}</div>
                    <div className="text-slate-500 text-xs truncate mt-0.5">
                      {itemSubtitle(item)}
                    </div>
                  </div>
                  {item.favorite && (
                    <StarIcon className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
