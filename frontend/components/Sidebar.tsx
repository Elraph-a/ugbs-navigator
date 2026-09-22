"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Chart, Chat, Mark, Plus, Shield } from "./Icons";

const TOPICS = [
  "How do I request an official transcript?",
  "How do I register for my courses this semester?",
  "Where do I check my results?",
  "When is the examination timetable released?",
  "How much are the fees for my programme?",
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile bar */}
      <div className="flex items-center gap-3 border-b border-line bg-shell px-4 py-3 text-shell-ink lg:hidden">
        <Mark className="size-6 text-accent" />
        <span className="flex-1 text-[0.875rem] font-semibold">Service Navigator</span>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="press rounded-sm border border-white/15 px-2.5 py-1 text-[0.75rem] font-medium"
          aria-expanded={open}
        >
          {open ? "Close" : "Menu"}
        </button>
      </div>

      <aside
        className={`${open ? "block" : "hidden"} shrink-0 bg-shell text-shell-ink lg:block lg:w-[16.5rem]`}
      >
        <div className="flex h-full flex-col gap-6 p-4">
          <div className="hidden items-center gap-2.5 px-1 pt-1 lg:flex">
            <Mark className="size-7 text-accent" />
            <div className="min-w-0">
              <p className="truncate text-[0.875rem] font-semibold leading-tight">
                Service Navigator
              </p>
              <p className="truncate text-[0.6875rem] leading-tight text-shell-muted">
                UGBS · University of Ghana
              </p>
            </div>
          </div>

          {/* A fresh ?new= value remounts the conversation; plain "/" would keep it. */}
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              router.push(`/?new=${Date.now()}`);
            }}
            className="press flex items-center gap-2 rounded-sm bg-white/10 px-3 py-2 text-left text-[0.8125rem] font-medium hover:bg-white/15"
          >
            <Plus className="size-4" />
            New conversation
          </button>

          <nav className="space-y-1">
            <NavItem href="/" active={pathname === "/"} onNavigate={() => setOpen(false)}>
              <Chat className="size-4" />
              Ask
            </NavItem>
            <NavItem
              href="/admin"
              active={pathname === "/admin"}
              onNavigate={() => setOpen(false)}
            >
              <Chart className="size-4" />
              Service analytics
            </NavItem>
          </nav>

          <div className="min-h-0 flex-1">
            <p className="label px-3 pb-2 text-shell-muted">Common enquiries</p>
            <ul className="space-y-0.5">
              {TOPICS.map((topic) => (
                <li key={topic}>
                  <Link
                    href={`/?q=${encodeURIComponent(topic)}`}
                    // Each of these is a dynamic render of "/". Prefetching all
                    // five on page load held five server requests open for as
                    // long as the page was up. They are actions, not pages.
                    prefetch={false}
                    onClick={() => setOpen(false)}
                    className="press hoverable-shell block truncate rounded-sm px-3 py-1.5 text-[0.8125rem] text-shell-muted hover:text-shell-ink"
                    title={topic}
                  >
                    {topic}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-sm bg-white/[0.06] p-3">
            <p className="flex items-center gap-1.5 text-[0.75rem] font-semibold">
              <Shield className="size-3.5 text-accent" />
              Grounded answers
            </p>
            <p className="pt-1 text-[0.6875rem] leading-relaxed text-shell-muted">
              Offices, rooms, fees and deadlines come from published documents, never
              from a language model.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}

function NavItem({
  href,
  active,
  children,
  onNavigate,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      prefetch={href === "/" ? false : undefined}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`press flex items-center gap-2.5 rounded-sm px-3 py-2 text-[0.8125rem] font-medium ${
        active
          ? "bg-white/10 text-shell-ink"
          : "text-shell-muted hover:bg-white/[0.07] hover:text-shell-ink"
      }`}
    >
      {children}
    </Link>
  );
}
