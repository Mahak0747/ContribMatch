import { useCallback, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-violet-500 focus:px-3 focus:py-2 focus:text-white">
        Skip to content
      </a>
      <Navbar variant="app" onMenu={() => setOpen(true)} />
      <div className="mx-auto flex max-w-7xl">
        <Sidebar open={open} onClose={close} />
        <main id="main" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
