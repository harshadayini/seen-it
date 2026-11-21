/**
 * Root layout: loads two families (Bodoni Moda for the oversized wordmark and ghost words,
 * Raleway for headings, body and figures), wraps every screen in the shared run/cart store,
 * and adds the laptop top bar on every page except the landing page, which keeps its bottom tab bar.
 */
import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Bodoni_Moda, Raleway } from "next/font/google";
import { TabBar } from "@/components/TabBar";
import { TopBar } from "@/components/TopBar";
import { RunProvider } from "@/lib/store";

const serif = Bodoni_Moda({ subsets: ["latin"], variable: "--font-serif" });
const sans = Raleway({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = { title: "Seen It", description: "Every video becomes shoppable, with confidence you can trust." };
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#e9e8e1" };

/** @param children the current screen @returns the html shell */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable}`}>
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <RunProvider>
          <div className="app">
            <TopBar />
            {children}
            <TabBar />
          </div>
        </RunProvider>
      </body>
    </html>
  );
}
