import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ExternalRailTimetables from "../../components/ExternalRailTimetables";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
it("only contacts providers on explicit actions and clears research after date changes", async () => {
  const fetch = vi.fn(async (url: string, options: RequestInit) => {
    const body = JSON.parse(String(options.body));
    if (url.endsWith("/locations")) return json({ status: "ok", locations: [{ uid: body.city_id, name: body.city_id, isMeta: true, countryCode: "IT" }] });
    expect(body).toEqual({ origin_id: "milan", destination_id: "bari", origin_uid: "milan", destination_uid: "bari", departure_date: "2026-10-20" });
    return json({ status: "scheduled", message: "Provider departures", environment: "test", notice: "Research only", checked_at: null, journeys: [{ segments: [{ origin: { name: "Milano Centrale" }, destination: { name: "Bari Centrale" }, operator: { name: "Trenitalia" }, transport: "TRAIN", identifier: "123", departureAt: "2026-10-20T09:00", arrivalAt: "2026-10-20T17:00" }] }] });
  });
  vi.stubGlobal("fetch", fetch);
  const view = render(<ExternalRailTimetables originId="milan" destinationId="bari" date="2026-10-20" />);
  fireEvent.click(screen.getByText("Search additional rail coverage · All Aboard"));
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Find provider cities / stations" }));
  await screen.findByLabelText("Provider origin");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect((screen.getByRole("button", { name: /Search All Aboard/ }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Provider origin"), { target: { value: "milan" } });
  fireEvent.change(screen.getByLabelText("Provider destination"), { target: { value: "bari" } });
  fireEvent.click(screen.getByRole("button", { name: /Search All Aboard/ }));
  await screen.findByText("Milano Centrale → Bari Centrale");
  expect(screen.getByText(/station-local times$/).textContent).toContain("2026-10-20 09:00");
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(screen.queryByRole("button", { name: /Use this departure/ })).toBeNull();
  view.rerender(<ExternalRailTimetables originId="milan" destinationId="bari" date="2026-10-21" />);
  await waitFor(() => expect(screen.queryByText("Milano Centrale → Bari Centrale")).toBeNull());
  expect(fetch).toHaveBeenCalledTimes(3);
});
