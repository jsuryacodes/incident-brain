import { Laptop, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePref } from "../lib/theme";

const OPTIONS: { id: ThemePref; label: string; Icon: typeof Sun }[] = [
  { id: "system", label: "System", Icon: Laptop },
  { id: "light", label: "Light", Icon: Sun },
  { id: "dark", label: "Dark", Icon: Moon },
];

/** System / Light / Dark as three buttons, current one marked. Shared by the console header and the landing page.
 *  The choice is written to localStorage by the theme store (which swallows storage errors). */
export function ThemeSwitch({ labels = true }: { labels?: boolean }) {
  const { pref, set } = useTheme();
  return (
    <div role="group" aria-label="Theme" data-testid="theme-switch" className="flex rounded-lg bg-surface-2 p-0.5">
      {OPTIONS.map(({ id, label, Icon }) => (
        <button key={id} onClick={() => set(id)} aria-pressed={pref === id} data-testid={`theme-${id}`} title={label}
          className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-sm ${
            pref === id ? "bg-surface font-medium text-text shadow-sm" : "text-muted hover:text-text"}`}>
          <Icon size={14} aria-hidden />
          <span className={labels ? "hidden lg:inline" : "sr-only"}>{label}</span>
        </button>
      ))}
    </div>
  );
}
