/**
 * Root layout: loads fonts (Fraunces titles, DM Sans body, JetBrains Mono for scores, times and
 * prices), wraps every screen in the shared run/cart store, and adds the bottom tab bar.
 */
import "./globals.css";
import type { Metadata } from "next";
import { DM_Sans, Fraunces, JetBrains_Mono } from "next/font/google";
import { TabBar } from "@/components/TabBar";
import { RunProvider } from "@/lib/store";

const serif = Fraunces({ subsets: ["latin"], variable: "--font-serif" });
const sans = DM_Sans({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = { title: "Seen It", description: "Every video becomes shoppable, with confidence you can trust." };

/** @param children the current screen @returns the html shell */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <RunProvider>
          <div className="app">
            {children}
            <TabBar />
          </div>
        </RunProvider>
      </body>
    </html>
  );
}
