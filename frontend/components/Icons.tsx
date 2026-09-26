/* One authored icon set: 24-unit grid, 1.6 stroke, round caps and joins.
   Drawn rather than pulled from a library so the weight matches the type. */

type Props = { className?: string };

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const Check = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

export const Alert = ({ className }: Props) => (
  <svg {...base} className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5v5.5M12 16.5h.01" />
  </svg>
);

export const Search = ({ className }: Props) => (
  <svg {...base} className={className}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4.5 4.5" />
  </svg>
);

export const Route = ({ className }: Props) => (
  <svg {...base} className={className}>
    <circle cx="6" cy="18" r="2.5" />
    <circle cx="18" cy="6" r="2.5" />
    <path d="M8.5 18h5a4 4 0 0 0 4-4V8.5" />
  </svg>
);

export const Pen = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M4 20h4L19 9a2.5 2.5 0 0 0-3.5-3.5L4.5 16.5 4 20Z" />
  </svg>
);

export const Doc = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M14 3H7a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 7 21h10a1.5 1.5 0 0 0 1.5-1.5V7.5L14 3Z" />
    <path d="M13.5 3.2V8h4.8M9 13h6M9 16.5h4" />
  </svg>
);

export const Office = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M4 21V6.5a1.5 1.5 0 0 1 1-1.4l7-2.4a1 1 0 0 1 1.3 1V21" />
    <path d="M13.3 9.5H19a1.5 1.5 0 0 1 1.5 1.5V21M3 21h18M8 8.5v.01M8 12.5v.01M8 16.5v.01" />
  </svg>
);

export const Chart = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M3.5 20.5h17M7 17V11M12 17V5.5M17 17v-3.5" />
  </svg>
);

export const Chat = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M20.5 12.5c0 4-3.8 7-8.5 7a9.8 9.8 0 0 1-2.8-.4L4 20.5l1.3-3.6A6.7 6.7 0 0 1 3.5 12.5c0-3.9 3.8-7 8.5-7s8.5 3.1 8.5 7Z" />
  </svg>
);

export const ArrowUp = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </svg>
);

export const Plus = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const Chevron = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="m9 6 6 6-6 6" />
  </svg>
);

export const Copy = ({ className }: Props) => (
  <svg {...base} className={className}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5.5 15H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v.5" />
  </svg>
);

export const Shield = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.6 7 8.9 4.1-1.3 7-4.7 7-8.9V6l-7-2.5Z" />
    <path d="m9.3 12.2 1.9 1.9 3.6-3.6" />
  </svg>
);

/** The assistant's mark. A stamped seal, because every answer is a cited clause. */
export const Mark = ({ className }: Props) => (
  <svg viewBox="0 0 24 24" className={className} aria-hidden>
    <circle cx="12" cy="12" r="10" fill="currentColor" opacity="0.12" />
    <circle
      cx="12"
      cy="12"
      r="7.2"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <path
      d="M8.6 12.2 11 14.6l4.4-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const Menu = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const Close = ({ className }: Props) => (
  <svg {...base} className={className}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
