import { useState } from 'react'
import { Menu, Wallet } from 'lucide-react'
import Sidebar from './Sidebar'

export default function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="lg:hidden flex items-center gap-3 px-4 py-3 bg-slate-800 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
            aria-label="Open menu"
          >
            <Menu size={22} />
          </button>
          <div className="w-7 h-7 bg-indigo-500 rounded-lg flex items-center justify-center">
            <Wallet size={15} className="text-white" />
          </div>
          <span className="text-white font-semibold">Expense Tracker</span>
        </header>

        <main className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto p-4 sm:p-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
