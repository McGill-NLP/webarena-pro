import { useState, useEffect } from 'react'
import { api } from './api'
import type { User } from './types'
import Login from './components/Login'
import Vault from './components/Vault'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="text-slate-400 text-sm">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return <Login onLogin={setUser} />
  }

  return <Vault user={user} onLogout={() => setUser(null)} />
}
