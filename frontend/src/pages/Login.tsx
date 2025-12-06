import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Login() {
  const { isAuthenticated, login, devLogin, isLoading } = useAuth();
  const navigate = useNavigate();
  const [devLoginError, setDevLoginError] = useState<string | null>(null);
  const [isDevLoggingIn, setIsDevLoggingIn] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  const handleDevLogin = async () => {
    setDevLoginError(null);
    setIsDevLoggingIn(true);
    try {
      await devLogin();
    } catch (error: any) {
      setDevLoginError(error.response?.data?.detail || 'Dev login failed');
    } finally {
      setIsDevLoggingIn(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-helios-cream">
        <div className="text-xl text-helios-teal">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-helios-cream">
      {/* Decorative background pattern */}
      <div className="absolute inset-0 opacity-5">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-helios-gold rounded-full blur-3xl"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-helios-teal rounded-full blur-3xl"></div>
      </div>
      
      <div className="relative bg-white p-10 rounded-2xl shadow-xl max-w-md w-full border border-helios-cream-dark">
        <div className="text-center mb-8">
          <img 
            src="/helios-logo.png" 
            alt="Helios" 
            className="w-32 h-32 mx-auto mb-6 drop-shadow-md"
          />
          <h1 className="text-4xl font-bold mb-2 text-helios-teal">Helios</h1>
          <p className="text-gray-600">
            Your digital companion for classical languages
          </p>
        </div>
        
        <div className="space-y-4">
          <p className="text-sm text-gray-600 text-center">
            Read and analyze ancient Greek and Latin texts with AI-powered tools
          </p>
          
          <button
            onClick={login}
            className="w-full flex items-center justify-center gap-3 bg-white border-2 border-gray-200 rounded-xl py-3 px-4 hover:bg-helios-cream hover:border-helios-gold transition duration-200"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            <span className="font-medium text-gray-700">Continue with Google</span>
          </button>
          
          {/* Dev Login - for local development */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-helios-cream-dark"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-gray-500">or for development</span>
            </div>
          </div>
          
          <button
            onClick={handleDevLogin}
            disabled={isDevLoggingIn}
            className="w-full flex items-center justify-center gap-2 bg-helios-gold hover:bg-helios-gold-light text-helios-teal-dark rounded-xl py-3 px-4 transition duration-200 disabled:opacity-50 font-medium"
          >
            <span className="text-lg">🔧</span>
            <span>
              {isDevLoggingIn ? 'Logging in...' : 'Dev Login (No OAuth)'}
            </span>
          </button>
          
          {devLoginError && (
            <p className="text-sm text-red-500 text-center">{devLoginError}</p>
          )}
          
          <p className="text-xs text-gray-500 text-center mt-4">
            By signing in, you agree to use this educational tool responsibly
          </p>
        </div>
      </div>
    </div>
  );
}
