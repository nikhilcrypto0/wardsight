import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { IS_PUBLIC } from "./lib/mode";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "WardSight",
  description: "Clinical documentation integrity on a synthetic ward. Demo, not for clinical use.",
};

const NAV = IS_PUBLIC
  ? [{ href: "/", label: "Ward replay" }]
  : [
      { href: "/replay", label: "Ward replay" },
      { href: "/", label: "CDI worklist" },
      { href: "/inbox", label: "Physician inbox" },
      { href: "/audit", label: "Audit log" },
    ];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <div className="bg-amber-100 text-amber-900 text-xs text-center py-1.5 px-4">
          Synthetic data only. No real patients. Demo, not for clinical use.
        </div>
        <header className="bg-white border-b border-slate-200">
          <div className="mx-auto max-w-7xl px-6 h-14 flex items-center gap-8">
            <Link href="/" className="font-semibold tracking-tight text-slate-900">
              WardSight
            </Link>
            <nav className="flex gap-1 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl px-6 py-8 flex-1">{children}</main>
        {IS_PUBLIC && (
          <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
            Public demo: a replay of precomputed results. The full app (worklist, live rules check, physician
            inbox, audit log) runs locally. Source:{" "}
            <a href="https://github.com/nikhilcrypto0/wardsight" className="text-teal-700 underline">
              github.com/nikhilcrypto0/wardsight
            </a>
          </footer>
        )}
      </body>
    </html>
  );
}
