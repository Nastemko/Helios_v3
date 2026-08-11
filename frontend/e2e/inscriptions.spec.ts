import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * End-to-end coverage for the Inscription Workbench.
 *
 * Every /api/inscriptions call is stubbed, so the suite runs without the
 * backend, without the Ithaca/Aeneas checkpoints and without auth. What it
 * proves is the part that actually broke: that the gap notation the UI teaches
 * survives to the request body, and that a declined analysis is visible rather
 * than silently rendering as success.
 */

// Comfortably over the model's 25-character minimum.
const TEXT_WITH_GAPS = 'εδοξεν τηι βουληι και τωι δημωι ????? αθηναιων';
const TEXT_NO_GAPS = 'ευψυχι αλεξανδρε ουδεις αθανατος';

const MODEL_STATUS = {
  models: {
    greek: { available: true, model_name: 'Ithaca' },
    latin: { available: true, model_name: 'Aeneas' },
  },
  features: [],
  supported_languages: ['greek', 'latin'],
};

const STATS = {
  total_inscriptions: 178551,
  inscriptions_with_dates: 100000,
  regions_count: 30,
  date_range: { earliest: -800, latest: 800 },
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

/**
 * The inscription textarea. The corpus browser below it also renders a search
 * input, so a bare getByRole('textbox') is ambiguous.
 */
const inscriptionInput = (page: Page) => page.locator('textarea');

/** Stub the read-only endpoints the page loads on mount. */
async function stubPageLoad(page: Page) {
  // AuthContext asks the backend whether auth is required before rendering any
  // route. This mirrors the DEBUG=True reply, where the shared dev user is
  // already signed in; without it the app renders the login gate instead.
  await page.route('**/api/auth/status', (route) =>
    json(route, {
      authenticated: true,
      user: {
        id: 1,
        email: 'dev@helios.local',
        name: 'Dev User',
        picture: null,
      },
    })
  );
  await page.route('**/api/inscriptions/model/status', (route) => json(route, MODEL_STATUS));
  await page.route('**/api/inscriptions/stats', (route) => json(route, STATS));
  await page.route('**/api/inscriptions/regions**', (route) => json(route, []));
  // The browser panel lists the corpus; an empty page keeps the DOM small.
  await page.route(/\/api\/inscriptions\/\?/, (route) => json(route, []));
}

/** Capture the body of the next POST to `endpoint`, answering with `response`. */
function capturePost(page: Page, endpoint: string, response: unknown) {
  const received: Record<string, unknown>[] = [];
  page.route(`**/api/inscriptions/${endpoint}`, (route) => {
    received.push(route.request().postDataJSON());
    return json(route, response);
  });
  return received;
}

const restorationResponse = (overrides: Record<string, unknown> = {}) => ({
  input_text: TEXT_WITH_GAPS,
  top_prediction: 'εδοξεν τηι βουληι και τωι δημωι βουλης αθηναιων',
  // The six characters of 'βουλης', which replaced the '?????' gap.
  restored_indices: [32, 33, 34, 35, 36, 37],
  alternatives: [],
  available: true,
  message: '',
  ...overrides,
});

const attributionResponse = () => ({
  input_text: TEXT_NO_GAPS,
  locations: [{ location_id: 1, name: 'Attica', score: 0.87 }],
  year_scores: new Array(160).fill(0).map((_, i) => (i === 80 ? 1 : 0)),
  predicted_date_range: { min: -50, max: 50, confidence: 0.87 },
  available: true,
  message: '',
});

test.beforeEach(async ({ page }) => {
  await stubPageLoad(page);
  await page.goto('/inscriptions');
});

test('sends the gap notation exactly as typed', async ({ page }) => {
  const requests = capturePost(page, 'restore', restorationResponse());

  await inscriptionInput(page).fill(TEXT_WITH_GAPS);
  await page.getByRole('button', { name: 'Restore' }).click();

  await expect.poll(() => requests.length).toBe(1);
  // Normalization is the server's job; the client must not mangle the marks.
  expect(requests[0].text).toBe(TEXT_WITH_GAPS);
  expect(requests[0].language).toBe('greek');
});

test('Restore stays disabled until the text marks a gap', async ({ page }) => {
  const restore = page.getByRole('button', { name: 'Restore' });

  await inscriptionInput(page).fill(TEXT_NO_GAPS);
  await expect(restore).toBeDisabled();
  await expect(restore).toHaveAttribute('title', /\? or #/);

  await inscriptionInput(page).fill(TEXT_WITH_GAPS);
  await expect(restore).toBeEnabled();
});

test('a hyphen does not count as a gap', async ({ page }) => {
  // '-' is the model's internal spelling and is rejected by the API, so it
  // must not enable an action that is guaranteed to fail.
  await inscriptionInput(page).fill(TEXT_WITH_GAPS.replace(/\?/g, '-'));

  await expect(page.getByRole('button', { name: 'Restore' })).toBeDisabled();
});

test('enforces the 25-character minimum', async ({ page }) => {
  await inscriptionInput(page).fill('εδοξεν τηι ?');

  await expect(page.getByText(/at least 25 characters/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Attribute' })).toBeDisabled();

  await inscriptionInput(page).fill(TEXT_WITH_GAPS);

  await expect(page.getByText(/at least 25 characters/)).toBeHidden();
  await expect(page.getByRole('button', { name: 'Attribute' })).toBeEnabled();
});

test('each action calls only its own endpoint', async ({ page }) => {
  const attribute = capturePost(page, 'attribute', attributionResponse());
  const restore = capturePost(page, 'restore', restorationResponse());
  const contextualize = capturePost(page, 'contextualize', {
    similar: [],
    available: true,
    message: '',
  });

  await inscriptionInput(page).fill(TEXT_NO_GAPS);
  await page.getByRole('button', { name: 'Attribute' }).click();

  await expect.poll(() => attribute.length).toBe(1);
  expect(restore).toHaveLength(0);
  expect(contextualize).toHaveLength(0);
});

test('highlights the characters the model restored', async ({ page }) => {
  capturePost(page, 'restore', restorationResponse());

  await inscriptionInput(page).fill(TEXT_WITH_GAPS);
  await page.getByRole('button', { name: 'Restore' }).click();

  await expect(page.getByText('Restored Text')).toBeVisible();
  // restored_indices drives a per-character span highlight.
  const highlighted = page.locator('span.bg-teal-200');
  await expect(highlighted).toHaveCount(6);
  await expect(highlighted.first()).toHaveText('β');
  // Only the restored run is marked; the surrounding text is left plain.
  await expect(page.locator('span.bg-teal-200').last()).toHaveText('ς');
});

test('shows why the model declined instead of faking a result', async ({ page }) => {
  capturePost(
    page,
    'restore',
    restorationResponse({
      available: false,
      message: 'Input text too short.',
      top_prediction: TEXT_WITH_GAPS,
      restored_indices: [],
    })
  );

  await inscriptionInput(page).fill(TEXT_WITH_GAPS);
  await page.getByRole('button', { name: 'Restore' }).click();

  await expect(page.getByText('Input text too short.')).toBeVisible();
});

test('surfaces a rejected notation error from the API', async ({ page }) => {
  await page.route('**/api/inscriptions/restore', (route) =>
    json(
      route,
      {
        detail:
          "Use '?' for each missing character (e.g. '?????' for five) and '#' "
          + "for a gap of unknown length. '-' is not supported.",
      },
      422
    )
  );

  // hasGaps gates on '?'/'#', so include one and let the API reject the '-'.
  await inscriptionInput(page).fill('εδοξεν τηι βουληι και τωι δημωι ??--- αθηναιων');
  await page.getByRole('button', { name: 'Restore' }).click();

  await expect(page.getByText(/is not supported/)).toBeVisible();
});

test('the language toggle switches which model is called', async ({ page }) => {
  const requests = capturePost(page, 'attribute', attributionResponse());

  await page.getByRole('button', { name: /Latin \(Aeneas\)/ }).click();
  await inscriptionInput(page).fill('imp caesar divi f augustus pontifex maximus');
  await page.getByRole('button', { name: 'Attribute' }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0].language).toBe('latin');
});
