import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5eead4" />
          <stop offset="1" stopColor="#60a5fa" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="#0f1722" stroke="url(#lg)" strokeOpacity="0.5" />
      <circle cx="16" cy="16" r="8.5" fill="none" stroke="url(#lg)" strokeWidth="2.4" strokeDasharray="40 14" strokeLinecap="round" />
      <circle cx="16" cy="16" r="3.2" fill="#60a5fa" />
    </svg>
  );
}

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors ${isActive ? "bg-ink-700/80 text-ink-50" : "text-ink-300 hover:text-ink-100 hover:bg-ink-750"}`;

export function TopNav({ children, center }: { children?: ReactNode; center?: ReactNode }) {
  return (
    <header className="relative z-20 flex h-[52px] shrink-0 items-center gap-4 border-b border-ink-700/70 bg-ink-900/85 px-4 backdrop-blur md:px-5">
      <Link to="/" className="flex items-center gap-2.5">
        <Logo />
        <div className="leading-tight">
          <div className="text-[14.5px] font-semibold tracking-tight text-ink-50">DemoBot</div>
          <div className="text-[10.5px] font-medium text-ink-400 hidden sm:block">Show it once</div>
        </div>
      </Link>
      <nav className="ml-2 hidden items-center gap-1 md:flex">
        <NavLink to="/" end className={link}>
          Library
        </NavLink>
        <NavLink to="/try" className={link}>
          Try it
        </NavLink>
        <NavLink to="/costs" className={link}>
          Costs &amp; About
        </NavLink>
      </nav>
      <div className="hidden min-w-0 flex-1 lg:block">{center}</div>
      <div className="flex-1 lg:hidden" />
      <NavLink to="/try" className={(a) => `${link(a)} md:hidden`}>
        Try it
      </NavLink>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  );
}
