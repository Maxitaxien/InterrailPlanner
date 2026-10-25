import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("https://tile.openstreetmap.org/**", route => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGN48fY+AAV1ArUsmq7KAAAAAElFTkSuQmCC", "base64") }));
});

test("compare island burdens and explicitly select a final stay", async ({ page }) => {
  const mutations: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET' && /\/api\/(trips|itineraries)/.test(request.url())) mutations.push(request.url()); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Compare final destinations', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Compare selected stays', exact: true }).click();
  const table = dialog.getByRole('table');
  await expect(table.getByRole('row', { name: /Corfu/ })).toContainText('1 ferry crossing');
  await expect(table.getByRole('row', { name: /Crete/ })).toContainText('2 ferry crossing');
  expect(mutations).toEqual([]);
  await dialog.getByRole('button', { name: 'Choose Corfu', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Southern endpoint', exact: true })).toHaveValue('corfu');
  await expect(page.getByRole('combobox', { name: 'Final region', exact: true })).toHaveValue('greece');
  expect(mutations).toEqual([]);
});

test("connection margins show overnight arrival and reject a tight onward service", async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Compare final destinations', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Compare selected stays', exact: true }).click();
  await dialog.getByText('Corfu · route, connections & arrival planning', { exact: true }).click();
  const connection = dialog.locator('.comparison-route').filter({ has: page.getByText('Corfu · route, connections & arrival planning', { exact: true }) });
  await expect(connection).toContainText('Brindisi railway station');
  await expect(connection).toContainText('Costa Morena');
  await expect(connection).toContainText('Disembark');
  await connection.getByText('Check researched connection times', { exact: true }).click();
  await connection.getByLabel('Arrive at starting station / city · optional', { exact: true }).fill('2027-06-10T20:00');
  await connection.getByLabel('Ferry departure · port local time', { exact: true }).fill('2027-06-10T22:00');
  await connection.getByLabel('Ferry arrival · port local time', { exact: true }).fill('2027-06-11T06:00');
  await connection.getByLabel('Onward service departure · destination local time · optional', { exact: true }).fill('2027-06-11T07:00');
  await connection.getByRole('button', { name: 'Calculate connection margins', exact: true }).click();
  await expect(connection.getByRole('status')).toContainText('too little margin');
  await expect(connection.getByRole('status')).toContainText('Early/late arrival');
  await expect(connection.getByRole('status')).toContainText('extra overnight stay');
  await expect(connection.getByRole('status')).toContainText('Europe/Rome');
  await expect(connection.getByRole('status')).toContainText('Europe/Athens');
  await connection.getByLabel('Ferry check-in / boarding allowance · minutes', { exact: true }).fill('180');
  await expect(connection.getByRole('status')).toHaveCount(0);
});

test("mobile comparison fits the dialog and can change a saved endpoint", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('spinbutton', { name: 'Calendar days', exact: true }).fill('35');
  await page.getByRole('button', { name: /Create trip & find routes/ }).click();
  await expect(page.locator('.route-stop-card')).not.toHaveCount(0);
  await page.getByRole('button', { name: 'Compare final destinations', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('checkbox', { name: /Lefkada/ }).check();
  await dialog.getByRole('button', { name: 'Compare selected stays', exact: true }).click();
  await expect(dialog.getByRole('table')).toBeVisible();
  const pageWidth = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(pageWidth.scroll).toBeLessThanOrEqual(pageWidth.viewport);
  await dialog.getByRole('table').locator('tbody tr').first().scrollIntoViewIfNeeded();
  await dialog.screenshot({ path: 'test-results/endpoint-comparison-mobile.png' });
  await dialog.getByRole('button', { name: 'Choose Lefkada · Lefkada Town', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('.route-stop-card').last()).toContainText('Lefkada');
  await page.reload();
  await expect(page.locator('.route-stop-card').last()).toContainText('Lefkada');
  await expect(page.getByRole('button', { name: 'Research flights from PVK', exact: true })).toBeVisible();
});

test("Brindisi compares western islands with explicit intermediate ports", async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Compare final destinations', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', { name: 'Compare from', exact: true }).selectOption('brindisi');
  for (const name of ['Corfu', 'Kefalonia · Sami', 'Crete · Heraklion']) {
    await dialog.getByRole('checkbox', { name: new RegExp(`^${name}`) }).uncheck();
  }
  for (const name of ['Paxos · Gaios', 'Ithaca · Vathy', 'Meganisi · Spartochori', 'Elba · Portoferraio']) {
    await dialog.getByRole('checkbox', { name: new RegExp(`^${name}`) }).check();
  }
  await dialog.getByRole('button', { name: 'Compare selected stays', exact: true }).click();
  await expect(dialog.getByRole('row', { name: /Paxos · Gaios/ })).toContainText('2 ferry crossing');
  await dialog.getByText('Meganisi · Spartochori · route, connections & arrival planning', { exact: true }).click();
  const meganisi = dialog.locator('.comparison-route').filter({ has: page.getByText('Meganisi · Spartochori · route, connections & arrival planning', { exact: true }) });
  await expect(meganisi).toContainText('Nydri');
  await expect(meganisi).toContainText('Spilia');
  await expect(meganisi).toContainText('Spartochori');
  await dialog.getByRole('button', { name: 'Choose Paxos · Gaios', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Southern endpoint', exact: true })).toHaveValue('paxos');
});
