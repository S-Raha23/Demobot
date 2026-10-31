// A small inline icon set (stroke icons, 24-unit grid).
const P: Record<string, string> = {
  play: "M7 4.5v15l12-7.5z",
  pause: "M7 4h3.5v16H7zM13.5 4H17v16h-3.5z",
  skip: "M5 5l9 7-9 7zM16 5h3v14h-3z",
  check: "M4.5 12.5l5 5L19.5 7",
  x: "M6 6l12 12M18 6L6 18",
  mic: "M12 3a3 3 0 013 3v6a3 3 0 01-6 0V6a3 3 0 013-3zM5.5 11a6.5 6.5 0 0013 0M12 17.5V21",
  clock: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2",
  bolt: "M13 2L4.5 13.5H12L11 22l8.5-11.5H12z",
  code: "M8.5 7L3.5 12l5 5M15.5 7l5 5-5 5",
  cube: "M12 2.5l8.5 4.75v9.5L12 21.5l-8.5-4.75v-9.5zM12 12l8.5-4.75M12 12v9.5M12 12L3.5 7.25",
  video: "M3.5 6.5h12v11h-12zM15.5 10.5l5-3v9l-5-3z",
  eye: "M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12s-3.5 6.5-9.5 6.5S2.5 12 2.5 12zM12 9.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5z",
  shield: "M12 2.5l8 3v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10v-6z",
  shuffle: "M3 7h4l10 10h4M3 17h4l3-3M14 10l3-3h4M18 4l3 3-3 3M18 14l3 3-3 3",
  reset: "M4 12a8 8 0 108-8H7M7 4L4 7l3 3",
  arrow: "M5 12h14M13 6l6 6-6 6",
  back: "M19 12H5M11 6l-6 6 6 6",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v4h16v-4",
  dollar: "M12 2v20M17 6.5c-1-1.5-2.8-2-5-2-2.8 0-4.5 1.3-4.5 3.4 0 4.6 10 2.3 10 7 0 2.1-1.8 3.6-5 3.6-2.4 0-4.4-.8-5.5-2.5",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  camera: "M4 7.5h3l1.5-2h7l1.5 2h3v11H4zM12 10a3.2 3.2 0 100 6.4 3.2 3.2 0 000-6.4z",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  target: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7.5a4.5 4.5 0 100 9 4.5 4.5 0 000-9zM12 11a1 1 0 100 2 1 1 0 000-2z",
  tool: "M14.5 6.5a4 4 0 00-5.4 5.1L3.5 17.2l3.3 3.3 5.6-5.6a4 4 0 005.1-5.4l-2.6 2.6-2.4-.5-.5-2.4z",
  brain: "M9 4a3 3 0 00-3 3 3 3 0 00-2 5 3 3 0 002 5 3 3 0 003 3h1V4zM15 4a3 3 0 013 3 3 3 0 012 5 3 3 0 01-2 5 3 3 0 01-3 3h-1V4z",
  file: "M6 3h8l4 4v14H6zM14 3v4h4",
  alert: "M12 3l9.5 17h-19zM12 10v4.5M12 17.5v.5",
  chat: "M4 5h16v11H9l-5 4z",
  rotate: "M20 12a8 8 0 11-2.3-5.6M20 4v5h-5",
  hand: "M8 13V5.5a1.5 1.5 0 013 0V12M11 11V4.5a1.5 1.5 0 013 0V12M14 11.5V6a1.5 1.5 0 013 0v8c0 4-2.5 7-6.5 7S5 18 4 15.5l-1-3a1.5 1.5 0 012.8-1L8 14",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16",
  info: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v5.5M12 7.5v.5",
};

export function Icon({ name, size = 16, className = "", fill = false }: { name: keyof typeof P | string; size?: number; className?: string; fill?: boolean }) {
  const d = P[name] ?? P.info;
  const filled = fill || name === "play" || name === "pause" || name === "skip";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={d} />
    </svg>
  );
}
