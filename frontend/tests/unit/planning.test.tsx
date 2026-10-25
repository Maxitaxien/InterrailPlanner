import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Home from "../../app/page";
import TravelPanel from "../../components/TravelPanel";
import RailTimetables from "../../components/RailTimetables";
import { useEditorStore } from "../../lib/editor-store";
vi.mock("../../components/RouteMap", () => ({ default: () => <div>Route map</div> }));
const destinations = [{ id: "prague", name: "Prague", country_code: "CZ", is_endpoint: false }, { id: "venice", name: "Venice", country_code: "IT", is_endpoint: false }, { id: "naples", name: "Naples", country_code: "IT", is_endpoint: true }];
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
function mount(element: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}
beforeEach(() => { localStorage.clear(); useEditorStore.setState({ active: 0 }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe("planning form", () => {
  it("saves the recovery token before an infeasible generation and retries the same trip", async () => {
    let creates = 0, generations = 0, updates = 0;
    const fetch = vi.fn(async (url: string, options?: RequestInit) => {
      if (url === "/api/rail-network") return json([]);
      if (url === "/api/destinations") return json(destinations);
      if (url === "/api/trips") {
        creates++;
        const request = JSON.parse(String(options?.body));
        expect(request.required_stops).toEqual(["prague", "venice"]);
        expect(request.total_days).toBe(21);
        expect(request.pass.travel_days_total).toBe(7);
        return json({ id: "saved-trip", revision: 1, edit_token: "private-token" }, 201);
      }
      if (url === "/api/trips/saved-trip" && options?.method === "PATCH") {
        updates++;
        const request = JSON.parse(String(options.body));
        expect(request.required_stops).toEqual(["prague"]);
        expect(request.pass.travel_days_total).toBe(15);
        expect(request.expected_revision).toBe(updates);
        return json({ revision: updates + 1 });
      }
      if (url === "/api/trips/saved-trip/generate") {
        generations++;
        expect((options?.headers as Record<string,string>)["X-Edit-Token"]).toBe("private-token");
        return json({ error: { code: "PASS_LIMIT_EXCEEDED", message: "The pass has too few travel days." } }, 422);
      }
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    mount(<Home />);
    const create = screen.getByRole("button", { name: /Create trip & find routes/ });
    await waitFor(() => expect((create as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(create);
    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain("too few travel days");
    expect(JSON.parse(localStorage.getItem("interrail:last-trip")!)).toEqual({ id: "saved-trip", token: "private-token" });
    fireEvent.click(screen.getByRole("button", { name: "Remove Venice from must-see stops" }));
    fireEvent.change(screen.getByLabelText("Total travel days"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry generation for saved trip" }));
    await waitFor(() => expect(generations).toBe(2));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Retry generation for saved trip" }));
    await waitFor(() => expect(generations).toBe(3));
    expect(updates).toBe(2);
    expect(creates).toBe(1);
  });
  it("keeps API failures visible and lets the user retry destinations", async () => {
    let requests = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => { if (url === "/api/rail-network") return json([]); requests++; return requests === 1 ? json({ error: { message: "Backend unavailable" } }, 503) : json(destinations); }));
    mount(<Home />);
    expect((await screen.findByRole("alert")).textContent).toContain("Backend unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));
    await waitFor(() => expect((screen.getByRole("button", { name: /Create trip & find routes/ }) as HTMLButtonElement).disabled).toBe(false));
    expect(requests).toBe(2);
  });
});
it("labels external searches and removes the old search link when dates change", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({ provider: "external-search", status: "link_only", search_url: "https://www.google.com/travel/flights?q=NAP-BGO", currency: "NOK", notice: "No availability has been checked." })));
  mount(<TravelPanel endpoint={{ destination_id: "naples", name: "Naples", arrival_date: "2027-06-17", arrival_day: 16, departure_day: 20 }} airport="NAP" returnDate="2027-06-21" />);
  fireEvent.click(screen.getByRole("button", { name: "Prepare flight search" }));
  const link = await screen.findByRole("link", { name: /Open external search/ });
  expect(link.getAttribute("href")).toContain("google.com/travel/flights");
  expect(screen.getByText(/No live offers retrieved/)).toBeDefined();
  fireEvent.change(screen.getByLabelText("Flight departure"), { target: { value: "2027-06-22" } });
  expect(screen.queryByRole("link", { name: /Open external search/ })).toBeNull();
});

it("prepares a flexible one-way departure range without changing hotel dates", async () => {
  const fetch = vi.fn(async (_url: string, options?: RequestInit) => {
    expect(JSON.parse(String(options?.body))).toMatchObject({ origin_airport: "NAP", trip_type: "one_way", departure_date: "2027-06-21", departure_date_end: "2027-06-23", adults: 2 });
    return json({ provider: "external-search", status: "link_only", search_url: "https://www.google.com/travel/flights?q=one+way", currency: "NOK", notice: "No availability checked", search_links: ["2027-06-21", "2027-06-22", "2027-06-23"].map(day => ({ departure_date: day, search_url: `https://www.google.com/travel/flights?q=one+way+${day}` })) });
  });
  vi.stubGlobal("fetch", fetch);
  mount(<TravelPanel endpoint={{ destination_id: "naples", name: "Naples", arrival_date: "2027-06-17", arrival_day: 16, departure_day: 20 }} airport="NAP" returnDate="2027-06-21" />);
  fireEvent.click(screen.getByLabelText("Flexible departure dates"));
  fireEvent.change(screen.getByLabelText("Latest flight departure"), { target: { value: "2027-06-23" } });
  fireEvent.click(screen.getByRole("button", { name: "Prepare flight search" }));
  expect(await screen.findByRole("link", { name: "One-way · 2027-06-22 ↗" })).toBeDefined();
  expect((screen.getByLabelText("Check-out") as HTMLInputElement).value).toBe("2027-06-21");
  fireEvent.change(screen.getByLabelText("Latest flight departure"), { target: { value: "2027-06-24" } });
  expect(screen.queryByRole("link", { name: "One-way · 2027-06-22 ↗" })).toBeNull();
});

it("shows prepared coverage warnings without searching or disabling timetable research", async () => {
  let timetableCalls = 0;
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === "/api/travel/rail/coverage") {
      expect(JSON.parse(String(options?.body))).toMatchObject({ origin_id: "oslo", destination_id: "bergen", departure_date: "2027-06-01" });
      return json({ status: "outside_prepared_dates", message: "Your date is outside every prepared rail calendar envelope.", notice: "Prepared metadata only, not import verification.", sources: [] });
    }
    if (url === "/api/travel/rail/timetables") {
      timetableCalls++;
      return json({ status: "no_journeys", message: "No journeys in this fixture", journeys: [], prepared_sources: [], notice: "Not a booking", checked_at: null });
    }
    throw new Error(`Unexpected URL ${url}`);
  });
  vi.stubGlobal("fetch", fetch);
  mount(<RailTimetables originId="oslo" destinationId="bergen" date="2027-06-01" />);
  expect(await screen.findByText("Your date is outside every prepared rail calendar envelope.")).toBeDefined();
  expect(timetableCalls).toBe(0);
  const search = screen.getByRole("button", { name: "Search self-hosted timetables" });
  expect((search as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(search);
  expect(await screen.findByText("No journeys in this fixture")).toBeDefined();
  expect(timetableCalls).toBe(1);
});

it("only applies a returned journey after an explicit selection", async () => {
  const choose = vi.fn(async () => {});
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url.endsWith("/coverage")
    ? json({ status: "no_metadata", message: "Synthetic coverage", notice: "Fixture only", sources: [] })
    : json({ status: "scheduled", message: "Synthetic journey", notice: "Not a booking", checked_at: null, prepared_sources: [], journeys: [{ selection_id: "synthetic-server-id", departure: "2027-06-01T20:00:00Z", arrival: "2027-06-02T04:00:00Z", duration_minutes: 480, transfers: 0, legs: [] }] })));
  mount(<RailTimetables originId="oslo" destinationId="prague" date="2027-06-01" onChoose={choose} />);
  expect(choose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Search self-hosted timetables" }));
  const button = await screen.findByRole("button", { name: "Use this departure in itinerary" });
  expect(choose).not.toHaveBeenCalled();
  fireEvent.click(button);
  await waitFor(() => expect(choose).toHaveBeenCalledWith("synthetic-server-id"));
});
