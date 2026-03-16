import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OPSFoundry Operations Console",
  description: "Exception-driven invoice autoposting dashboard with automatic validation routing.",
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
