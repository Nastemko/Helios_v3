import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi } from '../services/api';

export default function Home() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: () => textApi.getStats(),
  });

  return (
    <div className="flex-1 overflow-y-auto bg-helios-cream">
      <div className="max-w-7xl mx-auto px-4 py-12">
        {/* Hero Section with Logo */}
        <div className="text-center mb-16">
          <img 
            src="/helios-logo.png" 
            alt="Helios" 
            className="w-48 h-48 mx-auto mb-8 drop-shadow-lg"
          />
          <h1 className="text-5xl font-bold mb-4 text-helios-teal">Welcome to Helios</h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            An interactive platform for reading and analyzing ancient Greek and Latin texts
            with AI-powered insights and morphological analysis.
          </p>
        </div>

        {/* Stats */}
        {stats?.data && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-helios-cream-dark text-center">
              <div className="text-4xl font-bold text-helios-teal mb-2">
                {stats.data.total_texts}
              </div>
              <div className="text-gray-600">Classical Texts</div>
            </div>
            
            <div className="bg-white p-6 rounded-xl shadow-sm border border-helios-cream-dark text-center">
              <div className="text-4xl font-bold text-helios-gold-dark mb-2">
                {Math.round(stats.data.total_segments / 1000)}k+
              </div>
              <div className="text-gray-600">Text Segments</div>
            </div>
            
            <div className="bg-white p-6 rounded-xl shadow-sm border border-helios-cream-dark text-center">
              <div className="text-4xl font-bold text-helios-teal-light mb-2">
                {Object.keys(stats.data.texts_by_language || {}).length}
              </div>
              <div className="text-gray-600">Languages</div>
            </div>
          </div>
        )}

        {/* Features */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
          <div className="bg-white p-8 rounded-xl shadow-sm border border-helios-cream-dark hover:shadow-md transition-shadow">
            <div className="w-12 h-12 bg-helios-gold/20 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-helios-gold-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold mb-3 text-helios-teal">Extensive Library</h3>
            <p className="text-gray-600 mb-4">
              Access texts from the Perseus Digital Library, including works by Homer,
              Plato, Virgil, and many more classical authors.
            </p>
            <Link
              to="/browse"
              className="text-helios-teal hover:text-helios-teal-dark font-medium inline-flex items-center gap-1"
            >
              Browse Texts 
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>

          <div className="bg-white p-8 rounded-xl shadow-sm border border-helios-cream-dark hover:shadow-md transition-shadow">
            <div className="w-12 h-12 bg-helios-teal/10 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-helios-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold mb-3 text-helios-teal">Word Analysis</h3>
            <p className="text-gray-600 mb-4">
              Click any word to see its morphology, definitions, and grammatical form.
              Perfect for students learning Greek and Latin.
            </p>
          </div>

          <div className="bg-white p-8 rounded-xl shadow-sm border border-helios-cream-dark hover:shadow-md transition-shadow">
            <div className="w-12 h-12 bg-helios-gold/20 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-helios-gold-dark" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold mb-3 text-helios-teal">AI-Powered Insights</h3>
            <p className="text-gray-600 mb-4">
              Get translation suggestions from our AI tutor and explore texts with
              intelligent assistance.
            </p>
          </div>

          <div className="bg-white p-8 rounded-xl shadow-sm border border-helios-cream-dark hover:shadow-md transition-shadow">
            <div className="w-12 h-12 bg-helios-teal/10 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-helios-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold mb-3 text-helios-teal">Personal Notes</h3>
            <p className="text-gray-600 mb-4">
              Save notes and translations as you read. Your annotations are
              preserved across sessions.
            </p>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center bg-gradient-to-r from-helios-teal to-helios-teal-dark text-white p-12 rounded-xl shadow-lg">
          <h2 className="text-3xl font-bold mb-4">Ready to Start Reading?</h2>
          <p className="text-xl mb-6 opacity-90">
            Explore the classical world with modern technology
          </p>
          <Link
            to="/browse"
            className="inline-block bg-helios-gold hover:bg-helios-gold-light text-helios-teal-dark px-8 py-3 rounded-lg font-semibold transition-colors shadow-md"
          >
            Browse Texts
          </Link>
        </div>

        {/* Decorative footer laurel */}
        <div className="mt-12 text-center opacity-30">
          <svg className="w-24 h-8 mx-auto text-helios-gold-dark" viewBox="0 0 100 30" fill="currentColor">
            <path d="M50 25c-5-3-10-8-15-15C30 5 25 2 20 2c-3 0-6 1-8 3 5 2 10 8 15 15 5 7 10 10 15 10 3 0 6-2 8-5zM50 25c5-3 10-8 15-15C70 5 75 2 80 2c3 0 6 1 8 3-5 2-10 8-15 15-5 7-10 10-15 10-3 0-6-2-8-5z"/>
          </svg>
        </div>
      </div>
    </div>
  );
}
