import { useState, useEffect, useRef } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleLogout = async () => {
    setMobileMenuOpen(false);
    await logout();
    navigate('/login');
  };

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  // Close mobile menu when clicking outside
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMobileMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [mobileMenuOpen]);

  // Get initials for avatar
  const initials = user?.email 
    ? user.email.substring(0, 2).toUpperCase() 
    : 'UN';

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-helios-cream font-sans text-gray-800">
      {/* Top Navigation Bar */}
      <header ref={menuRef} className="bg-helios-teal shrink-0 z-10">
        <div className="h-14 flex items-center justify-between px-4">
          <div className="flex items-center gap-8">
              <Link to="/" className="flex items-center gap-2.5">
                  <img src="/helios-logo.png" alt="Helios" className="w-9 h-9 object-contain" />
                  <span className="font-semibold text-lg text-white">Helios</span>
              </Link>
              
              {/* Desktop nav links */}
              <nav className="hidden md:flex gap-1">
                   <Link
                      to="/browse"
                      className="text-sm font-medium text-white/80 hover:text-white px-3 py-1.5 rounded hover:bg-white/10 transition-colors"
                    >
                      Literary Texts
                    </Link>
                    <Link
                      to="/inscriptions"
                      className="text-sm font-medium text-white/80 hover:text-white px-3 py-1.5 rounded hover:bg-white/10 transition-colors flex items-center gap-1.5"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                      </svg>
                      Inscriptions
                    </Link>
              </nav>
          </div>

          <div className="flex items-center gap-3">
              {/* Hamburger button - mobile only */}
              <button
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="md:hidden p-2 hover:bg-white/10 rounded text-white/80 hover:text-white transition-colors"
                  aria-label="Toggle menu"
                  aria-expanded={mobileMenuOpen}
              >
                  {mobileMenuOpen ? (
                    // X icon
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : (
                    // Hamburger icon
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                  )}
              </button>

              <button 
                  onClick={handleLogout}
                  className="hidden md:block p-2 hover:bg-white/10 rounded-full text-white/80 hover:text-white transition-colors" 
                  title="Logout"
              >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
              </button>
              <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center text-white font-medium text-sm select-none" title={user?.email || ''}>
                  {initials}
              </div>
          </div>
        </div>

        {/* Mobile dropdown menu */}
        <div
          className={`md:hidden overflow-hidden transition-all duration-200 ease-in-out ${
            mobileMenuOpen ? 'max-h-60 border-t border-white/10' : 'max-h-0'
          }`}
        >
          <nav className="flex flex-col px-4 py-3 gap-1">
            <Link
              to="/browse"
              className="text-sm font-medium text-white/80 hover:text-white px-3 py-2.5 rounded hover:bg-white/10 transition-colors"
            >
              Literary Texts
            </Link>
            <Link
              to="/inscriptions"
              className="text-sm font-medium text-white/80 hover:text-white px-3 py-2.5 rounded hover:bg-white/10 transition-colors flex items-center gap-1.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              Inscriptions
            </Link>
            <div className="border-t border-white/10 mt-1 pt-2">
              <button
                onClick={handleLogout}
                className="w-full text-left text-sm font-medium text-white/80 hover:text-white px-3 py-2.5 rounded hover:bg-white/10 transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                Logout
              </button>
            </div>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden relative">
        <Outlet />
      </main>
    </div>
  );
}
