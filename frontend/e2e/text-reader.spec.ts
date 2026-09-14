import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * End-to-end coverage for the TextReader word-click path.
 *
 * The branch changed what a click sends: the segment content as `context`
 * and the clicked token's ordinal as `word_occurrence`, so the backend can
 * disambiguate repeated words. What this suite proves is that the request
 * body carries exactly those values and that punctuation is cleaned from
 * the clicked token — every /api call is stubbed, so no backend needed.
 */

// 'μῆνιν' twice: once with a trailing comma, once with a trailing period.
const SEGMENT_CONTENT = 'μῆνιν, ἄειδε θεὰ μῆνιν.';

const TEXT_DETAIL = {
  text: {
    id: 1,
    local_id: 'tlg0012.tlg001.perseus-grc1',
    author: 'Ὅμηρος',
    title: 'Ἰλιάς',
    language: 'grc',
    is_fragment: false,
  },
  segments: [
    {
      id: 11,
      book: '1',
      line: '1',
      content: SEGMENT_CONTENT,
      reference: '1.1',
      sequence: 1,
    },
  ],
  total_segments: 1,
};

const ANALYSIS = {
  word: 'μῆνιν',
  language: 'grc',
  lemma: 'μῆνις',
  pos: 'Noun',
  morphology: { case: 'Accusative' },
  definitions: [],
  lexicon_url: '',
  perseus_url: null,
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

/** A word token inside the reader segment (each token renders as a span). */
const wordTokens = (page: Page) => page.locator('[data-segment-id="11"] span');

/** Stub every endpoint the reader page touches on mount. */
async function stubPageLoad(page: Page) {
  // Same DEBUG=True-shaped reply as the inscriptions suite: without it the
  // app renders the login gate instead of the reader.
  await page.route('**/api/auth/status', (route) =>
    json(route, {
      authenticated: true,
      user: { id: 1, email: 'dev@helios.local', name: 'Dev User', picture: null },
    })
  );
  await page.route(/\/api\/texts/, (route) => {
    // The sidebar lists /api/texts/; the reader loads /api/texts/1.
    if (/\/api\/texts\/\d+/.test(route.request().url())) {
      return json(route, TEXT_DETAIL);
    }
    return json(route, []);
  });
  // WordAnalysisPanel and ToolsPanel both list annotations on mount.
  await page.route(/\/api\/annotations/, (route) => json(route, []));
}

/** Capture POST bodies to `endpoint`, answering with the canned analysis. */
function captureAnalyze(page: Page) {
  const received: Record<string, unknown>[] = [];
  page.route('**/api/analyze/word', (route) => {
    received.push(route.request().postDataJSON());
    return json(route, ANALYSIS);
  });
  return received;
}

test.beforeEach(async ({ page }) => {
  await stubPageLoad(page);
  await page.goto('/text/1');
  // The segment must be on screen before any clicks land.
  await expect(wordTokens(page).first()).toBeVisible();
});

test('clicking a repeated word sends its occurrence and the segment context', async ({
  page,
}) => {
  const requests = captureAnalyze(page);

  // The second 'μῆνιν' (index 3 of 4 tokens); one identical token precedes it.
  await wordTokens(page).nth(3).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0].word).toBe('μῆνιν');
  expect(requests[0].language).toBe('grc');
  expect(requests[0].context).toBe(SEGMENT_CONTENT);
  expect(requests[0].word_occurrence).toBe(1);
});

test('clicking the first occurrence sends occurrence 0', async ({ page }) => {
  const requests = captureAnalyze(page);

  await wordTokens(page).nth(0).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0].word_occurrence).toBe(0);
});

test('punctuation is cleaned from the clicked token', async ({ page }) => {
  const requests = captureAnalyze(page);

  // The rendered token carries a trailing comma; the API must not see it.
  await wordTokens(page).nth(0).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0].word).toBe('μῆνιν');
});

test('all identical tokens highlight and the analysis panel renders', async ({
  page,
}) => {
  captureAnalyze(page);

  await wordTokens(page).nth(3).click();

  // Highlight matches on normalized form, so both 'μῆνιν' tokens light up.
  await expect(page.locator('[data-segment-id="11"] span.bg-blue-200')).toHaveCount(2);
  // The stubbed analysis result reaches the panel.
  await expect(page.getByText('μῆνις')).toBeVisible();
});
