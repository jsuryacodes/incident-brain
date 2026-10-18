import { lazy, Suspense, useEffect } from "react";
import { Header } from "./components/Header";
import { Toasts } from "./components/Toasts";
import { Skeleton } from "./components/ui";
import { useApp } from "./lib/store";
import { StoryView } from "./views/StoryView";

const BrainView = lazy(() => import("./views/BrainView"));
const ExplorerView = lazy(() => import("./views/ExplorerView"));
const FirefighterView = lazy(() => import("./views/FirefighterView"));
const EvalView = lazy(() => import("./views/EvalView"));
const LandingView = lazy(() => import("./views/LandingView"));
const TITLES = { landing: "Incident Brain", story: "Story", firefighter: "Firefighter", eval: "Eval", brain: "Ask the Brain", explorer: "Explorer" };

export function App() {
  const { view, meta, tenant, loadMeta } = useApp();
  const landing = view === "landing";
  useEffect(() => {
    if (!landing) void loadMeta(); // the landing page needs no API
  }, [landing, loadMeta]);
  useEffect(() => {
    document.title = view === "landing" ? "Incident Brain — find out why, and show the work" : `${TITLES[view]} · Incident Brain`;
  }, [view]);
  if (landing)
    return (
      <Suspense fallback={<div className="p-6"><Skeleton className="h-64" /></div>}>
        <LandingView />
        <style>{"html, body, #root { height: auto; min-height: 100%; }"}</style>
      </Suspense>
    );
  return (
    <div className="flex h-full flex-col">
      <Header />
      <main className="min-h-0 flex-1">
        {!meta || !tenant ? (
          <div className="grid h-full grid-cols-1 gap-3 p-3 lg:grid-cols-[300px_1fr_380px]">
            <Skeleton className="h-full min-h-40" /><Skeleton className="h-full min-h-64" /><Skeleton className="h-full min-h-40" />
          </div>
        ) : (
          <Suspense fallback={<div className="p-4"><Skeleton className="h-64" /></div>}>
            {view === "story" && <StoryView key={tenant} />}
            {view === "firefighter" && <FirefighterView key={tenant} />}
            {view === "eval" && <EvalView />}
            {view === "brain" && <BrainView key={tenant} />}
            {view === "explorer" && <ExplorerView key={tenant} />}
          </Suspense>
        )}
      </main>
      <Toasts />
    </div>
  );
}
