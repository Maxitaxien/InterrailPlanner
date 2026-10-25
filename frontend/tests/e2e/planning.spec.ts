import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  // Keep these interaction tests independent of third-party tile availability.
  await page.route("https://tile.openstreetmap.org/**", route => route.fulfill({
    contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGN48fY+AAV1ArUsmq7KAAAAAElFTkSuQmCC", "base64")
  }));
});
test("create, edit, save and reopen a trip", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Create trip & find routes" })).toBeEnabled();
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.getByRole("navigation", { name: "Route alternatives" }).getByRole("button")).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Prague", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Venice", exact: true })).toBeVisible();
  await expect(page.getByText("20", { exact: true })).toBeVisible();
  const nights = page.getByRole("spinbutton", { name: "Nights in Prague" });
  const oldNights = Number(await nights.inputValue());
  await nights.fill(String(oldNights + 1));
  await nights.press("Tab");
  await expect(page.getByRole("status")).toHaveText("Changes saved and itinerary recalculated.");
  await expect(page.getByRole("spinbutton", { name: "Nights in Prague" })).toHaveValue(String(oldNights + 1));
  await page.reload();
  await expect(page.getByRole("spinbutton", { name: "Nights in Prague" })).toHaveValue(String(oldNights + 1));
  await expect(page.getByRole("combobox", { name: "Add a stop", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add stop", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Make time for the good bits." })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Find ideas for this route" })).toHaveCount(0);
  await expect(page.locator(".route-stop-card").last().getByRole("combobox", { name: "Switch final destination", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Things to do in Prague", exact: true })).toBeVisible();
  await page.getByLabel("Flight departure").fill("2027-06-21");
  await page.getByRole("button", { name: "Prepare flight search" }).click();
  await expect(page.getByRole("link", { name: "Open external search" })).toHaveAttribute("href", /google.com\/travel\/flights/);
  await expect(page.getByText("No live offers retrieved", { exact: false })).toBeVisible();
  expect(errors).toEqual([]);
});
test("rejects infeasible edit and preserves stored route", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  const nights = page.getByRole("spinbutton", { name: "Nights in Prague" });
  await expect(nights).toBeVisible();
  const previous = await nights.inputValue();
  await nights.fill("30"); await nights.press("Tab");
  await expect(page.locator(".message[role=alert]")).toContainText("exceed the trip duration");
  await page.reload();
  await expect(page.getByRole("spinbutton", { name: "Nights in Prague" })).toHaveValue(previous);
});
test("zero-night visits persist without removing a must-see city", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  const nights = page.getByRole("spinbutton", { name: "Nights in Prague" });
  await expect(nights).toBeVisible();
  await nights.fill("0");
  await nights.press("Tab");
  await expect(page.getByRole("status")).toHaveText("Changes saved and itinerary recalculated.");
  await expect(nights).toHaveValue("0");
  await expect(page.getByText("Day visit · no overnight stay", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByRole("spinbutton", { name: "Nights in Prague" })).toHaveValue("0");
  await expect(page.getByRole("heading", { name: "Prague", exact: true })).toBeVisible();
});
test("overnight intentions work before timetables exist and persist on reopening", async ({ page }) => {
  let timetableCalls = 0;
  await page.route("**/api/travel/rail/timetables", () => { timetableCalls++; throw new Error("No timetable search expected"); });
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  const firstCard = page.locator(".route-stop-card").first();
  await firstCard.getByRole("button", { name: "Plan & book this train leg" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Plan overnight travel · unverified" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(firstCard.locator(".leg-confidence")).toHaveText("Overnight intention · unverified");
  await expect(firstCard.getByRole("button", { name: "Plan & book this train leg" })).toBeFocused();
  await page.reload();
  await expect(firstCard.locator(".leg-confidence")).toHaveText("Overnight intention · unverified");
  await firstCard.getByRole("button", { name: "Plan & book this train leg" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear travel plan · use estimates" }).click();
  await expect(firstCard.locator(".leg-confidence")).toHaveText("Estimated corridor · timetable not checked");
  expect(timetableCalls).toBe(0);
});
test("reopened saved research shows its station times without a timetable refresh", async ({ page }) => {
  let timetableCalls = 0;
  await page.route("**/api/travel/rail/timetables", async route => {
    timetableCalls++;
    await route.fulfill({ json: { status: "not_configured", message: "Fixture only", notice: "Not a booking", journeys: [], prepared_sources: [] } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.locator(".route-stop-card").first()).toBeVisible();
  // Browser-only saved-response fixture. No synthetic trains enter application seeds.
  await page.route("**/api/trips/*", async route => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const trip = await response.json();
    trip.itineraries[0].legs[0].travel_plan = { kind: "timetable", status_label: "Saved timetable · recheck needed", needs_recheck: true,
      queried_at: "2026-10-01T12:00:00Z", recheck_after: "2026-10-02T12:00:00Z", arrival_date: "2027-06-02",
      journey: { departure: "2027-06-01T20:00:00Z", arrival: "2027-06-02T04:00:00Z", legs: [{ train: "Synthetic night train", operator: "Fixture Rail", origin: "Synthetic station A", destination: "Synthetic station B", departure: "2027-06-01T20:00:00Z", arrival: "2027-06-02T04:00:00Z", origin_timezone: "Europe/Oslo", destination_timezone: "Europe/Prague" }] } };
    await route.fulfill({ json: trip });
  });
  await page.reload();
  const firstCard = page.locator(".route-stop-card").first();
  await expect(firstCard.locator(".leg-confidence")).toHaveText("Saved timetable · recheck needed");
  await expect(firstCard).toContainText("Synthetic night train");
  await firstCard.getByRole("button", { name: "Plan & book this train leg" }).click();
  const saved = page.getByLabel("Saved timetable journey");
  await expect(saved).toContainText("22:00 (Europe/Oslo)");
  await expect(saved).toContainText("06:00 (Europe/Prague)");
  await saved.getByText("Saved trains & station times").click();
  await expect(saved).toContainText("Synthetic station A → Synthetic station B");
  expect(timetableCalls).toBe(0);
});
test("mobile layout and offline AI settings", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Take the scenic way." })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("link", { name: "AI settings" }).click();
  await expect(page.getByText("Connection: Ollama unavailable")).toBeVisible();
  await page.getByLabel("Model", { exact: true }).fill("qwen3:8b");
  await page.getByRole("button", { name: "Save model" }).click();
  await expect(page.getByRole("status")).toHaveText("Model preference saved in this browser.");
});

test("city activity ideas are explicitly requested, saved and reopened without generating again", async ({ page }) => {
  let generations = 0;
  page.on("request", request => { if (request.method() === "POST" && /\/cities\/prague\/ideas$/.test(request.url())) generations++; });
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  const card = page.locator(".route-stop-card").filter({ has: page.getByRole("heading", { name: "Prague", exact: true }) });
  await card.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("No saved ideas for Prague yet");
  expect(generations).toBe(0);
  await dialog.getByLabel("What would you like to do?").fill("A slow day with architecture and good food");
  await dialog.getByRole("button", { name: "Generate & save ideas", exact: true }).click();
  await expect(dialog.getByLabel("Saved ideas for Prague")).toContainText("Curated fallback");
  await expect(dialog).toContainText("New ideas saved to your trip");
  await expect(dialog).toContainText("No concrete recommendations this time");
  await expect(dialog.getByRole("heading", { name: "A slow neighbourhood walk · generic alternative", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Generate & save ideas", exact: true })).toHaveClass(/city-generate/);
  expect(generations).toBe(1);
  await page.keyboard.press("Escape");
  await page.reload();
  await card.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  await expect(dialog.getByLabel("Saved ideas for Prague")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Saved recommendations (1)", exact: true }).click();
  await dialog.getByRole("button", { name: /^A slow day with architecture and good food/ }).click();
  await expect(dialog.getByLabel("Saved ideas for Prague")).toContainText("A slow day with architecture and good food");
  await expect(dialog.getByLabel("What would you like to do?")).toHaveValue("A slow day with architecture and good food");
  expect(generations).toBe(1);
  await dialog.getByRole("button", { name: "Regenerate & save new version", exact: true }).click();
  await expect(dialog.locator(".saved-recommendation")).toHaveCount(2);
  expect(generations).toBe(2);
  await dialog.getByText("Model & web research", { exact: true }).click();
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  const size = await dialog.boundingBox();
  expect(size!.width).toBeLessThan(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await dialog.getByLabel("What would you like to do?").fill("A different day focused on cafés");
  const latest = dialog.locator(".saved-recommendation").first();
  await latest.getByRole("button", { name: "Delete saved recommendations", exact: true }).click();
  await latest.getByRole("button", { name: "Keep saved version", exact: true }).click();
  await expect(dialog.locator(".saved-recommendation")).toHaveCount(2);
  await latest.getByRole("button", { name: "Delete saved recommendations", exact: true }).click();
  await latest.getByRole("button", { name: "Permanently delete version", exact: true }).click();
  await expect(dialog.locator(".saved-recommendation")).toHaveCount(1);
  await expect(dialog.getByLabel("What would you like to do?")).toHaveValue("A different day focused on cafés");
  expect(generations).toBe(2);
  await page.reload();
  await card.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  await dialog.getByRole("button", { name: "Saved recommendations (1)", exact: true }).click();
  await dialog.getByRole("button", { name: "Delete saved recommendations", exact: true }).click();
  await dialog.getByRole("button", { name: "Permanently delete version", exact: true }).click();
  await expect(dialog).toContainText("No saved ideas for Prague yet");
  await expect(dialog.getByRole("button", { name: /^Saved recommendations/ })).toHaveCount(0);
  expect(generations).toBe(2);
});

test("dated city recommendations save the active route visit month and season", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Start date · optional", { exact: true }).fill("2027-06-01");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.getByRole("navigation", { name: "Route alternatives" }).getByRole("button")).toHaveCount(3);
  await page.getByRole("navigation", { name: "Route alternatives" }).getByRole("button").nth(1).click();
  await page.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const response = page.waitForResponse(response => response.request().method() === "POST" && /\/cities\/prague\/ideas$/.test(response.url()));
  await dialog.getByRole("button", { name: "Generate & save ideas", exact: true }).click();
  const saved = await response;
  const result = await saved.json();
  expect(saved.request().postDataJSON().itinerary_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(result.request.travel_context.scope).toBe("city_visit");
  expect(result.request.travel_context.periods).toEqual([{ month: "June", year: 2027, season: "summer" }]);
  await expect(dialog).toContainText("June 2027 (summer)");
  await expect(dialog).toContainText("planned city visit");
});

test("dialog text selection can end outside without closing, while deliberate dismissal still works", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  const opener = page.getByRole("button", { name: "Things to do in Prague", exact: true });
  await opener.click();
  const dialog = page.getByRole("dialog");
  const prompt = dialog.getByLabel("What would you like to do?");
  const text = "A relaxed day with architecture, food and time to explore together.";
  await prompt.fill(text);
  const box = (await prompt.boundingBox())!;
  const bounds = (await dialog.boundingBox())!;
  const outside = { x: Math.max(2, bounds.x - 20), y: box.y + 18 };
  await page.mouse.move(box.x + 80, box.y + 18);
  await page.mouse.down();
  await page.mouse.move(outside.x, outside.y, { steps: 8 });
  await page.mouse.up();
  await expect(dialog).toBeVisible();
  await expect(prompt).toHaveValue(text);
  await page.mouse.move(outside.x, outside.y);
  await page.mouse.down();
  await page.mouse.move(box.x + 20, box.y + 18, { steps: 8 });
  await page.mouse.up();
  await expect(dialog).toBeVisible();
  await page.mouse.click(outside.x, outside.y);
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  await opener.click();
  await page.getByRole("button", { name: "Close journey dialog", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await opener.click();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("city research always uses web search without configurable toggles or automatic requests", async ({ page }) => {
  let generations = 0;
  await page.route("**/api/trips/*/cities/prague/ideas", async route => {
    if (route.request().method() === "POST") {
      generations++;
      await route.fulfill({ status: 503, json: { error: { message: "Research test fixture" } } });
    } else {
      const response = await route.fetch();
      await route.fulfill({ json: { ...await response.json(), web_available: true } });
    }
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await page.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Model & web research", { exact: true }).click();
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await expect(dialog.getByRole("checkbox", { name: /Refresh web sources/ })).toHaveCount(0);
  expect(generations).toBe(0);
  await dialog.getByLabel("Research focus · sent to search engines", { exact: true }).fill("cat cafés");
  const request = page.waitForRequest(request => request.method() === "POST" && /\/cities\/prague\/ideas$/.test(request.url()));
  await dialog.getByRole("button", { name: "Generate & save ideas", exact: true }).click();
  const payload = (await request).postDataJSON();
  expect(payload).not.toHaveProperty("use_web");
  expect(payload.research_focus).toBe("cat cafés");
  expect(payload).not.toHaveProperty("refresh_web");
  await expect(dialog.getByRole("alert")).toContainText("Research test fixture");
  expect(generations).toBe(1);
});

test("failed AI validation keeps useful search leads visible without claiming visit times", async ({ page }) => {
  await page.route("**/api/trips/*/cities/prague/ideas", async route => {
    if (route.request().method() === "GET") {
      const response = await route.fetch();
      return route.fulfill({ json: { ...await response.json(), web_available: true } });
    }
    return route.fulfill({ json: {
      id: "synthetic-lead", saved_at: "2026-10-16T12:00:00Z", source: "web_research", generation_status: "invalid_response", cached: false,
      model: null, introduction: "These are search results to investigate, not verified venues.", warning: "Verify source details.",
      web_used: true, web_status: "searched", web_query: "cat activities in Prague",
      query_plan: { query: "cat activities in Prague", model: "qwen3:14b", source: "local_model", status: "planned" },
      request: { question: "Cat activities please", use_web: true },
      sources: [{ id: "w1", title: "Synthetic Cat Café", url: "https://example.com/cats", kind: "search_excerpt", retrieved_at: "2026-10-16T12:00:00Z" }],
      ideas: [{ title: "Research lead: Synthetic Cat Café", description: "A synthetic fixture, not a real venue.", why_for_you: "Open the source to check relevance.", time_minutes: 15, best_time: "flexible", source_ids: ["w1"] }],
    } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await page.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("What would you like to do?").fill("Cat activities please");
  await dialog.getByRole("button", { name: "Generate & save ideas", exact: true }).click();
  await expect(dialog.getByRole("heading", { name: "Research lead: Synthetic Cat Café", exact: true })).toBeVisible();
  await expect(dialog).toContainText("this does not mean the search found nothing");
  await expect(dialog).toContainText("Saved search query: cat activities in Prague");
  await expect(dialog).toContainText("Query planned locally by qwen3:14b");
  await expect(dialog.getByRole("link", { name: /^Synthetic Cat Café/ }).first()).toHaveAttribute("href", "https://example.com/cats");
  await expect(dialog).not.toContainText("Allow ~15 min");
});

test("missing required search service explains why city generation is disabled", async ({ page }) => {
  await page.route("**/api/trips/*/cities/prague/ideas", async route => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), web_available: false } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await page.getByRole("button", { name: "Things to do in Prague", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("City recommendations require SearXNG");
  await expect(dialog.getByRole("button", { name: "Generate & save ideas", exact: true })).toBeDisabled();
});

test("map city details, adding a stop, and the wide horizontal layout", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1200 });
  const errors: string[] = [];
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator(".map-marker")).toHaveCount(146);
  const initialOslo = await page.getByRole("button", { name: "Explore Oslo", exact: true }).locator("span").boundingBox();
  await page.getByRole("button", { name: "Explore Berlin", exact: true }).click();
  await expect(page.locator(".map-detail").getByRole("heading", { name: "Berlin", exact: true })).toBeVisible();
  await expect(page.locator(".map-detail")).toContainText("Museum Island");
  await page.getByRole("button", { name: "Add must-see stop", exact: true }).click();
  await expect(page.locator(".selected-stops")).toContainText("Berlin");
  await page.getByRole("button", { name: "Remove must-see stop", exact: true }).click();
  const selectedOslo = await page.getByRole("button", { name: "Explore Oslo", exact: true }).locator("span").boundingBox();
  expect(selectedOslo!.x).toBeCloseTo(initialOslo!.x, 0);
  await page.getByRole("button", { name: "Close map details" }).click();
  await page.getByText("Your existing pass", { exact: true }).click();
  await page.getByLabel("Total travel days", { exact: true }).fill("15");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.locator(".results .map-marker")).toHaveCount(146);
  const canvas = page.locator(".results .map");
  const size = await canvas.boundingBox();
  expect(size!.width).toBeGreaterThan(1700);
  expect(size!.height).toBeGreaterThan(700);
  const cards = page.locator(".route-stop-card");
  const first = await cards.nth(0).boundingBox();
  const second = await cards.nth(1).boundingBox();
  expect(second!.x).toBeGreaterThan(first!.x);
  expect(second!.y).toBe(first!.y);
  await page.getByRole("button", { name: "Explore Milan", exact: true }).click();
  const beforeAddOslo = await page.getByRole("button", { name: "Explore Oslo", exact: true }).locator("span").boundingBox();
  const beforeAddMap = await canvas.boundingBox();
  await page.getByRole("button", { name: "Add to route", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Changes saved and itinerary recalculated.");
  await expect(page.getByRole("spinbutton", { name: "Nights in Milan", exact: true })).toBeVisible();
  await expect(page.locator(".results .map-marker")).toHaveCount(146);
  const afterAddOslo = await page.getByRole("button", { name: "Explore Oslo", exact: true }).locator("span").boundingBox();
  const afterAddMap = await canvas.boundingBox();
  expect(afterAddOslo!.x - afterAddMap!.x).toBeCloseTo(beforeAddOslo!.x - beforeAddMap!.x, 0);
  expect(afterAddOslo!.y - afterAddMap!.y).toBeCloseTo(beforeAddOslo!.y - beforeAddMap!.y, 0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator(".results .map-explorer").screenshot({ path: "test-results/map-desktop.png" });
  await page.getByRole("button", { name: "Close map details" }).click();
  const oslo = await page.getByRole("button", { name: "Explore Oslo", exact: true }).locator("span").boundingBox();
  const bergen = await page.getByRole("button", { name: "Explore Bergen", exact: true }).locator("span").boundingBox();
  await page.mouse.click((oslo!.x + oslo!.width / 2 + bergen!.x + bergen!.width / 2) / 2, (oslo!.y + oslo!.height / 2 + bergen!.y + bergen!.height / 2) / 2);
  await expect(page.locator(".map-detail")).toContainText("RAIL CORRIDOR");
  await expect(page.locator(".map-detail")).toContainText("Bergen");
  await expect(page.locator(".map-detail")).toContainText("7h estimated");
  await page.locator(".map-detail").getByRole("button", { name: "Plan & book this train leg" }).click();
  await page.getByRole("tab", { name: "Reservations", exact: true }).click();
  await expect(page.getByRole("dialog").locator(".booking-status")).toContainText("Guidance only");
  await expect(page.getByRole("dialog").getByRole("link", { name: "Vy ↗", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Close map details" }).click();
  await page.getByRole("button", { name: "Explore Milan on map", exact: true }).click();
  await expect(page.locator(".map-detail").getByRole("heading", { name: "Milan", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator(".results .map-explorer").screenshot({ path: "test-results/map-mobile.png" });
  expect(errors).toEqual([]);
});

test("failed generation retries the edited one-stop request, and route cities can become must-see", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Your existing pass", { exact: true }).click();
  await page.getByLabel("Total travel days", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.locator(".message[role=alert]")).toContainText("your pass has 1 remaining");
  await page.getByRole("button", { name: "Remove Prague from must-see stops" }).click();
  await page.getByRole("button", { name: "Remove Venice from must-see stops" }).click();
  await page.getByRole("searchbox", { name: "Find a city" }).fill("Bergen");
  await page.locator(".city-search-results button").filter({ hasText: "Bergen" }).click();
  await page.getByRole("button", { name: "Add must-see stop", exact: true }).click();
  await page.getByLabel("Total travel days", { exact: true }).fill("15");
  const updated = page.waitForRequest(request => request.method() === "PATCH" && /\/api\/trips\/[^/]+$/.test(request.url()));
  await page.getByRole("button", { name: "Retry generation for saved trip" }).click();
  const body = (await updated).postDataJSON();
  expect(body.required_stops).toEqual(["bergen"]);
  expect(body.pass.travel_days_total).toBe(15);
  await expect(page.getByRole("navigation", { name: "Route alternatives" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bergen", exact: true })).toBeVisible();
  await expect(page.locator(".message[role=alert]")).toHaveCount(0);
  await page.getByRole("button", { name: "Choose must-see cities", exact: true }).click();
  await page.getByRole("button", { name: "Explore Bergen", exact: true }).click();
  await expect(page.getByRole("button", { name: "Remove must-see stop", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Remove must-see stop", exact: true }).click();
  await expect(page.locator(".selected-stops")).not.toContainText("Bergen");
});

test("honeymoon rail guidance uses the actual date, two adults and saved pass class", async ({ page }) => {
  let timetableCalls = 0;
  await page.route("**/api/travel/rail/coverage", async route => {
    const search = route.request().postDataJSON();
    expect(search.origin_id).toBe("oslo");
    await route.fulfill({ json: { status: "outside_prepared_dates", message: "Fixture: your date is outside the prepared rail calendars.", notice: "Prepared files only, not import verification.", sources: [{ id: "fixture", name: "Synthetic Norwegian feed", source_url: "https://example.com/timetables", license_url: "https://example.com/license", attribution: "Synthetic test data", rail_service_start: "2026-10-01", rail_service_end: "2027-02-01", rail_trip_count: 3, date_status: "outside_envelope", origin_stops: "present", destination_stops: "absent" }] } });
  });
  await page.route("**/api/travel/rail/timetables", async route => {
    timetableCalls++;
    const search = route.request().postDataJSON();
    expect(search.departure_date).toBe("2027-06-01");
    expect(search.departure_time).toBe("08:00");
    await route.fulfill({ json: { status: "scheduled", message: "Departures from test timetable fixture", notice: "Reservations and pass acceptance are not verified.", checked_at: "2027-06-01T06:00:00Z", origin_timezone: "Europe/Oslo", prepared_sources: [], journeys: [{ departure: "2027-06-01T06:00:00Z", arrival: "2027-06-01T10:00:00Z", duration_minutes: 240, transfers: 0, legs: [{ mode: "LONG_DISTANCE", origin: "Oslo S", destination: "Gothenburg C", departure: "2027-06-01T06:00:00Z", arrival: "2027-06-01T10:00:00Z", origin_timezone: "Europe/Oslo", destination_timezone: "Europe/Stockholm", operator: "Fixture Rail", train: "Test 123", real_time: false, stay_seated: false }] }] } });
  });
  await page.goto("/");
  await expect(page.getByText("JUST THE TWO OF YOU · A HONEYMOON BY RAIL")).toBeVisible();
  await page.getByLabel("Start date · optional", { exact: true }).fill("2027-06-01");
  await page.getByText("Your existing pass", { exact: true }).click();
  await page.getByRole("combobox", { name: "Pass travel class", exact: true }).selectOption("1");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  const firstCard = page.locator(".route-stop-card").first();
  await expect(firstCard).toBeVisible();
  const requested = page.waitForRequest(request => request.url().endsWith("/api/travel/rail/booking-guide"));
  const before = await firstCard.boundingBox();
  await firstCard.getByRole("button", { name: "Plan & book this train leg" }).click();
  const dialog = page.getByRole("dialog");
  const after = await firstCard.boundingBox();
  expect(after!.height).toBeCloseTo(before!.height, 0);
  const body = (await requested).postDataJSON();
  expect(body.adults).toBe(2);
  expect(body.travel_class).toBe(1);
  expect(body.departure_date).toBe("2027-06-01");
  expect(body.via[0]).toBe("oslo");
  expect(timetableCalls).toBe(0);
  await expect(dialog.getByLabel("Prepared timetable coverage")).toContainText("outside the prepared rail calendars");
  await dialog.getByText("Feed dates, city coverage & credits", { exact: true }).click();
  await expect(dialog.getByLabel("Prepared timetable coverage")).toContainText("Synthetic Norwegian feed");
  await expect(dialog.getByLabel("Prepared timetable coverage")).toContainText("outside your search date");
  await dialog.getByRole("button", { name: "Search self-hosted timetables", exact: true }).click();
  await expect(dialog.locator(".timetable-journey")).toContainText("Fixture Rail · Test 123");
  await expect(dialog.locator(".timetable-journey")).toContainText("08:00 (Europe/Oslo)");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(firstCard.getByRole("button", { name: "Plan & book this train leg" })).toBeFocused();
  await expect(firstCard.locator(".leg-confidence")).toContainText("1 timetable option(s)");
  await firstCard.getByRole("button", { name: "Plan & book this train leg" }).click();
  await dialog.getByLabel("Travel date", { exact: true }).fill("2027-06-02");
  await expect(dialog.locator(".timetable-journey")).toHaveCount(0);
  expect(timetableCalls).toBe(1);
  await page.getByRole("tab", { name: "Reservations", exact: true }).click();
  await expect(dialog.locator(".booking-status")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Passholder reservations ↗", exact: true })).toBeVisible();
  await dialog.getByLabel("How you’ll travel").selectOption("tickets");
  await expect(dialog.getByRole("link", { name: "Passholder reservations ↗", exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: "Journey notes", exact: true }).click();
  await expect(dialog.getByLabel("Journey details to copy")).toHaveValue(/2 adults · 1st class/);
  await expect(dialog.getByLabel("Journey details to copy")).toHaveValue(/Compare full-price tickets/);
  await page.setViewportSize({ width: 390, height: 844 });
  const modalSize = await dialog.boundingBox();
  expect(modalSize!.width).toBeLessThan(390);
  await dialog.screenshot({ path: "test-results/train-dialog-mobile.png" });
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Adults", { exact: true })).toHaveValue("2");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("link", { name: "Booking data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Self-hosted timetables, separate passholder bookings." })).toBeVisible();
  await expect(page.getByRole("table")).toContainText("Transitland");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("long journeys are advisory and Greece uses a separately booked endpoint ferry", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByLabel("Daily rail limit · hours", { exact: true })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Final region", exact: true }).selectOption("greece");
  await page.getByRole("combobox", { name: "Southern endpoint", exact: true }).selectOption("athens");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.locator(".route-stop-card").last()).toContainText("Athens");
  await expect(page.locator(".journey-overview")).toContainText("no daily cap");
  await expect(page.locator(".journey-overview")).toContainText("night(s) in transit");
  const port = page.locator(".route-stop-card").filter({ has: page.getByRole("heading", { name: "Bari", exact: true }) });
  await expect(port).toContainText("26h 0m estimated ferry + onward transfer to Athens");
  await expect(port.locator(".rail-booking")).toHaveCount(0);
  await port.getByRole("button", { name: "Plan ferry & onward transfer" }).click();
  await expect(page.getByRole("dialog").getByRole("link", { name: "Check ferry sailings & cabins ↗" })).toHaveAttribute("href", "https://www.superfast.com/en-gb");
  await expect(page.getByRole("dialog")).toContainText("Not counted as a rail-pass travel day");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Find an in-between stop", exact: true }).first().click();
  const suggestion = page.getByRole("dialog").locator("button:not([disabled])").filter({ hasText: "Add a stay in" }).first();
  await expect(suggestion).toBeVisible();
  const label = (await suggestion.innerText()).replace("Add a stay in ", "");
  await suggestion.click();
  await expect(page.getByRole("status")).toHaveText("Changes saved and itinerary recalculated.");
  await expect(page.getByRole("spinbutton", { name: `Nights in ${label}`, exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator(".route-stop-card").last()).toContainText("Athens");
  await expect(page.locator(".endpoint-transfer")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("remove a must-see from its stop card with explicit confirmation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await page.getByRole("button", { name: "Remove Prague from route", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("also removes it from the trip’s must-see list");
  await page.getByRole("button", { name: "Keep this stop", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Prague", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remove Prague from route", exact: true }).click();
  await page.getByRole("button", { name: "Remove stay & recalculate", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".selected-stops")).not.toContainText("Prague");
  await expect(page.locator(".route-stop-card").getByRole("heading", { name: "Prague", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".selected-stops")).not.toContainText("Prague");
});

test("Greek island endpoints keep ferry research separate and editable", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("combobox", { name: "Final region", exact: true }).selectOption("islands");
  await page.getByRole("searchbox", { name: "Find a city" }).fill("Naxos");
  await page.locator(".city-search-results button").filter({ hasText: "Naxos" }).click();
  await page.getByRole("button", { name: "Make island final destination", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Southern endpoint", exact: true })).toHaveValue("naxos");
  await page.getByRole("button", { name: "Close map details" }).click();
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await expect(page.locator(".route-stop-card").last()).toContainText("Naxos");
  await expect(page.locator(".endpoint-transfer")).toHaveCount(2);
  await page.getByRole("button", { name: "Plan ferry & onward transfer" }).last().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Piraeus (Athens) → Naxos");
  await expect(dialog).toContainText("not confirmed sailings");
  await dialog.screenshot({ path: "test-results/island-transfer-dialog-desktop.png" });
  await page.keyboard.press("Escape");
  await page.locator(".route-stop-card").last().getByRole("combobox", { name: "Switch final destination", exact: true }).selectOption("capri");
  await expect(page.locator(".route-stop-card").last()).toContainText("Capri");
  await expect(page.locator(".endpoint-transfer")).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".route-stop-card").last()).toContainText("Capri");
});

test("flight home searches are one-way with independent flexible departure dates", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Start date · optional", { exact: true }).fill("2027-06-01");
  await page.getByRole("combobox", { name: "Southern endpoint", exact: true }).selectOption("naples");
  await page.getByRole("button", { name: "Create trip & find routes" }).click();
  await page.getByLabel("Flexible departure dates", { exact: true }).check();
  await page.getByLabel("Latest flight departure", { exact: true }).fill("2027-06-23");
  await page.getByRole("button", { name: "Prepare flight search", exact: true }).click();
  const links = page.getByRole("link", { name: /^One-way ·/ });
  await expect(links).toHaveCount(3);
  const href = await page.getByRole("link", { name: "One-way · 2027-06-22 ↗", exact: true }).getAttribute("href");
  const url = new URL(href!);
  expect(url.searchParams.get("q")).toContain("One way flights from NAP to BGO on 2027-06-22 for 2 adults");
  await expect(page.getByLabel("Check-out", { exact: true })).toHaveValue("2027-06-21");
  await page.getByLabel("Latest flight departure", { exact: true }).fill("2027-06-24");
  await expect(links).toHaveCount(0);
  await page.getByLabel("Flexible departure dates", { exact: true }).uncheck();
  await expect(page.getByLabel("Latest flight departure", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Prepare flight search", exact: true }).click();
  await expect(page.getByRole("link", { name: "Open external search ↗", exact: true })).toBeVisible();
});
