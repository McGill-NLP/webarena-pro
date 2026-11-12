import { expect, test, type Page } from '@playwright/test';

const airports = [
  { iata: 'YUL', city_name: 'Montreal' },
  { iata: 'JFK', city_name: 'New York' },
  { iata: 'LHR', city_name: 'London' },
  { iata: 'CDG', city_name: 'Paris' },
].map(airport => ({
  ...airport, name: `${airport.city_name} Airport`, country: 'Test country',
  display_name: `${airport.city_name} (${airport.iata})`, hub_score: 1,
}));

test.beforeEach(async ({ page }) => {
  await page.route(url => url.pathname.startsWith('/api/'), async route => {
    const url = new URL(route.request().url());
    switch (url.pathname) {
      case '/api/auth/check':
        return route.fulfill({ json: {} });
      case '/api/config':
        return route.fulfill({ json: { benchmark_mode: false, benchmark_date: null } });
      case '/api/geolocation':
        return route.fulfill({ json: { currency: 'USD', nearest_airports: [] } });
      case '/api/currency/rates':
        return route.fulfill({ json: { rates: { USD: 1 }, symbols: { USD: '$' } } });
      case '/api/airports/autocomplete': {
        const query = url.searchParams.get('q')!.toLowerCase();
        const matches = airports.filter(airport =>
          airport.iata.toLowerCase() === query || airport.city_name.toLowerCase().startsWith(query));
        return route.fulfill({ json: matches });
      }
      case '/api/search':
        return route.fulfill({ json: {
          outbound_flights: [], return_flights: [], multi_city_flights: [],
          search_id: 'test', origin: 'YUL', destination: 'JFK', same_airline_discount: 1,
        } });
      default:
        throw new Error(`Unexpected API request: ${url.pathname}`);
    }
  });
  await page.goto('/');
  await page.getByLabel('Trip type').selectOption('one_way');
  await page.getByLabel('Departure', { exact: true }).fill(departureDate());
  await page.getByLabel('Where from?').fill('YUL');
  await expect(page.getByTestId('airport-option-YUL')).toBeVisible();
});

function departureDate() {
  const date = new Date();
  date.setDate(date.getDate() + 7);
  return date.toISOString().slice(0, 10);
}

async function expectSearch(page: Page, destination: string) {
  await expect(page.getByTestId('search-button')).toBeEnabled();
  const request = page.waitForRequest('**/api/search');
  await page.getByTestId('search-button').click();
  expect((await request).postDataJSON().legs[0]).toEqual({
    origin: 'YUL', destination, date: departureDate(),
  });
}

test('Any and Anywhere cannot submit an unknown airport, including on Enter', async ({ page }) => {
  const searches: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/search') searches.push(request.url());
  });
  const destination = page.getByLabel('Where to?');
  await destination.fill('Any');
  await expect(page.getByTestId('search-button')).toBeDisabled();
  await expect(destination).toHaveAttribute('aria-invalid', 'true');
  await destination.pressSequentially('where');
  await expect(page.getByRole('status')).toHaveText('No matching airports. Choose a specific city or airport.');
  await destination.press('Enter');
  await destination.press('Tab');
  await expect(destination).toHaveValue('Anywhere');
  await expect(page.getByTestId('search-button')).toBeDisabled();
  expect(searches).toEqual([]);
});

for (const text of ['ZZZ', 'Nowhere (ZZZ)']) {
  test(`rejects unsupported airport text: ${text}`, async ({ page }) => {
    await page.getByLabel('Where to?').fill(text);
    await expect(page.getByLabel('Where to?')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByTestId('search-button')).toBeDisabled();
  });
}

for (const text of [' jfk ', 'New York (jfk)']) {
  test(`accepts a validated typed code after blur: ${text}`, async ({ page }) => {
    await page.getByLabel('Where to?').fill(text);
    await page.getByLabel('Where to?').press('Tab');
    await expectSearch(page, 'JFK');
  });
}

test('a three-letter city prefix requires selecting an airport', async ({ page }) => {
  await page.getByLabel('Where to?').fill('Par');
  await expect(page.getByTestId('airport-option-CDG')).toBeVisible();
  await expect(page.getByTestId('search-button')).toBeDisabled();
  await page.getByTestId('airport-option-CDG').click();
  await expect(page.getByLabel('Where to?')).toHaveValue('Paris (CDG)');
  await expectSearch(page, 'CDG');
});

test('editing invalidates a selected airport and ignores an older lookup', async ({ page }) => {
  await page.getByLabel('Where to?').fill('LHR');
  await expect(page.getByTestId('search-button')).toBeEnabled();

  let releaseLookup!: () => void;
  const pendingLookup = new Promise<void>(resolve => { releaseLookup = resolve; });
  await page.route('**/api/airports/autocomplete?q=JFK', async route => {
    await pendingLookup;
    await route.fulfill({ json: [airports[1]] });
  });
  const requested = page.waitForRequest('**/api/airports/autocomplete?q=JFK');
  await page.getByLabel('Where to?').fill('JFK');
  await requested;
  await expect(page.getByTestId('search-button')).toBeDisabled();
  await page.getByLabel('Where to?').fill('Anywhere');
  await expect(page.getByLabel('Where to?')).toHaveAttribute('aria-invalid', 'true');
  const completed = page.waitForResponse('**/api/airports/autocomplete?q=JFK');
  releaseLookup();
  await completed;
  await expect(page.getByTestId('search-button')).toBeDisabled();
  await expect(page.getByLabel('Where to?')).toHaveValue('Anywhere');
  await expect(page.getByTestId('airport-option-JFK')).not.toBeVisible();
});

test('lookup errors keep Search disabled and a new edit can recover', async ({ page }) => {
  await page.route('**/api/airports/autocomplete?q=JFK', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.getByLabel('Where to?').fill('JFK');
  await expect(page.getByRole('status')).toHaveText('Unable to look up airports. Edit the field to try again.');
  await expect(page.getByTestId('search-button')).toBeDisabled();
  await page.unroute('**/api/airports/autocomplete?q=JFK');
  await page.getByLabel('Where to?').fill('jfk');
  await expectSearch(page, 'JFK');
});

test('validates every multi-city airport', async ({ page }) => {
  await page.getByLabel('Trip type').selectOption('multi_city');
  await page.getByTestId('mc-origin-0-input').fill('YUL');
  await page.getByTestId('mc-dest-0-input').fill('JFK');
  await page.getByTestId('mc-date-0-input').fill(departureDate());
  await page.getByTestId('mc-dest-1-input').fill('Any');
  await page.getByTestId('mc-date-1-input').fill(departureDate());
  await expect(page.getByTestId('mc-dest-1-input')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('search-button')).toBeDisabled();
  await page.getByTestId('mc-dest-1-input').fill('LHR');
  await expect(page.getByTestId('search-button')).toBeEnabled();
  const request = page.waitForRequest('**/api/search');
  await page.getByTestId('search-button').click();
  expect((await request).postDataJSON().legs).toEqual([
    { origin: 'YUL', destination: 'JFK', date: departureDate() },
    { origin: 'JFK', destination: 'LHR', date: departureDate() },
  ]);
});
