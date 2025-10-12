# Helios V1.0 Implementation Plan

**Status:** Approved for Development  
**Date:** October 12, 2025  
**Based on:** PRD v1.5

## Architecture Overview

### Tech Stack

- **Frontend:** React + TypeScript with Vite
- **Backend:** Python FastAPI
- **Database:** PostgreSQL for users/annotations, optimized text storage
- **Authentication:** OAuth2 (Google) with JWT tokens
- **AI Integration:** Aeneas model via existing `predictingthepast` library
- **Morphological Analysis:** Perseus Word Study Tool API or morpheus service

### Key Design Decisions

- Separate frontend and backend for scalability
- Parse and index Perseus XML texts into efficient queryable format
- Cache Aeneas model in memory for <500ms response times
- Use connection pooling for 100+ concurrent users

### System Architecture

```
┌─────────────┐
│   Browser   │
│  (React)    │
└──────┬──────┘
       │ HTTPS/REST
       ▼
┌─────────────────┐
│  FastAPI        │
│  Backend        │
├─────────────────┤
│ • Text API      │
│ • Auth API      │
│ • Word Analysis │
│ • Aeneas AI     │
│ • Annotations   │
└────┬───┬───┬────┘
     │   │   │
     ▼   ▼   ▼
  ┌──┐ ┌──┐ ┌──┐
  │DB│ │AI│ │MA│
  └──┘ └──┘ └──┘
PostgreSQL Aeneas Morpheus
```

## Implementation Phases

### Phase 1: Backend Foundation & Data Pipeline

#### 1.1 Project Structure Setup

**Objective:** Create organized project structure with proper dependency management

**Tasks:**
- Create `backend/` directory with FastAPI application structure
- Create `frontend/` directory with React + Vite + TypeScript
- Set up Python virtual environment
- Configure CORS for local development

**Files to Create:**
```
backend/
├── main.py
├── config.py
├── requirements.txt
├── models/
├── routers/
├── services/
├── parsers/
├── middleware/
├── utils/
└── alembic/

frontend/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── components/
│   ├── pages/
│   ├── contexts/
│   ├── services/
│   └── types/
├── package.json
├── tsconfig.json
└── vite.config.ts
```

**Dependencies:**
```python
# backend/requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
alembic>=1.12.0
psycopg2-binary>=2.9.9
pydantic>=2.4.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.6
authlib>=1.2.1
httpx>=0.25.0
# From predictingthepast_exp
absl-py>=2.2.0
flax>=0.10.4
jax>=0.4.35
jaxlib>=0.4.35
ml-collections>=1.0.0
numpy>=2.2.4
pillow>=10.3.0
tqdm>=4.67.1
lxml>=4.9.3
```

#### 1.2 Perseus Text Parser

**Objective:** Parse all Perseus TEI XML files and create structured database entries

**Key Components:**
- XML parser using lxml for TEI format
- Extract author, title, URN, language metadata
- Parse text structure (books, lines, paragraphs)
- Handle both complete texts and fragments

**Implementation:**

`backend/parsers/perseus_xml_parser.py`:
```python
import lxml.etree as ET
from pathlib import Path
from typing import Dict, List, Optional

class PerseusXMLParser:
    """Parse Perseus TEI XML files"""
    
    TEI_NS = '{http://www.tei-c.org/ns/1.0}'
    
    def parse_file(self, xml_path: Path) -> Dict:
        """Parse a single Perseus XML file"""
        # Extract URN from path or file
        # Parse metadata from teiHeader
        # Extract text content
        # Return structured dict
        
    def extract_metadata(self, root: ET.Element) -> Dict:
        """Extract author, title, editor, etc."""
        
    def extract_text_segments(self, root: ET.Element) -> List[Dict]:
        """Extract all text lines/segments with references"""
        
    def parse_directory(self, data_dir: Path) -> List[Dict]:
        """Parse all XML files in directory tree"""
```

**Database Population Script:**

`backend/scripts/populate_texts.py`:
```python
# Parse all XML files from canonical-greekLit/data/
# Bulk insert into database
# Create indexes for search
```

#### 1.3 Database Schema

**Models:**

`backend/models/user.py`:
```python
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    oauth_provider = Column(String)  # 'google', etc.
    oauth_id = Column(String)
    created_at = Column(DateTime, server_default=func.now())
```

`backend/models/text.py`:
```python
class Text(Base):
    __tablename__ = "texts"
    
    id = Column(Integer, primary_key=True)
    urn = Column(String, unique=True, nullable=False)  # e.g., urn:cts:greekLit:tlg0012.tlg001
    author = Column(String, nullable=False)
    title = Column(String, nullable=False)
    language = Column(String)  # 'grc', 'lat'
    is_fragment = Column(Boolean, default=False)
    metadata = Column(JSON)  # Additional metadata
```

`backend/models/text_segment.py`:
```python
class TextSegment(Base):
    __tablename__ = "text_segments"
    
    id = Column(Integer, primary_key=True)
    text_id = Column(Integer, ForeignKey("texts.id"))
    book = Column(String)
    line = Column(String)
    sequence = Column(Integer)  # For ordering
    content = Column(Text, nullable=False)  # The actual Greek/Latin text
    reference = Column(String)  # e.g., "1.1" for book 1, line 1
```

`backend/models/annotation.py`:
```python
class Annotation(Base):
    __tablename__ = "annotations"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    text_id = Column(Integer, ForeignKey("texts.id"))
    segment_id = Column(Integer, ForeignKey("text_segments.id"))
    word = Column(String)  # The specific word being annotated
    note = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
```

**Migration:**
```bash
alembic init alembic
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

#### 1.4 Text API Endpoints

**Router:**

`backend/routers/texts.py`:
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/texts", tags=["texts"])

@router.get("/")
async def list_texts(
    search: Optional[str] = None,
    language: Optional[str] = None,
    author: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List and search available texts"""
    # Filter by search term, language, author
    # Return paginated results

@router.get("/{urn}")
async def get_text(urn: str, db: Session = Depends(get_db)):
    """Get text metadata and content"""
    # Return full text with all segments

@router.get("/{urn}/segment/{reference}")
async def get_text_segment(
    urn: str, 
    reference: str,
    db: Session = Depends(get_db)
):
    """Get specific book/line reference"""
    # e.g., /api/texts/urn:cts:greekLit:tlg0012.tlg001/segment/1.1
```

### Phase 2: Authentication & User Management

#### 2.1 OAuth Integration

**Configuration:**

`backend/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    class Config:
        env_file = ".env"
```

**Authentication Router:**

`backend/routers/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from authlib.integrations.starlette_client import OAuth

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/login/google")
async def login_google(request: Request):
    """Redirect to Google OAuth"""
    redirect_uri = request.url_for('auth_google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/callback/google")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""
    # Exchange code for token
    # Get user info
    # Create or update user in database
    # Generate JWT token
    # Return JWT to frontend

@router.get("/me")
async def get_current_user(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return current_user

@router.post("/logout")
async def logout():
    """Logout (client-side JWT removal)"""
    return {"message": "Logged out"}
```

**JWT Utilities:**

`backend/utils/security.py`:
```python
from datetime import datetime, timedelta
from jose import JWTError, jwt

def create_access_token(data: dict):
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    """Verify and decode JWT token"""
    # Decode and validate
    # Return user data
```

#### 2.2 Protected Endpoints

**Middleware:**

`backend/middleware/auth.py`:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    # Verify token
    # Get user from database
    # Return user or raise 401
```

### Phase 3: Word Analysis Integration

#### 3.1 Morphological Analysis Service

**Options:**
1. Use Perseus morpheus service (if available)
2. Use CLTK (Classical Language Toolkit) library
3. Use pre-built morphological databases from Perseus

**Implementation:**

`backend/services/morphology.py`:
```python
from typing import Dict, List, Optional

class MorphologyService:
    """Morphological analysis for Greek and Latin words"""
    
    def __init__(self):
        # Initialize morphology database or service connection
        pass
    
    async def analyze_word(
        self, 
        word: str, 
        language: str,
        context: Optional[str] = None
    ) -> Dict:
        """
        Analyze a Greek or Latin word
        
        Returns:
        {
            "word": "ἄειδε",
            "lemma": "ἀείδω",
            "pos": "verb",
            "morphology": {
                "person": "2nd/3rd",
                "number": "singular",
                "tense": "imperfect",
                "mood": "indicative",
                "voice": "active"
            },
            "definitions": [
                "to sing",
                "to celebrate in song"
            ],
            "lexicon_url": "https://logeion.uchicago.edu/ἀείδω"
        }
        """
        
    def get_lexicon_url(self, lemma: str, language: str) -> str:
        """Generate lexicon URL for lemma"""
        if language == 'grc':
            return f"https://logeion.uchicago.edu/{lemma}"
        elif language == 'lat':
            return f"https://logeion.uchicago.edu/{lemma}"
```

**API Endpoint:**

`backend/routers/analysis.py`:
```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/analyze", tags=["analysis"])

@router.post("/word")
async def analyze_word(
    word: str,
    language: str,
    context: Optional[str] = None,
    morphology_service: MorphologyService = Depends()
):
    """Analyze a Greek or Latin word"""
    result = await morphology_service.analyze_word(word, language, context)
    return result
```

### Phase 4: Aeneas AI Model Integration

#### 4.1 Model Setup

**Service:**

`backend/services/aeneas_service.py`:
```python
import pickle
import jax
from pathlib import Path
from predictingthepast.eval import inference
from predictingthepast.models.model import Model
from predictingthepast.util import alphabet as util_alphabet

class AeneasService:
    """Aeneas AI model service for text restoration and attribution"""
    
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.models = {}
        self._load_models()
    
    def _load_models(self):
        """Load Greek and Latin models into memory"""
        # Load Greek model
        if (self.model_dir / "ithaca_153143996_2.pkl").exists():
            self.models['greek'] = self._load_checkpoint(
                self.model_dir / "ithaca_153143996_2.pkl",
                self.model_dir / "iphi.json",
                self.model_dir / "iphi_emb_xid153143996.pkl",
                'greek'
            )
        
        # Load Latin model
        if (self.model_dir / "aeneas_117149994_2.pkl").exists():
            self.models['latin'] = self._load_checkpoint(
                self.model_dir / "aeneas_117149994_2.pkl",
                self.model_dir / "led.json",
                self.model_dir / "led_emb_xid117149994.pkl",
                'latin'
            )
    
    def _load_checkpoint(self, checkpoint_path, dataset_path, retrieval_path, language):
        """Load a model checkpoint"""
        with open(checkpoint_path, 'rb') as f:
            checkpoint = pickle.load(f)
        
        params = jax.device_put(checkpoint['params'])
        model = Model(**checkpoint['model_config'])
        
        alphabet = (util_alphabet.LatinAlphabet() if language == 'latin' 
                   else util_alphabet.GreekAlphabet())
        
        dataset = inference.load_dataset(dataset_path)
        retrieval = inference.load_retrieval(retrieval_path)
        
        return {
            'model': model,
            'params': params,
            'alphabet': alphabet,
            'region_map': checkpoint['region_map'],
            'vocab_char_size': checkpoint['model_config']['vocab_char_size'],
            'dataset': dataset,
            'retrieval': retrieval
        }
    
    async def restore_text(self, text: str, language: str) -> Dict:
        """
        Restore damaged text (marked with # for missing chars)
        
        Input: "μῆνιν ἄ#ιδε θεὰ"
        Output: Multiple restoration options with probabilities
        """
        if language not in self.models:
            raise ValueError(f"Model not loaded for language: {language}")
        
        model_data = self.models[language]
        
        restoration = inference.restore(
            text,
            forward=model_data['model'].apply,
            params=model_data['params'],
            alphabet=model_data['alphabet'],
            vocab_char_size=model_data['vocab_char_size'],
            beam_width=100,
            temperature=1.0,
            unk_restoration_max_len=15
        )
        
        return restoration.build_json()
    
    async def attribute_text(self, text: str, language: str) -> Dict:
        """
        Predict geographical origin and date of text
        """
        if language not in self.models:
            raise ValueError(f"Model not loaded for language: {language}")
        
        model_data = self.models[language]
        
        attribution = inference.attribute(
            text,
            forward=model_data['model'].apply,
            params=model_data['params'],
            alphabet=model_data['alphabet'],
            vocab_char_size=model_data['vocab_char_size']
        )
        
        return attribution.build_json()
    
    async def contextualize_text(self, text: str, language: str) -> Dict:
        """
        Find similar inscriptions and contextual parallels
        """
        if language not in self.models:
            raise ValueError(f"Model not loaded for language: {language}")
        
        model_data = self.models[language]
        
        contextualization = inference.contextualize(
            text,
            model_data['dataset'],
            model_data['retrieval'],
            model_data['model'].apply,
            model_data['params'],
            model_data['alphabet'],
            model_data['region_map']
        )
        
        return contextualization.build_json()

# Global instance
aeneas_service: Optional[AeneasService] = None

def get_aeneas_service() -> AeneasService:
    """Dependency for FastAPI"""
    if aeneas_service is None:
        raise RuntimeError("Aeneas service not initialized")
    return aeneas_service
```

**Startup Configuration:**

`backend/main.py`:
```python
from fastapi import FastAPI
from pathlib import Path

app = FastAPI(title="Helios API")

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global aeneas_service
    
    # Load Aeneas models
    model_dir = Path("./models")
    aeneas_service = AeneasService(model_dir)
    print("Aeneas models loaded successfully")
```

#### 4.2 AI Endpoints

`backend/routers/aeneas.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/aeneas", tags=["aeneas"])

class RestoreRequest(BaseModel):
    text: str
    language: str  # 'greek' or 'latin'

class AttributeRequest(BaseModel):
    text: str
    language: str

@router.post("/restore")
async def restore_text(
    request: RestoreRequest,
    service: AeneasService = Depends(get_aeneas_service)
):
    """
    Restore damaged text. Use # to mark missing characters.
    
    Example: "μῆνιν ἄ#ιδε θεὰ"
    """
    if len(request.text) < 50 or len(request.text) > 750:
        raise HTTPException(400, "Text must be between 50 and 750 characters")
    
    result = await service.restore_text(request.text, request.language)
    return result

@router.post("/attribute")
async def attribute_text(
    request: AttributeRequest,
    service: AeneasService = Depends(get_aeneas_service)
):
    """
    Predict geographical origin and date of text
    """
    result = await service.attribute_text(request.text, request.language)
    return result

@router.post("/contextualize")
async def contextualize_text(
    request: AttributeRequest,
    service: AeneasService = Depends(get_aeneas_service)
):
    """
    Find similar inscriptions and contextual parallels
    """
    result = await service.contextualize_text(request.text, request.language)
    return result
```

### Phase 5: Annotations System

#### 5.1 Annotation CRUD API

`backend/routers/annotations.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

router = APIRouter(prefix="/api/annotations", tags=["annotations"])

class AnnotationCreate(BaseModel):
    text_id: int
    segment_id: int
    word: str
    note: str

class AnnotationUpdate(BaseModel):
    note: str

@router.post("/")
async def create_annotation(
    annotation: AnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new annotation"""
    db_annotation = Annotation(
        user_id=current_user.id,
        **annotation.dict()
    )
    db.add(db_annotation)
    db.commit()
    db.refresh(db_annotation)
    return db_annotation

@router.get("/")
async def get_annotations(
    text_id: Optional[int] = None,
    segment_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's annotations with optional filters"""
    query = db.query(Annotation).filter(Annotation.user_id == current_user.id)
    
    if text_id:
        query = query.filter(Annotation.text_id == text_id)
    if segment_id:
        query = query.filter(Annotation.segment_id == segment_id)
    
    return query.all()

@router.put("/{annotation_id}")
async def update_annotation(
    annotation_id: int,
    annotation: AnnotationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an annotation"""
    db_annotation = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()
    
    if not db_annotation:
        raise HTTPException(404, "Annotation not found")
    
    db_annotation.note = annotation.note
    db.commit()
    return db_annotation

@router.delete("/{annotation_id}")
async def delete_annotation(
    annotation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an annotation"""
    db_annotation = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()
    
    if not db_annotation:
        raise HTTPException(404, "Annotation not found")
    
    db.delete(db_annotation)
    db.commit()
    return {"message": "Annotation deleted"}
```

### Phase 6: Frontend Development

#### 6.1 Core UI Components

**Setup:**

`frontend/package.json`:
```json
{
  "name": "helios-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.18.0",
    "axios": "^1.6.0",
    "@tanstack/react-query": "^5.8.0",
    "zustand": "^4.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.1.0",
    "typescript": "^5.2.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

**API Service:**

`frontend/src/services/api.ts`:
```typescript
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface Text {
  id: number;
  urn: string;
  author: string;
  title: string;
  language: string;
  is_fragment: boolean;
}

export interface TextSegment {
  id: number;
  book: string;
  line: string;
  content: string;
  reference: string;
}

export interface WordAnalysis {
  word: string;
  lemma: string;
  pos: string;
  morphology: Record<string, string>;
  definitions: string[];
  lexicon_url: string;
}

export const textApi = {
  list: (params?: { search?: string; language?: string; author?: string }) =>
    api.get<Text[]>('/api/texts', { params }),
  
  get: (urn: string) =>
    api.get<{ text: Text; segments: TextSegment[] }>(`/api/texts/${urn}`),
  
  getSegment: (urn: string, reference: string) =>
    api.get<TextSegment>(`/api/texts/${urn}/segment/${reference}`),
};

export const analysisApi = {
  analyzeWord: (word: string, language: string, context?: string) =>
    api.post<WordAnalysis>('/api/analyze/word', { word, language, context }),
};

export const aeneasApi = {
  restore: (text: string, language: string) =>
    api.post('/api/aeneas/restore', { text, language }),
  
  attribute: (text: string, language: string) =>
    api.post('/api/aeneas/attribute', { text, language }),
  
  contextualize: (text: string, language: string) =>
    api.post('/api/aeneas/contextualize', { text, language }),
};

export const annotationApi = {
  create: (data: { text_id: number; segment_id: number; word: string; note: string }) =>
    api.post('/api/annotations', data),
  
  list: (params?: { text_id?: number; segment_id?: number }) =>
    api.get('/api/annotations', { params }),
  
  update: (id: number, note: string) =>
    api.put(`/api/annotations/${id}`, { note }),
  
  delete: (id: number) =>
    api.delete(`/api/annotations/${id}`),
};

export const authApi = {
  loginGoogle: () => window.location.href = `${API_BASE_URL}/api/auth/login/google`,
  
  me: () => api.get('/api/auth/me'),
  
  logout: () => {
    localStorage.removeItem('auth_token');
    return api.post('/api/auth/logout');
  },
};

export default api;
```

**Text Browser Component:**

`frontend/src/components/TextBrowser.tsx`:
```typescript
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { textApi, type Text } from '../services/api';

export function TextBrowser() {
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState<string>('');
  
  const { data: texts, isLoading } = useQuery({
    queryKey: ['texts', search, language],
    queryFn: () => textApi.list({ search, language }),
  });
  
  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-6">Browse Texts</h1>
      
      <div className="mb-6 flex gap-4">
        <input
          type="text"
          placeholder="Search by author or title..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 px-4 py-2 border rounded-lg"
        />
        
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="px-4 py-2 border rounded-lg"
        >
          <option value="">All Languages</option>
          <option value="grc">Greek</option>
          <option value="lat">Latin</option>
        </select>
      </div>
      
      {isLoading ? (
        <div>Loading...</div>
      ) : (
        <div className="grid gap-4">
          {texts?.data.map((text: Text) => (
            <a
              key={text.id}
              href={`/text/${text.urn}`}
              className="p-4 border rounded-lg hover:bg-gray-50 transition"
            >
              <div className="flex items-center gap-2">
                <h3 className="text-xl font-semibold">{text.title}</h3>
                {text.is_fragment && (
                  <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                    Fragment
                  </span>
                )}
              </div>
              <p className="text-gray-600">{text.author}</p>
              <p className="text-sm text-gray-500">{text.urn}</p>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Text Reader Component:**

`frontend/src/components/TextReader.tsx`:
```typescript
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { textApi, type TextSegment } from '../services/api';
import { WordAnalysisPanel } from './WordAnalysisPanel';

export function TextReader() {
  const { urn } = useParams<{ urn: string }>();
  const [selectedWord, setSelectedWord] = useState<{
    word: string;
    language: string;
    segmentId: number;
  } | null>(null);
  
  const { data, isLoading } = useQuery({
    queryKey: ['text', urn],
    queryFn: () => textApi.get(urn!),
    enabled: !!urn,
  });
  
  const handleWordClick = (word: string, segmentId: number) => {
    const language = data?.data.text.language || 'grc';
    setSelectedWord({ word, language, segmentId });
  };
  
  if (isLoading) return <div>Loading text...</div>;
  if (!data) return <div>Text not found</div>;
  
  const { text, segments } = data.data;
  
  return (
    <div className="flex h-screen">
      {/* Main text area */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-4xl font-bold mb-2">{text.title}</h1>
            <h2 className="text-2xl text-gray-600 mb-4">{text.author}</h2>
            {text.is_fragment && (
              <div className="flex items-center gap-2 text-yellow-700 bg-yellow-50 p-3 rounded-lg">
                <span className="text-xl">⚠️</span>
                <span>This is a fragmentary text</span>
              </div>
            )}
          </div>
          
          <div className="space-y-4">
            {segments.map((segment: TextSegment) => (
              <div key={segment.id} className="flex gap-4">
                <div className="text-gray-400 w-16 text-right text-sm">
                  {segment.reference}
                </div>
                <div
                  className="flex-1 text-lg leading-relaxed greek-text"
                  style={{ fontFamily: 'GFS Didot, Georgia, serif' }}
                >
                  {segment.content.split(/\s+/).map((word, idx) => (
                    <span
                      key={idx}
                      onClick={() => handleWordClick(word, segment.id)}
                      className="cursor-pointer hover:bg-blue-100 transition px-1 rounded"
                    >
                      {word}{' '}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      
      {/* Side panel */}
      {selectedWord && (
        <WordAnalysisPanel
          word={selectedWord.word}
          language={selectedWord.language}
          segmentId={selectedWord.segmentId}
          textId={text.id}
          onClose={() => setSelectedWord(null)}
        />
      )}
    </div>
  );
}
```

#### 6.2 Interactive Word Panel

`frontend/src/components/WordAnalysisPanel.tsx`:
```typescript
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { analysisApi, annotationApi, type WordAnalysis } from '../services/api';

interface Props {
  word: string;
  language: string;
  segmentId: number;
  textId: number;
  onClose: () => void;
}

export function WordAnalysisPanel({ word, language, segmentId, textId, onClose }: Props) {
  const [note, setNote] = useState('');
  const queryClient = useQueryClient();
  
  const { data: analysis, isLoading } = useQuery({
    queryKey: ['word-analysis', word, language],
    queryFn: () => analysisApi.analyzeWord(word, language),
  });
  
  const { data: annotations } = useQuery({
    queryKey: ['annotations', textId, segmentId],
    queryFn: () => annotationApi.list({ text_id: textId, segment_id: segmentId }),
  });
  
  const createAnnotation = useMutation({
    mutationFn: (note: string) =>
      annotationApi.create({ text_id: textId, segment_id: segmentId, word, note }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['annotations'] });
      setNote('');
    },
  });
  
  if (isLoading) {
    return (
      <div className="w-96 border-l bg-white p-6">
        <div>Loading analysis...</div>
      </div>
    );
  }
  
  const wordData = analysis?.data;
  
  return (
    <div className="w-96 border-l bg-white p-6 overflow-y-auto">
      <div className="flex justify-between items-start mb-6">
        <h2 className="text-2xl font-bold greek-text">{word}</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
          ✕
        </button>
      </div>
      
      {wordData && (
        <div className="space-y-6">
          {/* Lemma */}
          <div>
            <h3 className="text-sm font-semibold text-gray-500 mb-1">LEMMA</h3>
            <p className="text-xl greek-text">{wordData.lemma}</p>
          </div>
          
          {/* Part of Speech */}
          <div>
            <h3 className="text-sm font-semibold text-gray-500 mb-1">PART OF SPEECH</h3>
            <p className="text-lg">{wordData.pos}</p>
          </div>
          
          {/* Morphology */}
          <div>
            <h3 className="text-sm font-semibold text-gray-500 mb-2">MORPHOLOGY</h3>
            <div className="space-y-1">
              {Object.entries(wordData.morphology).map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span className="text-gray-600 capitalize">{key}:</span>
                  <span className="font-medium">{value}</span>
                </div>
              ))}
            </div>
          </div>
          
          {/* Definitions */}
          <div>
            <h3 className="text-sm font-semibold text-gray-500 mb-2">DEFINITIONS</h3>
            <ul className="space-y-2">
              {wordData.definitions.map((def, idx) => (
                <li key={idx} className="text-gray-700">
                  {idx + 1}. {def}
                </li>
              ))}
            </ul>
          </div>
          
          {/* Lexicon Link */}
          <div>
            <a
              href={wordData.lexicon_url}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full py-2 px-4 bg-blue-600 text-white text-center rounded-lg hover:bg-blue-700 transition"
            >
              View Full Lexicon Entry →
            </a>
          </div>
          
          {/* Annotations */}
          <div>
            <h3 className="text-sm font-semibold text-gray-500 mb-2">YOUR NOTES</h3>
            
            {/* Existing annotations */}
            <div className="space-y-2 mb-3">
              {annotations?.data
                .filter(a => a.word === word)
                .map(annotation => (
                  <div key={annotation.id} className="p-3 bg-gray-50 rounded">
                    <p className="text-sm">{annotation.note}</p>
                  </div>
                ))}
            </div>
            
            {/* Add new annotation */}
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add a personal note..."
              className="w-full px-3 py-2 border rounded-lg resize-none"
              rows={3}
            />
            <button
              onClick={() => createAnnotation.mutate(note)}
              disabled={!note.trim()}
              className="mt-2 w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 transition"
            >
              Save Note
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

#### 6.3 Aeneas Integration UI

`frontend/src/components/AeneasPanel.tsx`:
```typescript
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { aeneasApi } from '../services/api';

interface Props {
  text: string;
  language: string;
}

export function AeneasPanel({ text, language }: Props) {
  const [activeTab, setActiveTab] = useState<'restore' | 'attribute' | 'context'>('restore');
  
  const { data: restoration } = useQuery({
    queryKey: ['aeneas-restore', text, language],
    queryFn: () => aeneasApi.restore(text, language),
    enabled: activeTab === 'restore',
  });
  
  const { data: attribution } = useQuery({
    queryKey: ['aeneas-attribute', text, language],
    queryFn: () => aeneasApi.attribute(text, language),
    enabled: activeTab === 'attribute',
  });
  
  const { data: contextualization } = useQuery({
    queryKey: ['aeneas-context', text, language],
    queryFn: () => aeneasApi.contextualize(text, language),
    enabled: activeTab === 'context',
  });
  
  return (
    <div className="border-t mt-6 pt-6">
      <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
        <span>🤖</span>
        <span>AI Analysis (Aeneas)</span>
      </h3>
      
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveTab('restore')}
          className={`px-4 py-2 rounded ${
            activeTab === 'restore' ? 'bg-blue-600 text-white' : 'bg-gray-200'
          }`}
        >
          Restoration
        </button>
        <button
          onClick={() => setActiveTab('attribute')}
          className={`px-4 py-2 rounded ${
            activeTab === 'attribute' ? 'bg-blue-600 text-white' : 'bg-gray-200'
          }`}
        >
          Attribution
        </button>
        <button
          onClick={() => setActiveTab('context')}
          className={`px-4 py-2 rounded ${
            activeTab === 'context' ? 'bg-blue-600 text-white' : 'bg-gray-200'
          }`}
        >
          Context
        </button>
      </div>
      
      {activeTab === 'restore' && restoration && (
        <div>
          <h4 className="font-semibold mb-2">Text Restoration Suggestions:</h4>
          {/* Display restoration results */}
          <pre className="text-sm bg-gray-50 p-3 rounded overflow-auto">
            {JSON.stringify(restoration.data, null, 2)}
          </pre>
        </div>
      )}
      
      {activeTab === 'attribute' && attribution && (
        <div>
          <h4 className="font-semibold mb-2">Geographical & Date Attribution:</h4>
          {/* Display attribution results */}
          <pre className="text-sm bg-gray-50 p-3 rounded overflow-auto">
            {JSON.stringify(attribution.data, null, 2)}
          </pre>
        </div>
      )}
      
      {activeTab === 'context' && contextualization && (
        <div>
          <h4 className="font-semibold mb-2">Similar Inscriptions:</h4>
          {/* Display similar inscriptions */}
          <pre className="text-sm bg-gray-50 p-3 rounded overflow-auto">
            {JSON.stringify(contextualization.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
```

#### 6.4 Authentication Flow

`frontend/src/contexts/AuthContext.tsx`:
```typescript
import { createContext, useContext, useEffect, useState } from 'react';
import { authApi } from '../services/api';

interface User {
  id: number;
  email: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  useEffect(() => {
    // Check for auth token in URL (after OAuth redirect)
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    
    if (token) {
      localStorage.setItem('auth_token', token);
      window.history.replaceState({}, '', window.location.pathname);
    }
    
    // Load user if token exists
    const loadUser = async () => {
      try {
        const response = await authApi.me();
        setUser(response.data);
      } catch (error) {
        localStorage.removeItem('auth_token');
      } finally {
        setIsLoading(false);
      }
    };
    
    if (localStorage.getItem('auth_token')) {
      loadUser();
    } else {
      setIsLoading(false);
    }
  }, []);
  
  const login = () => {
    authApi.loginGoogle();
  };
  
  const logout = async () => {
    await authApi.logout();
    setUser(null);
  };
  
  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
```

`frontend/src/pages/Login.tsx`:
```typescript
import { useAuth } from '../contexts/AuthContext';
import { Navigate } from 'react-router-dom';

export function Login() {
  const { user, login } = useAuth();
  
  if (user) {
    return <Navigate to="/" />;
  }
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="bg-white p-8 rounded-2xl shadow-xl max-w-md w-full">
        <h1 className="text-4xl font-bold text-center mb-2">Helios</h1>
        <p className="text-gray-600 text-center mb-8">
          Your digital companion for classical languages
        </p>
        
        <button
          onClick={login}
          className="w-full flex items-center justify-center gap-3 bg-white border-2 border-gray-300 rounded-lg py-3 px-4 hover:bg-gray-50 transition"
        >
          <img 
            src="https://www.google.com/favicon.ico" 
            alt="Google"
            className="w-5 h-5"
          />
          <span className="font-medium">Continue with Google</span>
        </button>
      </div>
    </div>
  );
}
```

### Phase 7: Integration & Testing

#### 7.1 End-to-End Integration

**Test Scenarios:**
1. User authentication flow
2. Browse and load Homer's Iliad
3. Click word "μῆνιν" and verify analysis appears in <500ms
4. Create annotation and verify persistence
5. Load fragmentary text and test Aeneas restoration
6. Test with 100 concurrent users (load testing)

**Performance Monitoring:**

`backend/middleware/performance.py`:
```python
import time
from fastapi import Request
import logging

logger = logging.getLogger(__name__)

async def performance_middleware(request: Request, call_next):
    """Log request performance"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} "
        f"completed in {duration:.3f}s"
    )
    
    # Alert if response time > 500ms
    if duration > 0.5:
        logger.warning(f"Slow request: {request.url.path} took {duration:.3f}s")
    
    response.headers["X-Response-Time"] = str(duration)
    return response
```

#### 7.2 Database Optimization

**Indexes:**
```python
# In model definitions
class TextSegment(Base):
    __tablename__ = "text_segments"
    
    # ... columns ...
    
    __table_args__ = (
        Index('idx_text_id', 'text_id'),
        Index('idx_text_reference', 'text_id', 'reference'),
    )

class Annotation(Base):
    __tablename__ = "annotations"
    
    # ... columns ...
    
    __table_args__ = (
        Index('idx_user_text', 'user_id', 'text_id'),
        Index('idx_user_segment', 'user_id', 'segment_id'),
    )
```

**Connection Pooling:**

`backend/database.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,  # Number of connections to keep open
    max_overflow=40,  # Additional connections under load
    pool_timeout=30,
    pool_recycle=3600,  # Recycle connections after 1 hour
)
```

### Phase 8: Deployment

#### 8.1 Docker Configuration

`Dockerfile` (backend):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Download Aeneas models (Greek only for initial launch)
RUN mkdir -p models && \
    curl -o models/ithaca_153143996_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/ithaca_153143996_2.pkl && \
    curl -o models/iphi.json \
    https://storage.googleapis.com/ithaca-resources/models/iphi.json && \
    curl -o models/iphi_emb_xid153143996.pkl \
    https://storage.googleapis.com/ithaca-resources/models/iphi_emb_xid153143996.pkl

# Run database migrations and start server
CMD alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000
```

`docker-compose.yml`:
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: helios
      POSTGRES_USER: helios
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://helios:${DB_PASSWORD}@postgres:5432/helios
      SECRET_KEY: ${SECRET_KEY}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      GOOGLE_REDIRECT_URI: ${GOOGLE_REDIRECT_URI}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    volumes:
      - ./canonical-greekLit:/app/canonical-greekLit:ro
  
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    environment:
      VITE_API_URL: ${API_URL}

volumes:
  postgres_data:
```

#### 8.2 Environment Configuration

`.env.example`:
```bash
# Database
DATABASE_URL=postgresql://helios:password@localhost:5432/helios

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback/google

# Frontend
VITE_API_URL=http://localhost:8000
```

#### 8.3 Deployment Checklist

- [ ] Set up PostgreSQL database on hosting service
- [ ] Configure OAuth callback URLs in Google Cloud Console
- [ ] Set environment variables in production
- [ ] Deploy backend to cloud service (Railway, Render, Fly.io)
- [ ] Build and deploy frontend to Vercel/Netlify
- [ ] Run initial database migration
- [ ] Populate database with Perseus texts
- [ ] Download and configure Aeneas models
- [ ] Test authentication flow end-to-end
- [ ] Load test with 100 concurrent users
- [ ] Set up monitoring and error tracking
- [ ] Create user documentation

## Success Metrics

### Performance Targets
- ✓ Word analysis: < 500ms
- ✓ Text loading: < 3 seconds
- ✓ Concurrent users: 100+
- ✓ Uptime: 99.5%

### Functional Completeness
- ✓ User authentication (Google OAuth)
- ✓ Text browsing and search
- ✓ Text display with proper Greek rendering
- ✓ Word-by-word analysis
- ✓ Morphological information
- ✓ Lexicon links
- ✓ Aeneas text restoration
- ✓ Aeneas attribution (geography, date)
- ✓ User annotations
- ✓ Fragment indicators

### User Experience
- ✓ Intuitive UI (no manual needed)
- ✓ Responsive design
- ✓ Cross-browser compatibility
- ✓ Beautiful Greek typography

## Risk Mitigation

### Technical Risks

1. **Aeneas model performance**
   - **Risk:** Model inference too slow (>500ms)
   - **Mitigation:** 
     - Keep model in memory (no reload per request)
     - Implement model quantization (INT8) if needed
     - Cache frequent requests
     - Use GPU acceleration if available

2. **Database performance**
   - **Risk:** Slow queries under load
   - **Mitigation:**
     - Proper indexing on frequently queried columns
     - Connection pooling (20 base + 40 overflow)
     - Cache text segments in Redis if needed
     - Pagination for large result sets

3. **XML parsing overhead**
   - **Risk:** Parsing 2500+ files takes too long
   - **Mitigation:**
     - Parse once during deployment/setup
     - Store in database, not on-demand parsing
     - Create background job for updates

4. **Morphological analysis availability**
   - **Risk:** External service unavailable
   - **Mitigation:**
     - Download and host morphological databases locally
     - Use CLTK library as fallback
     - Graceful degradation (show lemma only)

### Product Risks

1. **User adoption**
   - **Risk:** Students don't use the tool
   - **Mitigation:**
     - Partner with classics department for pilot
     - Gather feedback early and iterate
     - Ensure <500ms word lookup (faster than manual)

2. **Data accuracy**
   - **Risk:** Incorrect morphological analysis
   - **Mitigation:**
     - Use established Perseus data
     - Show confidence scores where available
     - Allow user feedback on errors

## Timeline Estimate

**Total: 8-10 weeks for full implementation**

- Week 1-2: Backend foundation, database, Perseus parser
- Week 3: Authentication, text API
- Week 4: Morphological analysis integration
- Week 5-6: Aeneas model integration and optimization
- Week 7: Frontend development
- Week 8: Integration, testing, optimization
- Week 9: Deployment and documentation
- Week 10: Buffer for issues and pilot launch

## Next Steps

1. Initialize project structure
2. Set up development environment
3. Begin Phase 1: Backend foundation
4. Download Aeneas model files
5. Parse first test text (Homer's Iliad)
6. Implement text API
7. Continue through phases systematically

---

**Document Version:** 1.0  
**Last Updated:** October 12, 2025  
**Maintainer:** Development Team

