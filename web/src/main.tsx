import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Navigator from "./navigator/Navigator";
import "./styles.css";

const Lab = lazy(() => import("./lab/Lab"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary><BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigator />} />
        <Route path="/lab/*" element={<Suspense fallback={null}><Lab /></Suspense>} />
      </Routes>
    </BrowserRouter></ErrorBoundary>
  </StrictMode>,
);
