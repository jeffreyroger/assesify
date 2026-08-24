import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Assesify",
  description: "Gamified Learning Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        suppressHydrationWarning={true}
        className="antialiased font-nunito bg-surface-light text-surface-dark dark:bg-surface-dark dark:text-surface-light"
      >
        {children}
      </body>
    </html>
  );
}
