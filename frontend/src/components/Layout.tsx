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
    <div className="h-screen flex flex-col overflow-hidden bg-gray-50 font-sans text-gray-800">
      {/* Top Navigation Bar */}
      <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shrink-0 z-10">
        <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">H</div>
                <span className="font-semibold text-lg">Helios</span>
            </Link>
            
            <nav className="hidden md:flex gap-4">
                 <Link
                    to="/browse"
                    className="text-sm font-medium text-gray-600 hover:text-gray-900 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
                  >
                    Browse
                  </Link>
            </nav>
        </div>

        <div className="flex items-center gap-4">
            <button 
                onClick={handleLogout}
                className="p-2 hover:bg-gray-100 rounded-full text-gray-600" 
                title="Logout"
            >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
            </button>
            <div className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-600 font-medium text-sm select-none" title={user?.email || ''}>
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
