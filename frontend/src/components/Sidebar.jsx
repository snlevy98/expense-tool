import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  CreditCard,
  Upload,
  PiggyBank,
  History,
  BarChart2,
  Settings,
  LogOut,
  Wallet,
  Tag,
  ShoppingCart,
  X,
} from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useAppStore } from '../store/appStore'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/transactions', icon: CreditCard, label: 'Transactions' },
  { to: '/import', icon: Upload, label: 'Import' },
  { to: '/categorize', icon: Tag, label: 'Categorize', badgeKey: 'uncategorized' },
  { to: '/amazon', icon: ShoppingCart, label: 'Amazon', badgeKey: 'amazon' },
  { to: '/budgets', icon: PiggyBank, label: 'Budgets' },
  { to: '/budget-history', icon: History, label: 'History' },
  { to: '/reports', icon: BarChart2, label: 'Reports' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar({ isOpen, onClose }) {
  const signOut = useAuthStore((s) => s.signOut)
  const uncategorizedCount = useAppStore((s) => s.uncategorizedCount)
  const amazonUncategorizedCount = useAppStore((s) => s.amazonUncategorizedCount)

  const badgeCounts = {
    uncategorized: uncategorizedCount,
    amazon: amazonUncategorizedCount,
  }

  return (
    <aside
      className={`
        fixed inset-y-0 left-0 z-40 w-64 bg-slate-800 flex flex-col
        transform transition-transform duration-200 ease-in-out
        lg:static lg:translate-x-0 lg:shrink-0
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
      `}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-700">
        <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center shrink-0">
          <Wallet size={18} className="text-white" />
        </div>
        <span className="text-white font-semibold text-lg flex-1">Expense Tracker</span>
        {/* Close button — mobile only */}
        <button
          onClick={onClose}
          className="lg:hidden p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          aria-label="Close menu"
        >
          <X size={20} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label, badgeKey }) => {
          const count = badgeKey ? badgeCounts[badgeKey] : 0
          return (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                }`
              }
            >
              <Icon size={18} />
              <span className="flex-1">{label}</span>
              {count > 0 && (
                <span className="bg-amber-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                  {count > 99 ? '99+' : count}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* Sign out */}
      <div className="px-3 py-4 border-t border-slate-700">
        <button
          onClick={signOut}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
        >
          <LogOut size={18} />
          Sign Out
        </button>
      </div>
    </aside>
  )
}
