import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import EndpointTransferDetails from "../../components/EndpointTransferDetails";

vi.mock("../../components/Modal", () => ({ default: ({ open, title, children }: { open: boolean; title: string; children: React.ReactNode }) => open ? <div role="dialog" aria-label={title}><h2>{title}</h2>{children}</div> : null }));
afterEach(cleanup);
it("labels the Lefkada bridge approach as ground transport and offers no ferry cabin link", () => {
  render(<EndpointTransferDetails transfers={[{ onward_url: "https://www.visitgreece.gr/", reservation_warning: "Road over the mainland bridge; no ferry on this segment.", components: [{ mode: "ground_transfer", origin: "Igoumenitsa", destination: "Lefkada Town via mainland bridge", estimated_minutes: 180 }] }]} />);
  fireEvent.click(screen.getByRole("button", { name: "Plan onward ground transfer" }));
  expect(screen.getByRole("dialog", { name: "Your onward ground connection" })).toBeTruthy();
  expect(screen.getByText("Your onward ground connection")).toBeTruthy();
  expect(screen.getByText(/Road over the mainland bridge/)).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Check ferry sailings & cabins ↗" })).toBeNull();
});
