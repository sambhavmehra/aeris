'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';

export default function HudAutoNavigator() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const checkHudStatus = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/status');
        if (!res.ok) return;
        const data = await res.json();
        
        const currentHud = data.current_hud; // 'codepipeline', 'repaircenter', 'webweaver', or null
        const activePipelineId = data.active_pipeline_id;

        if (currentHud) {
          const targetPath = `/${currentHud}`;
          // If we are not currently on that HUD page
          if (pathname !== targetPath) {
            sessionStorage.setItem('aeris_auto_redirected', 'true');
            if (activePipelineId) {
              router.push(`${targetPath}?id=${activePipelineId}`);
            } else {
              router.push(targetPath);
            }
          }
        } else {
          // If no active HUD is reported by backend, but the user was auto-redirected here
          if (sessionStorage.getItem('aeris_auto_redirected') === 'true') {
            sessionStorage.removeItem('aeris_auto_redirected');
            // Redirect back to home only if currently viewing one of the HUDs
            if (pathname === '/codepipeline' || pathname === '/repaircenter' || pathname === '/webweaver') {
              router.push('/');
            }
          }
        }
      } catch (e) {
        // ignore connection errors (backend offline / booting)
      }
    };

    checkHudStatus();
    const interval = setInterval(checkHudStatus, 3000);
    return () => clearInterval(interval);
  }, [pathname, router]);

  return null;
}
