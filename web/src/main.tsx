import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Navigator from "./navigator/Navigator";
import { ActivityBar } from "./components/ActivityBar";
import { installActivityTracking } from "./lib/activity";
import "./styles.css";
import "./ui/kit.css";

installActivityTracking();

const Lab = lazy(() => import("./lab/Lab"));
const MapView = lazy(() => import("./map/MapView"));
const JourneyTunnel = lazy(() => import("./journey/JourneyTunnel"));
const Phone = lazy(() => import("./companion/PhoneCompanion").then(m=>({default:m.PhoneCompanion})));

// Page zoom is never intended in this app (the 3D view has its own zoom), and doing it by accident breaks the layout.
addEventListener("wheel", e => { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && ["+", "-", "=", "0", "_"].includes(e.key)) e.preventDefault(); });
for (const name of ["gesturestart", "gesturechange", "gestureend"]) addEventListener(name, e => e.preventDefault());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary><BrowserRouter>
      <ActivityBar />
      <Routes>
        <Route path="/map" element={<Suspense fallback={null}><MapView /></Suspense>} />
        <Route path="/tunnel" element={<Suspense fallback={null}><JourneyTunnel /></Suspense>} />
        <Route path="/" element={<Navigator />} />
        <Route path="/phone" element={<Suspense fallback={null}><Phone /></Suspense>} />
        <Route path="/lab/*" element={<Suspense fallback={null}><Lab /></Suspense>} />
      </Routes>
    </BrowserRouter></ErrorBoundary>
  </StrictMode>,
);
