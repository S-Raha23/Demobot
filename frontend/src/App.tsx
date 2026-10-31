import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import { Spinner } from "./components/ui";

const Run = lazy(() => import("./pages/Run"));
const TryIt = lazy(() => import("./pages/TryIt"));
const About = lazy(() => import("./pages/About"));

function Loading() {
  return (
    <div className="flex h-full items-center justify-center text-ink-300">
      <Spinner size={22} />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/run/:id" element={<Run />} />
        <Route path="/try" element={<TryIt />} />
        <Route path="/try/:id" element={<TryIt />} />
        <Route path="/costs" element={<About />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </Suspense>
  );
}
