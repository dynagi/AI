import type { Metadata } from "next";
import { IBM_Plex_Mono, Pixelify_Sans, VT323 } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/AuthProvider";

const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-mono", display: "swap" });
const pixel = Pixelify_Sans({ subsets: ["latin"], variable: "--font-pixel", display: "swap" });
const vt = VT323({ subsets: ["latin"], weight: "400", variable: "--font-vt", display: "swap" });

export const metadata: Metadata = {
  title: "FinPilot.exe",
  description: "Your Money. Smarter. An AI personal finance decision-support agent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${mono.variable} ${pixel.variable} ${vt.variable}`}>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
