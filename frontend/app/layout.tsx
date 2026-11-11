import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DUKAANTRA | Retail Business Intelligence",
  description:
    "An intelligent business workspace for India's local retailers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}