import type { Metadata } from "next";
import "./globals.css";
import "./runtime.css";

export const metadata: Metadata = {
  title: "SURAKSH | Federating CCTV",
  description: "Government CCTV federation and intelligence control room"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
