"use client";

/* Charts are drawn by hand rather than pulled from a library: at this scale a
   dependency buys nothing, and the register's hairline grammar is easier to keep
   when the marks are ours. Stroke widths stay honest under scaling via
   vector-effect, and every series carries a text alternative. */

const W = 720;
const H = 200;
const PAD = { top: 14, right: 8, bottom: 22, left: 30 };

function scale(values: number[], height: number) {
  const max = Math.max(...values, 1);
  const top = Math.ceil(max * 1.15);
  return {
    top,
    y: (value: number) =>
      PAD.top + (height - PAD.top - PAD.bottom) * (1 - value / top),
  };
}

export function DemandOverTime({
  weeks,
  totals,
  forecastWeeks,
  forecastValues,
}: {
  weeks: string[];
  totals: number[];
  forecastWeeks: string[];
  forecastValues: number[];
}) {
  const all = [...totals, ...forecastValues];
  const { top, y } = scale(all, H);
  const count = all.length;
  const x = (i: number) =>
    PAD.left + ((W - PAD.left - PAD.right) * i) / Math.max(count - 1, 1);

  const line = totals.map((value, i) => `${x(i)},${y(value)}`).join(" ");
  const area = `${PAD.left},${y(0)} ${line} ${x(totals.length - 1)},${y(0)}`;

  // The forecast continues from the last observed point so the join is visible.
  const projected = [totals[totals.length - 1], ...forecastValues]
    .map((value, i) => `${x(totals.length - 1 + i)},${y(value)}`)
    .join(" ");

  const ticks = [0, Math.round(top / 2), top];

  return (
    <figure className="mt-4">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label={`Weekly enquiry volume across ${weeks.length} weeks, peaking at ${Math.max(...totals)}, with a ${forecastValues.length}-week projection.`}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--line)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={PAD.left - 6}
              y={y(tick) + 3.5}
              textAnchor="end"
              className="tabular"
              fontSize="9"
              fill="var(--faint)"
            >
              {tick}
            </text>
          </g>
        ))}

        <polygon points={area} fill="var(--accent)" opacity="0.09" />
        <polyline
          points={line}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.75"
          vectorEffect="non-scaling-stroke"
        />
        <polyline
          points={projected}
          fill="none"
          stroke="var(--faint)"
          strokeWidth="1.5"
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />

        {totals.map((value, i) => (
          <circle key={i} cx={x(i)} cy={y(value)} r="2" fill="var(--accent)" />
        ))}

        <text x={PAD.left} y={H - 6} fontSize="9" fill="var(--faint)">
          {weeks[0]}
        </text>
        <text
          x={x(totals.length - 1)}
          y={H - 6}
          fontSize="9"
          fill="var(--faint)"
          textAnchor="middle"
        >
          {weeks[weeks.length - 1]}
        </text>
        <text x={W - PAD.right} y={H - 6} fontSize="9" fill="var(--faint)" textAnchor="end">
          {forecastWeeks[forecastWeeks.length - 1]} (projected)
        </text>
      </svg>
    </figure>
  );
}

export function RankedBars({
  rows,
  accent = "var(--accent)",
}: {
  rows: { label: string; value: number; sub?: string; alert?: boolean }[];
  accent?: string;
}) {
  const max = Math.max(...rows.map((row) => row.value), 1);

  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((row, index) => (
        <li key={row.label} className="slip py-2.5" style={{ animationDelay: `${index * 35}ms` }}>
          <div className="flex items-baseline justify-between gap-3">
            {/* Sentence case, not title case: labels are both category keys
                ("fees and finance") and service names ("Graduation and congregation"). */}
            <span className="text-[0.875rem] leading-snug first-letter:uppercase">{row.label}</span>
            <span className="shrink-0 text-[0.875rem] font-semibold tabular">
              {row.value.toLocaleString()}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunk">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(row.value / max) * 100}%`,
                  background: row.alert ? "var(--oxide)" : accent,
                }}
              />
            </div>
            {row.sub && (
              <span className="w-20 shrink-0 text-right text-[0.75rem] text-faint tabular">
                {row.sub}
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}


/** Enquiries by hour of the day. Columns rather than a line: each hour is a
 *  slot on a rota, not a point on a trend. */
export function HourBars({
  hours,
  counts,
  peak,
}: {
  hours: number[];
  counts: number[];
  peak: number | null;
}) {
  const max = Math.max(...counts, 1);
  const label = (hour: number) =>
    hour === 0 ? "12am" : hour < 12 ? `${hour}am` : hour === 12 ? "12pm" : `${hour - 12}pm`;

  return (
    <figure className="mt-1">
      <div
        className="flex items-end gap-[3px]"
        role="img"
        aria-label={`Enquiries by hour, busiest at ${peak === null ? "no clear hour" : label(peak)}.`}
      >
        {hours.map((hour, index) => (
          <div key={hour} className="group flex flex-1 flex-col items-center gap-1">
            <span className="text-[0.625rem] text-faint tabular opacity-0 group-hover:opacity-100">
              {counts[index]}
            </span>
            <div
              className="w-full rounded-t-[2px]"
              style={{
                height: `${Math.max((counts[index] / max) * 84, counts[index] ? 2 : 0)}px`,
                background: hour === peak ? "var(--accent)" : "var(--line)",
              }}
              title={`${label(hour)}: ${counts[index]}`}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between pt-1.5 text-[0.625rem] text-faint tabular">
        {[0, 6, 12, 18, 23].map((hour) => (
          <span key={hour}>{label(hour)}</span>
        ))}
      </div>
    </figure>
  );
}
