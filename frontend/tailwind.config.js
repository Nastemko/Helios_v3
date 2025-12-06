/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'greek': ['"GFS Didot"', 'Georgia', 'serif'],
      },
      colors: {
        // Helios brand colors from logo
        'helios': {
          gold: '#C9A962',
          'gold-light': '#D4BC7D',
          'gold-dark': '#A88B4A',
          teal: '#1E5F74',
          'teal-light': '#2A7A94',
          'teal-dark': '#164858',
          cream: '#F8F5EE',
          'cream-dark': '#EDE8DC',
        },
      },
    },
  },
  plugins: [],
}

