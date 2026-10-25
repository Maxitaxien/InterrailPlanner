import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import EndpointComparison from "../../components/EndpointComparison";
import ConnectionCheck from "../../components/ConnectionCheck";
import TravelPanel from "../../components/TravelPanel";
import { ConnectionPlan } from "../../lib/connection-types";

vi.mock("../../components/Modal", () => ({ default: ({ open, title, children }: { open: boolean; title: string; children: React.ReactNode }) => open ? <div role="dialog" aria-label={title}>{children}</div> : null }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
const destinations = [
  { id: "bari", name: "Bari", country_code: "IT", is_endpoint: true, latitude: 0, longitude: 0 },
  { id: "corfu", name: "Corfu", country_code: "GR", is_endpoint: true, latitude: 0, longitude: 0 },
  { id: "crete", name: "Crete", country_code: "GR", is_endpoint: true, latitude: 0, longitude: 0 },
];
const airport = { airport: "NAP", name: "Naples", route: "Ferry to Naples + airport transfer", estimated_minutes: 240, ferry_crossings: 1, status: "illustrative_candidate", notice: "Flights unverified" };
const plan: ConnectionPlan = { steps: [{ kind: "port_access", label: "Station to port", estimated_minutes: 45 }, { kind: "check_in", label: "Ferry check-in", estimated_minutes: 90 }], before_departure_minutes: 135, after_arrival_minutes: 45, ferry_count: 1, overnight_nights: 1, arrival_time_status: "unknown", notice: "Planning allowance", arrival_notes: [] };

it("only compares on request, clears stale results, and applies an endpoint explicitly", async () => {
  const choose = vi.fn(async () => true);
  const fetch = vi.fn(async () => json({ origin_name: "Bari", notice: "Local estimates", comparisons: [{ endpoint_id: "crete", name: "Crete", status: "modeled", selectable: true, estimated_minutes: 2400, ferry_crossings: 2, onward_ground_legs: 1, transit_nights_lower_bound: 2, burden: "Longer journey", airport_access: airport }] }));
  vi.stubGlobal("fetch", fetch);
  render(<EndpointComparison destinations={destinations} onChoose={choose} />);
  fireEvent.click(screen.getByRole("button", { name: "Compare final destinations" }));
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Compare selected stays" }));
  await screen.findByText("40h");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(choose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox", { name: /Corfu/ }));
  expect(screen.queryByText("40h")).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Compare selected stays" }));
  await screen.findByText("40h");
  fireEvent.click(screen.getByRole("button", { name: "Choose Crete" }));
  await waitFor(() => expect(choose).toHaveBeenCalledWith("crete"));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("failed endpoint application keeps comparison and the constraint error visible", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({ origin_name: "Bari", notice: "Local estimates", comparisons: [{ endpoint_id: "crete", name: "Crete", status: "modeled", selectable: true, estimated_minutes: 2400, airport_access: airport }] })));
  render(<EndpointComparison destinations={destinations} onChoose={async () => false} />);
  fireEvent.click(screen.getByRole("button", { name: "Compare final destinations" }));
  fireEvent.click(screen.getByRole("button", { name: "Compare selected stays" }));
  fireEvent.click(await screen.findByRole("button", { name: "Choose Crete" }));
  expect((await screen.findByRole("alert")).textContent).toContain("constraints");
  expect(screen.getByRole("dialog")).toBeTruthy();
});

it("checks explicit local times and clears the result when any assumption changes", async () => {
  const fetch = vi.fn(async (_url: string, options: RequestInit) => {
    const body = JSON.parse(String(options.body));
    expect(body.ferry_departure).toBe("2027-06-10T22:00");
    expect(body.ferry_check_in_minutes).toBe(90);
    expect(body.port_access_minutes).toBe(45);
    return json({ status: "insufficient_margin", latest_arrival_at_start: "2027-06-10T19:45:00+02:00", ready_at_destination: "2027-06-11T06:45:00+03:00", origin_timezone: "Europe/Rome", destination_timezone: "Europe/Athens", before_margin_minutes: -15, onward_margin_minutes: null, arrival_day_change: 1, warnings: ["Consider an extra overnight stay"], notice: "Research only" });
  });
  vi.stubGlobal("fetch", fetch);
  render(<ConnectionCheck connectionId="bari-corfu-ferry-transfer" plan={plan} />);
  fireEvent.click(screen.getByText("Check researched connection times"));
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Ferry departure · port local time"), { target: { value: "2027-06-10T22:00" } });
  fireEvent.change(screen.getByLabelText("Ferry arrival · port local time"), { target: { value: "2027-06-11T06:00" } });
  fireEvent.submit(screen.getByRole("button", { name: "Calculate connection margins" }).closest("form")!);
  await screen.findByText("These times leave too little margin");
  expect(screen.getByText(/Consider an extra overnight/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Ferry check-in / boarding allowance · minutes"), { target: { value: "180" } });
  expect(screen.queryByText("These times leave too little margin")).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("candidate airport does not silently become a flight departure", async () => {
  const fetch = vi.fn(async () => json({}));
  vi.stubGlobal("fetch", fetch);
  render(<TravelPanel endpoint={{ destination_id: "capri", name: "Capri", arrival_date: null, departure_day: 20, arrival_day: 16 }} airport={null} returnDate={null} airportAccess={airport} />);
  expect((screen.getByLabelText("Departure airport · IATA") as HTMLInputElement).value).toBe("");
  expect((screen.getByRole("button", { name: "Prepare flight search" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Research flights from NAP" }));
  expect((screen.getByLabelText("Departure airport · IATA") as HTMLInputElement).value).toBe("NAP");
  expect(fetch).not.toHaveBeenCalled();
});
