# Helios Frontend

React + TypeScript frontend for the Helios classical texts application.

## Features

- 📚 Browse and search classical Greek and Latin texts
- 📖 Interactive text reader with word-by-word analysis
- 🔍 Morphological analysis with lexicon links
- 📝 Personal annotations and notes
- 🔐 Google OAuth authentication
- 🎨 Modern, responsive UI with Tailwind CSS

## Setup

### Prerequisites

- Node.js 18+ and npm
- Backend API running on `http://localhost:8000`

### Installation

```bash
# Install dependencies
npm install
```

### Configuration

Create a `.env` file (optional):

```
VITE_API_URL=http://localhost:8000
```

### Development

```bash
# Start development server
npm run dev
```

The app will be available at `http://localhost:3000`

### Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/       # Reusable UI components
│   │   ├── Layout.tsx
│   │   └── WordAnalysisPanel.tsx
│   ├── pages/            # Page components
│   │   ├── Home.tsx
│   │   ├── Login.tsx
│   │   ├── TextBrowser.tsx
│   │   └── TextReader.tsx
│   ├── contexts/         # React contexts
│   │   └── AuthContext.tsx
│   ├── services/         # API services
│   │   └── api.ts
│   ├── types/            # TypeScript types
│   │   └── index.ts
│   ├── App.tsx           # Main app component
│   ├── main.tsx          # Entry point
│   └── index.css         # Global styles
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## Key Technologies

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **React Router** - Routing
- **TanStack Query** - Data fetching and caching
- **Axios** - HTTP client
- **Tailwind CSS** - Styling

## Features

### Authentication

Users authenticate via Google OAuth. The backend handles the OAuth flow and returns a JWT token, which is stored in localStorage.

### Text Reader

- Click any word to see morphological analysis
- Analysis appears in a side panel
- Links to external lexicons (Logeion, Perseus)
- Personal annotations saved per user

### Word Analysis

Real-time morphological analysis including:
- Lemma (dictionary form)
- Part of speech
- Detailed morphology (person, number, tense, etc.)
- Multiple definitions
- External lexicon links

### Annotations

- Create personal notes for any word
- Notes persist across sessions
- Delete annotations when no longer needed

## Deployment

### Vercel (Recommended)

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel
```

### Netlify

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Build
npm run build

# Deploy
netlify deploy --prod --dir=dist
```

### Docker

```dockerfile
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## Environment Variables

- `VITE_API_URL` - Backend API URL (default: `http://localhost:8000`)

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

Older browsers may not support all features.

## Development Tips

### Hot Reload

Vite provides instant hot module replacement (HMR). Changes to components will reflect immediately without losing state.

### TypeScript

All components are fully typed. The TypeScript compiler will catch type errors during development.

### API Mocking

For development without the backend, consider using MSW (Mock Service Worker) or similar tools.

## Troubleshooting

### CORS Errors

If you see CORS errors, ensure the backend has the frontend URL in its `CORS_ORIGINS` configuration.

### Authentication Loop

If redirected back to login repeatedly, check:
1. JWT token in localStorage
2. Backend `/api/auth/me` endpoint is working
3. Token hasn't expired

### Greek Characters Not Displaying

Ensure the GFS Didot font is loading correctly. Check browser console for font loading errors.

## License

See parent directory for license information.

