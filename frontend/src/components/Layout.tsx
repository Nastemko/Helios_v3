import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  // Get initials for avatar
  const initials = user?.email 
    ? user.email.substring(0, 2).toUpperCase() 
    : 'UN';

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-helios-cream font-sans text-gray-800">
      {/* Top Navigation Bar */}
      <header className="h-14 bg-helios-teal flex items-center justify-between px-4 shrink-0 z-10">
        <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2.5">
                <img src="/helios-logo.png" alt="Helios" className="w-9 h-9 object-contain" />
                <span className="font-semibold text-lg text-white">Helios</span>
            </Link>
            
            <nav className="hidden md:flex gap-4">
                 <Link
                    to="/browse"
                    className="text-sm font-medium text-white/80 hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors"
                  >
                    Browse
                  </Link>
            </nav>
        </div>

        <div className="flex items-center gap-4">
            <button 
                onClick={handleLogout}
                className="p-2 hover:bg-white/10 rounded-full text-white/80 hover:text-white transition-colors" 
                title="Logout"
            >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
            </button>
            <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center text-white font-medium text-sm select-none" title={user?.email || ''}>
                {initials}
            </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden relative">
        <Outlet />
      </main>
    </div>
  );
}
