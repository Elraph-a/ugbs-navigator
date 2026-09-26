"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Chart, Chat, Close, Menu, Plus, Shield } from "./Icons";

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

  // On a phone the panel sits above the page, so it has to behave like a
  // dialog: Escape closes it, and the page behind it does not scroll.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      {/* Phone header. The panel is reached from here, not shown above the page. */}
      <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-line bg-shell px-3 py-2.5 text-shell-ink lg:hidden">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="press -m-1 rounded-sm p-2 hover:bg-white/10"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="sidebar"
        >
          <Menu className="size-5" />
        </button>
        <span className="flex-1 truncate text-[0.875rem] font-semibold">
          UGBS Service Navigator
        </span>
        <button
          type="button"
          onClick={() => router.push(`/?new=${Date.now()}`)}
          className="press -m-1 rounded-sm p-2 hover:bg-white/10"
          aria-label="New conversation"
        >
          <Plus className="size-5" />
        </button>
      </header>

      {/* Dimmed page behind the open panel. */}
      <div
        onClick={() => setOpen(false)}
        aria-hidden
        className={`fixed inset-0 z-40 bg-ink/50 transition-opacity duration-200 lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      <aside
        id="sidebar"
        className={`fixed inset-y-0 left-0 z-50 flex w-[17rem] max-w-[85vw] shrink-0 flex-col bg-shell text-shell-ink transition-transform duration-[250ms] ease-[var(--ease-out)] motion-reduce:transition-none lg:static lg:z-auto lg:w-[16.5rem] lg:max-w-none lg:translate-x-0 ${
          open ? "translate-x-0 shadow-[var(--shadow-lg)]" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
          <div className="flex items-start gap-2">
            <Link
              href="/"
              prefetch={false}
              onClick={() => setOpen(false)}
              className="press min-w-0 flex-1 rounded-sm"
            >
              {/* The crest is dark indigo, so it sits on a light card to stay legible. */}
              <span className="block w-fit rounded-sm bg-white px-2.5 py-1.5">
                <Image
                  src="/ugbs-logo.png"
                  alt="University of Ghana Business School"
                  width={258}
                  height={100}
                  priority
                  className="h-8 w-auto"
                />
              </span>
              <span className="mt-2 block text-[0.875rem] font-semibold leading-tight">
                Service Navigator
              </span>
              <span className="mt-0.5 block text-[0.6875rem] leading-snug text-shell-muted">
                Student project, not an official UGBS service
              </span>
            </Link>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="press -m-1 rounded-sm p-2 hover:bg-white/10 lg:hidden"
              aria-label="Close menu"
            >
              <Close className="size-5" />
            </button>
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
              <Shield className="size-3.5 text-gold" />
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
