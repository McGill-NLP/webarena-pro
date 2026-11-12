import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import type { VaultItem, User, NavCategory } from '../types'
import Sidebar from './Sidebar'
import ItemList from './ItemList'
import ItemDetail from './ItemDetail'

interface VaultProps {
  user: User
  onLogout: () => void
}

export default function Vault({ user, onLogout }: VaultProps) {
  const [items, setItems] = useState<VaultItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [category, setCategory] = useState<NavCategory>('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const loadItems = useCallback(async () => {
    try {
      const data = await api.items.list()
      setItems(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  const handleLogout = async () => {
    await api.logout()
    onLogout()
  }

  const handleCategorySelect = (c: NavCategory) => {
    setCategory(c)
    setSelectedId(null)
    setSearch('')
  }

  const filteredItems = items.filter(item => {
    if (category === 'favorites' && !item.favorite) return false
    if (category !== 'all' && category !== 'favorites' && item.type !== category) return false
    if (search) {
      return item.name.toLowerCase().includes(search.toLowerCase())
    }
    return true
  })

  const selectedItem = items.find(i => i.id === selectedId) ?? null

  return (
    <div className="flex h-screen bg-slate-100 overflow-hidden">
      <Sidebar
        category={category}
        onSelect={handleCategorySelect}
        items={items}
        user={user}
        onLogout={handleLogout}
      />
      <div className="flex flex-1 overflow-hidden">
        <ItemList
          items={filteredItems}
          selectedId={selectedId}
          onSelect={setSelectedId}
          search={search}
          onSearch={setSearch}
          loading={loading}
          category={category}
        />
        <ItemDetail item={selectedItem} />
      </div>
    </div>
  )
}
