import { API_URL } from "./api";

export type RuntimeAlert = {
  id: string; detection_id: string; watchlist_entry_id: string; priority: string;
  status: string; created_at: string; plate_text: string | null; camera_id: string;
  camera_name: string; department: string; source_system: string; district: string;
  location: string; detected_at: string; vehicle_confidence: number;
  plate_confidence: number | null; is_demo: boolean;
};

export async function subscribeAlerts(token: string, signal: AbortSignal,
  onAlert: (alert: RuntimeAlert) => void, onState: (state: string) => void, onReady?: () => void) {
  let cursor = "";
  while (!signal.aborted) {
    try {
      const response = await fetch(`${API_URL}/alerts/stream${cursor ? `?after=${encodeURIComponent(cursor)}` : ""}`, {
        headers: { Authorization: `Bearer ${token}` }, signal
      });
      if (!response.ok || !response.body) throw new Error(`Alert stream HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!signal.aborted) {
          const { done, value } = await reader.read();
          if (done) throw new Error("Alert connection closed");
          buffer += decoder.decode(value, { stream: true });
          let end: number;
          while ((end = buffer.indexOf("\n\n")) !== -1) {
            const message = buffer.slice(0, end); buffer = buffer.slice(end + 2);
            const lines = message.split("\n");
            const type = lines.find(l => l.startsWith("event: "))?.slice(7);
            if (type === "ready") { onState("CONNECTED"); onReady?.(); }
            if (type === "alert") {
              const data = lines.filter(l => l.startsWith("data: ")).map(l => l.slice(6)).join("\n");
              const alert = JSON.parse(data) as RuntimeAlert;
              cursor = alert.id; onAlert(alert);
            }
          }
        }
      } finally { await reader.cancel().catch(() => {}); }
    } catch (error) {
      if (signal.aborted) return;
      onState(`DISCONNECTED: ${error instanceof Error ? error.message : "connection failed"}; retrying`);
      await new Promise<void>(resolve => {
        const stop = () => { clearTimeout(timer); resolve(); };
        const timer = setTimeout(() => { signal.removeEventListener("abort", stop); resolve(); }, 2000);
        signal.addEventListener("abort", stop, { once: true });
      });
    }
  }
}
