// A small inline icon set (1.6px strokes on a 20px grid), so the dashboard
// needs no icon library.

const PATHS = {
  compass: "M10 2.5a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15Zm3.2 4.3-1.7 4.7-4.7 1.7 1.7-4.7 4.7-1.7Z",
  box: "M3.5 6.5 10 3l6.5 3.5v7L10 17l-6.5-3.5v-7Zm0 0L10 10m0 0 6.5-3.5M10 10v7",
  ledger: "M5 3h9.5a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5V3Zm0 0v14M8 7h5M8 10h5M8 13h3",
  building: "M4 17V4.5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1V17m0-8h3a1 1 0 0 1 1 1v7M3 17h14M7 7h2M7 10h2M7 13h2",
  chat: "M3.5 5a1.5 1.5 0 0 1 1.5-1.5h10A1.5 1.5 0 0 1 16.5 5v7a1.5 1.5 0 0 1-1.5 1.5H8l-3.5 3v-3H5A1.5 1.5 0 0 1 3.5 12V5Zm3.5 3h6M7 10.5h4",
  user: "M10 10a3.25 3.25 0 1 0 0-6.5A3.25 3.25 0 0 0 10 10Zm-5.5 7a5.5 5.5 0 0 1 11 0",
  desk: "M3 8h14M4.5 8v8.5M15.5 8v8.5M6.5 4.5h7V8h-7z",
  play: "M6.5 4.5v11l9-5.5-9-5.5Z",
  ticket: "M3 6.5a1.5 1.5 0 0 0 0 3v4A1.5 1.5 0 0 0 4.5 15h11a1.5 1.5 0 0 0 1.5-1.5v-4a1.5 1.5 0 0 1 0-3v-1A1.5 1.5 0 0 0 15.5 5h-11A1.5 1.5 0 0 0 3 6.5Zm9-1.5v10",
  flag: "M5 17V3.5m0 0h9l-2 3.5 2 3.5H5",
  search: "M9 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12Zm4.5-1.5L17 17",
  wrench: "M12.5 3.2a4 4 0 0 0-4.6 5.4L3.5 13a1.8 1.8 0 0 0 2.5 2.5l4.4-4.4a4 4 0 0 0 5.4-4.6l-2.4 2.4-2.3-.6-.6-2.3 2.4-2.4Z",
  alert: "M10 3 2.5 16.5h15L10 3Zm0 5.5v3.5m0 2.2v.3",
  arrow: "M3.5 10h12m0 0-4-4m4 4-4 4",
  return: "M16 10H5m0 0 4-4m-4 4 4 4",
  stop: "M10 17.5a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15ZM4.7 4.7l10.6 10.6",
  shield: "M10 2.8 4 5v4.6c0 3.6 2.6 6.4 6 7.6 3.4-1.2 6-4 6-7.6V5l-6-2.2Zm-2.5 7.4 1.8 1.8 3.4-3.6",
  refresh: "M16 10a6 6 0 1 1-1.8-4.3M16 3.5v3.2h-3.2",
  check: "M4 10.5 8 14.5 16 6",
  file: "M5.5 2.5h6l3.5 3.5v11.5h-9.5v-15Zm6 0V6h3.5M8 10h5M8 13h5",
  coin: "M10 17.5a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Zm2.3-10a2.6 2.6 0 0 0-2.3-1c-1.4 0-2.4.7-2.4 1.8 0 2.6 4.9 1.4 4.9 4 0 1.1-1.1 1.9-2.5 1.9-1.1 0-2-.4-2.5-1.1M10 5v1.5m0 7.5v1.5",
  gavel: "M8.5 3.5l5 5M7 5l5 5m-6.5 1.5 4-4m-6 9h7M11 7.5 6 12.5",
  spark: "M10 2.5v4m0 7v4m-7.5-7.5h4m7 0h4M4.7 4.7l2.8 2.8m5 5 2.8 2.8m0-10.6-2.8 2.8m-5 5-2.8 2.8",
  dot: "M10 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z",
  clock: "M10 17.5a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15ZM10 6v4.2l2.8 1.8",
  chevron: "M6 8l4 4 4-4",
  plug: "M7 2.5V6m6-3.5V6M5 6h10v3a5 5 0 0 1-10 0V6Zm5 8v3.5",
  wallet: "M3.5 6.5h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-12V6.5Zm0 0V5a1.5 1.5 0 0 1 1.5-1.5h9M13 12h3.5",
  lock: "M5.5 9h9v8h-9V9Zm1.8 0V6.5a2.7 2.7 0 0 1 5.4 0V9",
  x: "M5 5l10 10M15 5 5 15",
  cart: "M3 4h2l1.6 8.5h8.4l1.5-6H6",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 16,
  className,
  title,
}: {
  name: IconName;
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
