import type { SVGProps } from "react";

const base: SVGProps<SVGSVGElement> = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

export const CheckIcon = () => (
  <svg {...base}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);
export const CopyIcon = () => (
  <svg {...base}>
    <rect x="9" y="9" width="11" height="11" rx="2.5" />
    <path d="M5 15V6.5A1.5 1.5 0 0 1 6.5 5H15" />
  </svg>
);
export const SendIcon = () => (
  <svg {...base}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
export const AlertIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5v5.5M12 16.5v.01" />
  </svg>
);
export const InfoIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5.5M12 7.5v.01" />
  </svg>
);
export const CrownIcon = () => (
  <svg {...base} width={14} height={14}>
    <path d="m4 17 1.5-9 4.5 4 2-6 2 6 4.5-4L20 17z" />
  </svg>
);
export const RefreshIcon = () => (
  <svg {...base}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" />
  </svg>
);
export const BeeMark = () => (
  <svg viewBox="0 0 32 32" width={28} height={28} aria-hidden="true">
    <ellipse cx="16" cy="19" rx="9" ry="8" fill="var(--honey)" />
    <path
      d="M9 17.5q7 2 14 0M8.6 21.5q7.4 2.2 14.8 0"
      stroke="var(--honey-ink)"
      strokeWidth="2.2"
      fill="none"
      strokeLinecap="round"
    />
    <ellipse
      cx="11.5"
      cy="9.5"
      rx="4.2"
      ry="5.2"
      fill="var(--accent-soft)"
      stroke="var(--accent)"
      strokeWidth="1.4"
      transform="rotate(-18 11.5 9.5)"
    />
    <ellipse
      cx="20.5"
      cy="9.5"
      rx="4.2"
      ry="5.2"
      fill="var(--accent-soft)"
      stroke="var(--accent)"
      strokeWidth="1.4"
      transform="rotate(18 20.5 9.5)"
    />
  </svg>
);
export const ChevronIcon = () => (
  <svg
    {...base}
    className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-muted"
  >
    <path d="m6 9 6 6 6-6" />
  </svg>
);
