import type { Metadata } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import { Providers } from "./providers";
export const metadata: Metadata = { title: "Our Honeymoon by Rail · Interrail Helper", description: "Plan a honeymoon from Oslo to southern Europe, with beautiful stops, slow days and train booking guidance for two." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Providers>{children}</Providers></body></html>;
}
