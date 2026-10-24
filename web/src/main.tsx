import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Navigator from "./navigator/Navigator";
import "./styles.css";

const Lab = lazy(() => import("./lab/Lab"));
const Phone = lazy(() => import("./companion/PhoneCompanion").then(m=>({default:m.PhoneCompanion})));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary><BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigator />} />
        <Route path="/phone" element={<Suspense fallback={null}><Phone /></Suspense>} />
        <Route path="/lab/*" element={<Suspense fallback={null}><Lab /></Suspense>} />
      </Routes>
    </BrowserRouter></ErrorBoundary>
  </StrictMode>,
);
