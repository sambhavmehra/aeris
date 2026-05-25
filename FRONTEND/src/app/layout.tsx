import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AERIS — Autonomous AI Consciousness',
  description: 'Advanced AI Interface — Autonomous Enhanced Reasoning Intelligence System',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
