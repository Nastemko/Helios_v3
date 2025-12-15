<!-- a12a8f67-c90c-4588-a84b-8cc13546bf01 f2280305-688f-4f3b-a9ec-63875e82a560 -->
# Helios V2.0 - Feature Branch Strategy

This plan outlines the development across 5 distinct feature branches.

## 🌿 Branch 1: Cleanup (`feat/remove-lexical-routes`)

**Goal:** Remove static lexical routes and external linking dependencies.

- [ ] Remove `get_lexicon_url` from backend routers/services.
- [ ] Clean up `WordAnalysisPanel` in frontend to remove "View in Logeion" links.
- [ ] Verify `WordAnalysisResponse` schema updates.

## 🌿 Branch 2: Study Tools (`feat/study-tools`)

**Goal:** Implement Notepad and Highlighting features (Full Stack).

- [ ] **Backend:**
- Add `StudentNote` and `Highlight` models & migrations.
- Create `routers/study.py` endpoints.
- [ ] **Frontend:**
- Add `Notepad` component.
- Add `HighlightableText` component for segment selection.
- Integrate API calls.

## 🌿 Branch 3: Tutor Infrastructure (`feat/tutor-integration`)

**Goal:** Setup LLM service foundation.

- [ ] Create `LLMProvider` interface.
- [ ] Implement `GroqProvider` and `MockProvider`.
- [ ] Add environment configuration for API keys.
- [ ] Create basic connectivity test endpoint.

## 🌿 Branch 4: Translation Suggestions (`feat/translation-suggestions`)

**Goal:** Implement the "Ask Tutor" suggestion flow.

- [ ] **Backend:** Create `suggest_translation` endpoint with context-aware prompt.
- [ ] **Frontend:** Add "Ask Tutor" button to Highlight popover.
- [ ] Display AI suggestions in the UI.

## 🌿 Branch 5: Translation Feedback (`feat/translation-feedback`)

**Goal:** Implement the "Check My Translation" feedback flow.

- [ ] **Backend:** Create `check_translation` endpoint with morphology-aware prompt.
- [ ] **Frontend:** Add "Check Translation" input mode to segments.
- [ ] Display AI feedback/corrections.

---
**Next Step:** Execute Branch 1.

### To-dos

- [ ] Remove static lexical routes and external links
- [ ] Create database models for StudentNote and Highlight
- [ ] Implement backend API for notes and highlights
- [ ] Implement Frontend Notepad component
- [ ] Implement Frontend Highlighting logic
- [ ] Setup LLM Service (Provider interface + Groq/Mock impl)
- [ ] Implement Contextual Translation Suggestion endpoint
- [ ] Implement Translation Feedback endpoint
- [ ] Integrate LLM features into Frontend UI