import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi } from '../services/api';

export default function Home() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: () => textApi.getStats(),
  });

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="text-center mb-12">
            <h1 className="text-5xl font-bold mb-4">Welcome to Helios</h1>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            An interactive platform for reading and analyzing ancient Greek and Latin texts
            with AI-powered insights and morphological analysis.
            </p>
        </div>

        {/* Stats */}
        {stats?.data && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <div className="bg-white p-6 rounded-lg shadow-sm border text-center">
                <div className="text-4xl font-bold text-blue-600 mb-2">
                {stats.data.total_texts}
                </div>
                <div className="text-gray-600">Classical Texts</div>
            </div>
            
            <div className="bg-white p-6 rounded-lg shadow-sm border text-center">
                <div className="text-4xl font-bold text-green-600 mb-2">
                {Math.round(stats.data.total_segments / 1000)}k+
                </div>
                <div className="text-gray-600">Text Segments</div>
            </div>
            
            <div className="bg-white p-6 rounded-lg shadow-sm border text-center">
                <div className="text-4xl font-bold text-purple-600 mb-2">
                {Object.keys(stats.data.texts_by_language || {}).length}
                </div>
                <div className="text-gray-600">Languages</div>
            </div>
            </div>
        )}

        {/* Features */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
            <div className="bg-white p-8 rounded-lg shadow-sm border">
            <div className="text-3xl mb-4">📚</div>
            <h3 className="text-xl font-semibold mb-3">Extensive Library</h3>
            <p className="text-gray-600 mb-4">
                Access texts from the Perseus Digital Library, including works by Homer,
                Plato, Virgil, and many more classical authors.
            </p>
            <Link
                to="/browse"
                className="text-blue-600 hover:text-blue-700 font-medium"
            >
                Browse Texts →
            </Link>
            </div>

            <div className="bg-white p-8 rounded-lg shadow-sm border">
            <div className="text-3xl mb-4">🔍</div>
            <h3 className="text-xl font-semibold mb-3">Word Analysis</h3>
            <p className="text-gray-600 mb-4">
                Click any word to see its morphology, definitions, and lexicon entries.
                Perfect for students learning Greek and Latin.
            </p>
            </div>

            <div className="bg-white p-8 rounded-lg shadow-sm border">
            <div className="text-3xl mb-4">🤖</div>
            <h3 className="text-xl font-semibold mb-3">AI-Powered Restoration</h3>
            <p className="text-gray-600 mb-4">
                Use Google DeepMind's Aeneas model to restore damaged inscriptions
                and predict their geographical origin and date.
            </p>
            </div>

            <div className="bg-white p-8 rounded-lg shadow-sm border">
            <div className="text-3xl mb-4">📝</div>
            <h3 className="text-xl font-semibold mb-3">Personal Annotations</h3>
            <p className="text-gray-600 mb-4">
                Save notes and translations as you read. Your annotations are
                preserved across sessions.
            </p>
            </div>
        </div>

        {/* CTA */}
        <div className="text-center bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-12 rounded-lg">
            <h2 className="text-3xl font-bold mb-4">Ready to Start Reading?</h2>
            <p className="text-xl mb-6 opacity-90">
            Explore the classical world with modern technology
            </p>
            <Link
            to="/browse"
            className="inline-block bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-gray-100 transition"
            >
            Browse Texts
            </Link>
        </div>
        </div>
    </div>
  );
}
