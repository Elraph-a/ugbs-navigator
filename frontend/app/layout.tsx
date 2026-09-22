import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

// Self-hosted at build time, so the demo carries no runtime font dependency.
const archivo = Archivo({
  // latin-ext carries the cedi sign (U+20B5). With "latin" alone, bold fee text
  // fell back to a system face that drew GH₵30 as "GHC30" — the wrong currency,
  // on a fee.
  subsets: ["latin", "latin-ext"],
  variable: "--font-archivo",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "UGBS Service Navigator",
  description:
    "Ask about any University of Ghana Business School administrative procedure and get an answer grounded in published documents.",
};

const CONTRACT = `
THESIS: An assistant that shows its work. The agent's real steps stream from the
backend as it routes, searches and verifies, so the interface reveals the mechanism
rather than covering a wait with a spinner. It refuses the answer-from-nowhere chat box.
OWN-WORLD: Deep ink shell against a soft canvas, white cards on quiet shadow, viridian
for verified and interactive, ochre for ageing sources, oxide for refusals. Archivo,
tabular figures, authored stroke icons.
STORY: A student asks in their own words, watches the agent place the enquiry and
search published documents, then gets numbered steps, the fee table, the office to
visit and the sources, or else a plain refusal and the office to contact.
FIRST VIEWPORT: Shell left, conversation centred at 46rem, greeting and four real
enquiries as cards, composer resting at the bottom with the privacy line beneath it.
FORM: Conversational agent interface. Operate mode, designed for the real use scene:
a phone, in daylight, in a corridor.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={archivo.variable}>
      <body>
        <div dangerouslySetInnerHTML={{ __html: `<!--${CONTRACT}-->` }} />
        <div className="flex h-dvh flex-col lg:flex-row">
          <Sidebar />
          <div className="min-w-0 flex-1 overflow-hidden">{children}</div>
        </div>
      </body>
    </html>
  );
}
