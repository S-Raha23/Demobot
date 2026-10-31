import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import { Spinner } from "./components/ui";

const Run = lazy(() => import("./pages/Run"));
const TryIt = lazy(() => import("./pages/TryIt"));
const About = lazy(() => import("./pages/About"));

function Loading() {
  return (
    <main id="main-content" className="flex h-full items-center justify-center text-ink-300">
      <Spinner size={22} />
    </main>
  );
}

function NotFound() {
  return (
    <main id="main-content" className="flex h-full items-center justify-center p-6">
      <div className="panel max-w-sm p-6 text-center">
        <div className="text-[16px] font-semibold text-ink-50">Page not found</div>
        <p className="mt-1 text-[12.5px] text-ink-400">That page does not exist.</p>
        <Link to="/" className="btn btn-primary mt-4 justify-center">
          Back to Library
        </Link>
      </div>
    </main>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-ink-800 focus:px-4 focus:py-2 focus:text-[13px] focus:font-semibold focus:text-ink-50 focus:ring-1 focus:ring-sparkopen"
      >
        Skip to content
      </a>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/run/:id" element={<Run />} />
        <Route path="/try" element={<TryIt />} />
        <Route path="/try/:id" element={<TryIt />} />
        <Route path="/costs" element={<About />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
