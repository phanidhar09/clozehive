import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Navbar from './Navbar'

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 lg:ml-[260px]">
        <Navbar />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6 animate-fade-in">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
