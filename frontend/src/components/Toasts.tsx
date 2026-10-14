import { X } from "lucide-react";
import { useApp } from "../lib/store";

export function Toasts() {
  const { toasts, dismiss } = useApp();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,380px)] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} role={t.kind === "error" ? "alert" : "status"}
          className={`card pointer-events-auto flex items-start gap-3 p-3 text-sm fade-in ${t.kind === "error" ? "border-alert/50" : ""}`}>
          <p className="flex-1">{t.text}</p>
          {t.retry && (
            <button className="font-medium text-accent" onClick={() => (dismiss(t.id), t.retry!())}>Retry</button>
          )}
          <button aria-label="Dismiss" className="text-muted hover:text-text" onClick={() => dismiss(t.id)}><X size={15} /></button>
        </div>
      ))}
    </div>
  );
}
