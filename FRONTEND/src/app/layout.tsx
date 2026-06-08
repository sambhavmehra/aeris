import type { Metadata } from 'next';
import './globals.css';
import HudAutoNavigator from '@/components/HudAutoNavigator';

export const metadata: Metadata = {
  title: 'AERIS — Autonomous AI Consciousness',
  description: 'Advanced AI Interface — Autonomous Enhanced Reasoning Intelligence System',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <HudAutoNavigator />
        {children}
      </body>
    </html>
  );
}
