import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Home from './pages/Home';
import TextBrowser from './pages/TextBrowser';
import TextReader from './pages/TextReader';
import InscriptionWorkbench from './pages/InscriptionWorkbench';

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl">Loading...</div>
      </div>
    );
  }
  
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      
      <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
        <Route index element={<Home />} />
        <Route path="browse" element={<TextBrowser />} />
        <Route path="text/:textId" element={<TextReader />} />
        <Route path="inscriptions" element={<InscriptionWorkbench />} />
      </Route>
    </Routes>
  );
}

export default App;

