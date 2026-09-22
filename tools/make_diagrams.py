"""Draw the report's two diagrams from one layout spec.

    ..\\AI_Lab\\Scripts\\python.exe tools\\make_diagrams.py

Writes, for each diagram, an editable `.drawio` file (open at diagrams.net) and
an `.svg` for rendering. `tools/render_diagrams.mjs` turns the SVG into the PNG
that goes in the report.

One spec produces both formats on purpose: the file the team edits and the image
in the report cannot drift apart if they are generated from the same nodes.

The content is not invented here. Every step, fee, room and rule in the as-is
process comes from `data/structured/services.json`, which was transcribed by hand
from the University's published transcript page.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config

# --------------------------------------------------------------------------
# Palette. Muted fills with dark text so the diagrams survive photocopying and
# a projector, which is where they will actually be read.
# --------------------------------------------------------------------------

# Text is drawn larger than the boxes strictly need, because these diagrams are
# printed in a report: at A4 width a 12-unit label on a 1,390-unit canvas lands
# at about 4pt, which is unreadable on paper.
FONT_SCALE = 1.3

INK = "#1c1d1f"
STYLES = {
    "start": {"fill": "#1c1d1f", "stroke": "#1c1d1f", "text": "#ffffff", "shape": "round"},
    "step": {"fill": "#f4f4f2", "stroke": "#b9b9b4", "text": INK, "shape": "rect"},
    "decision": {"fill": "#fdf3df", "stroke": "#d9a934", "text": INK, "shape": "diamond"},
    "system": {"fill": "#eef1f8", "stroke": "#8a9ac0", "text": INK, "shape": "rect"},
    "office": {"fill": "#eaf2ec", "stroke": "#7ba488", "text": INK, "shape": "rect"},
    "end": {"fill": "#e8e8e5", "stroke": "#8f8f8a", "text": INK, "shape": "round"},
    "pain": {"fill": "#fcecea", "stroke": "#c96a5c", "text": "#7d2f24", "shape": "note"},
    "group": {"fill": "none", "stroke": "#c9c9c4", "text": "#6c6c66", "shape": "group"},
    "data": {"fill": "#f2effa", "stroke": "#9b8ec4", "text": INK, "shape": "rect"},
    "model": {"fill": "#fdf3df", "stroke": "#d9a934", "text": INK, "shape": "rect"},
}


class Node:
    def __init__(self, nid, x, y, w, h, label, kind="step", sub=None, size=12):
        self.id, self.x, self.y, self.w, self.h = nid, x, y, w, h
        self.label, self.kind, self.sub, self.size = label, kind, sub, size


class Edge:
    def __init__(self, src, dst, label=None, exit_side="bottom", entry_side="top"):
        self.src, self.dst, self.label = src, dst, label
        self.exit_side, self.entry_side = exit_side, entry_side


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------

SIDES = {
    "top": (0.5, 0.0),
    "bottom": (0.5, 1.0),
    "left": (0.0, 0.5),
    "right": (1.0, 0.5),
}


def anchor(node: Node, side: str) -> tuple[float, float]:
    fx, fy = SIDES[side]
    return node.x + node.w * fx, node.y + node.h * fy


def route(a: Node, b: Node, exit_side: str, entry_side: str) -> list[tuple[float, float]]:
    """An orthogonal path from one node to another.

    Only the four cases the diagrams need are handled; anything else falls back
    to a straight line, which is visibly wrong and therefore easy to catch.
    """
    x1, y1 = anchor(a, exit_side)
    x2, y2 = anchor(b, entry_side)

    if exit_side == "bottom" and entry_side == "top":
        if abs(x1 - x2) < 1:
            return [(x1, y1), (x2, y2)]
        mid = (y1 + y2) / 2
        return [(x1, y1), (x1, mid), (x2, mid), (x2, y2)]
    if exit_side == "top" and entry_side == "bottom":
        mid = (y1 + y2) / 2
        if abs(x1 - x2) < 1:
            return [(x1, y1), (x2, y2)]
        return [(x1, y1), (x1, mid), (x2, mid), (x2, y2)]
    if exit_side in ("left", "right") and entry_side == "top":
        return [(x1, y1), (x2, y1), (x2, y2)]
    if exit_side == "bottom" and entry_side in ("left", "right"):
        return [(x1, y1), (x1, y2), (x2, y2)]
    if exit_side in ("left", "right") and entry_side in ("left", "right"):
        mid = (x1 + x2) / 2
        return [(x1, y1), (mid, y1), (mid, y2), (x2, y2)]
    return [(x1, y1), (x2, y2)]


def wrap(text: str, width: float, size: float) -> list[str]:
    """Greedy wrap. Character width is about 0.54 em in the fonts used here."""
    limit = max(int((width - 20) / (size * 0.54)), 6)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if len(candidate) <= limit:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
    return lines


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------


def svg_node(n: Node) -> str:
    s = STYLES[n.kind]
    parts = []
    if s["shape"] == "diamond":
        cx, cy = n.x + n.w / 2, n.y + n.h / 2
        pts = f"{cx},{n.y} {n.x + n.w},{cy} {cx},{n.y + n.h} {n.x},{cy}"
        parts.append(
            f'<polygon points="{pts}" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.5"/>'
        )
    elif s["shape"] == "group":
        parts.append(
            f'<rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="10" fill="none" '
            f'stroke="{s["stroke"]}" stroke-width="1.25" stroke-dasharray="6 5"/>'
        )
        parts.append(
            f'<text x="{n.x + 14}" y="{n.y + 22}" font-size="15" fill="{s["text"]}" '
            f'font-weight="600" letter-spacing="0.6">{escape(n.label.upper())}</text>'
        )
        return "".join(parts)
    elif s["shape"] == "note":
        fold = 14
        pts = (
            f"{n.x},{n.y} {n.x + n.w - fold},{n.y} {n.x + n.w},{n.y + fold} "
            f"{n.x + n.w},{n.y + n.h} {n.x},{n.y + n.h}"
        )
        parts.append(
            f'<polygon points="{pts}" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.25"/>'
        )
    else:
        rx = n.h / 2 if s["shape"] == "round" else 8
        parts.append(
            f'<rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="{rx}" '
            f'fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.5"/>'
        )

    size = n.size * FONT_SCALE
    sub_size = size - 1
    lines = wrap(n.label, n.w, size)
    sub_lines = wrap(n.sub, n.w, sub_size) if n.sub else []
    line_h = size * 1.3
    sub_h = sub_size * 1.25
    total = len(lines) * line_h + (len(sub_lines) * sub_h + 6 if sub_lines else 0)
    y = n.y + n.h / 2 - total / 2 + n.size * 0.95
    weight = "600" if n.kind in ("start", "end", "office") else "500"

    for line in lines:
        parts.append(
            f'<text x="{n.x + n.w / 2}" y="{y:.1f}" text-anchor="middle" font-size="{size:.1f}" '
            f'font-weight="{weight}" fill="{s["text"]}">{escape(line)}</text>'
        )
        y += line_h
    if sub_lines:
        y += 4
        for line in sub_lines:
            parts.append(
                f'<text x="{n.x + n.w / 2}" y="{y:.1f}" text-anchor="middle" '
                f'font-size="{sub_size:.1f}" fill="{s["text"]}" opacity="0.72">{escape(line)}</text>'
            )
            y += sub_h
    return "".join(parts)


def svg_edge(e: Edge, nodes: dict[str, Node]) -> str:
    points = route(nodes[e.src], nodes[e.dst], e.exit_side, e.entry_side)
    d = " ".join(f"{'M' if i == 0 else 'L'} {x:.1f} {y:.1f}" for i, (x, y) in enumerate(points))
    out = [
        f'<path d="{d}" fill="none" stroke="#7d7d78" stroke-width="1.5" '
        f'marker-end="url(#arrow)"/>'
    ]
    if e.label:
        # On the longest segment. Two branches leaving the same point share
        # their first segment, so labelling that one stacks them on top of
        # each other; the longest segment is where the paths have separated.
        (x1, y1), (x2, y2) = max(
            zip(points, points[1:]),
            key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]),
        )
        lx, ly = (x1 + x2) / 2, (y1 + y2) / 2
        horizontal = abs(y2 - y1) < 1
        width = len(e.label) * 8 + 10
        dx, dy = (0, -6) if horizontal else (10, 0)
        out.append(
            f'<rect x="{lx + dx - (width / 2 if horizontal else 2)}" y="{ly + dy - 11}" '
            f'width="{width}" height="18" rx="3" fill="#ffffff" opacity="0.92"/>'
            f'<text x="{lx + dx}" y="{ly + dy}" text-anchor="{"middle" if horizontal else "start"}" '
            f'font-size="14" font-weight="600" fill="#5c5c57">{escape(e.label)}</text>'
        )
    return "".join(out)


def to_svg(title: str, subtitle: str, nodes: list[Node], edges: list[Edge], w: int, h: int) -> str:
    index = {n.id: n for n in nodes}
    groups = [n for n in nodes if n.kind == "group"]
    rest = [n for n in nodes if n.kind != "group"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="Segoe UI, Inter, Helvetica, Arial, sans-serif">
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M 0 0 L 10 5 L 0 10 z" fill="#7d7d78"/></marker></defs>
<rect width="{w}" height="{h}" fill="#ffffff"/>
<text x="40" y="46" font-size="21" font-weight="700" fill="{INK}">{escape(title)}</text>
<text x="40" y="70" font-size="13" fill="#6c6c66">{escape(subtitle)}</text>
{"".join(svg_node(n) for n in groups)}
{"".join(svg_edge(e, index) for e in edges)}
{"".join(svg_node(n) for n in rest)}
</svg>"""


# --------------------------------------------------------------------------
# draw.io
# --------------------------------------------------------------------------

DRAWIO_SHAPES = {
    "rect": "rounded=1;arcSize=12;",
    "round": "rounded=1;arcSize=60;",
    "diamond": "rhombus;",
    "note": "shape=note;size=14;",
    "group": "rounded=1;dashed=1;verticalAlign=top;align=left;spacingLeft=10;spacingTop=4;",
}


def to_drawio(title: str, nodes: list[Node], edges: list[Edge]) -> str:
    cells = []
    for n in nodes:
        s = STYLES[n.kind]
        style = (
            DRAWIO_SHAPES[s["shape"]]
            + f"whiteSpace=wrap;html=1;fillColor={s['fill']};strokeColor={s['stroke']};"
            + f"fontColor={s['text']};fontSize={n.size};"
            + ("fontStyle=1;" if n.kind in ("start", "end", "office", "group") else "")
        )
        # draw.io holds the label as escaped HTML inside the attribute, and
        # renders it as HTML because the style sets html=1. Escaping the whole
        # string (tags included) is what makes the file well-formed XML.
        label = n.label.replace("\n", "<br>") + (
            f"<br><font style='font-size:{n.size - 1}px' color='#6c6c66'>{n.sub}</font>"
            if n.sub
            else ""
        )
        cells.append(
            f'<mxCell id="{n.id}" value="{escape(label, {chr(34): "&quot;"})}" '
            f'style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" as="geometry"/></mxCell>'
        )
    for i, e in enumerate(edges):
        ex, ey = SIDES[e.exit_side]
        nx, ny = SIDES[e.entry_side]
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#7d7d78;"
            f"exitX={ex};exitY={ey};entryX={nx};entryY={ny};exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
            "fontSize=11;fontColor=#5c5c57;"
        )
        cells.append(
            f'<mxCell id="e{i}" value="{escape(e.label or "")}" style="{style}" edge="1" '
            f'parent="1" source="{e.src}" target="{e.dst}"><mxGeometry relative="1" as="geometry"/></mxCell>'
        )
    body = "\n        ".join(cells)
    return f"""<mxfile host="app.diagrams.net">
  <diagram name="{escape(title)}">
    <mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" page="1" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        {body}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""


# --------------------------------------------------------------------------
# Diagram 1 — the as-is process
# --------------------------------------------------------------------------


def process_diagram() -> tuple[str, str, list[Node], list[Edge], int, int]:
    N, E = [], []
    col = 250  # main column centre
    w = 300

    def step(nid, y, label, kind="step", sub=None, x=None, width=w, h=72):
        N.append(Node(nid, (col - width / 2) if x is None else x, y, width, h, label, kind, sub))

    step("start", 100, "Student needs an official transcript", "start", h=58)

    N.append(Node("d1", col - 110, 190, 220, 92, "Postgraduate\nstudent?", "decision"))
    step("sgs", 210, "Email the School of Graduate Studies", "office",
         "sgstranscript@ug.edu.gh — a different office entirely", x=600, width=350, h=80)

    N.append(Node("d2", col - 110, 340, 220, 92, "Graduated\nbefore 1996?", "decision"))
    step("pre96a", 350, "Pay at the Cash Office", "office", x=600, width=350, h=56)
    step("pre96b", 418, "Submit the receipt at Room D2, AAD", "office",
         "Ready for collection in about two weeks", x=600, width=350, h=80)

    N.append(Node("d3", col - 110, 500, 220, 92, "Needed the\nsame day?", "decision"))
    step("exp1", 500, "Submit the request before 11:00 AM", "step",
         "Express is not available on the STS portal", x=600, width=350, h=80)
    step("exp2", 582, "Pay at the Cash Office", "office", x=600, width=350, h=56)
    step("exp3", 646, "Submit the receipt at Room D2, AAD", "office",
         "Typically ready within 24 hours — GH₵60", x=600, width=350, h=80)

    step("s1", 660, "Check your record on the MIS portal", "system", "mis.ug.edu.gh")
    step("s2", 748, "Submit the request and pay on the STS portal", "system", "sts.ug.edu.gh")
    step("s3", 836, "Track the request on the same portal", "system")
    N.append(Node("d4", col - 110, 920, 220, 92, "Collected by\nsomeone else?", "decision"))
    step("proxy", 930, "Bring a consent letter, the owner's ID and the proxy's ID", "step",
         "Only discoverable at the collection desk", x=600, width=350, h=92)
    step("done", 1080, "Transcript issued", "end", h=58)

    E += [
        Edge("start", "d1"),
        Edge("d1", "sgs", "yes", "right", "left"),
        Edge("d1", "d2", "no"),
        Edge("d2", "pre96a", "yes", "right", "left"),
        Edge("pre96a", "pre96b"),
        Edge("d2", "d3", "no"),
        Edge("d3", "exp1", "yes", "right", "left"),
        Edge("exp1", "exp2"),
        Edge("exp2", "exp3"),
        Edge("d3", "s1", "no"),
        Edge("s1", "s2"),
        Edge("s2", "s3"),
        Edge("s3", "d4"),
        Edge("d4", "proxy", "yes", "right", "left"),
        Edge("d4", "done", "no"),
    ]

    pains = [
        ("p1", 96, "1. Four different routes, and the student must know which one applies "
                    "before starting. Nothing asks them."),
        ("p2", 248, "2. Three separate systems: MIS Web for records, the STS portal for the "
                    "request and payment, the Cash Office for express and pre-1996 routes."),
        ("p3", 400, "3. Two offices own “transcripts”. Postgraduate requests go to the "
                    "School of Graduate Studies, which is one line on the AAD's page."),
        ("p4", 552, "4. Express eligibility is a time-of-day rule — before 11:00 AM — visible "
                    "only to a student who reads the whole page first."),
        ("p5", 704, "5. Six fee variants by delivery mode: GH₵30 pick-up, GH₵85 by post, "
                    "US$55 courier, US$10 digital, GH₵60 express, GH₵25 per extra copy."),
        ("p6", 856, "6. Proxy rules surface at the collection desk. A student who did not "
                    "read ahead makes a second trip."),
    ]
    for nid, y, text in pains:
        N.append(Node(nid, 1010, y, 360, 124, text, "pain", size=11))

    return (
        "As-is process: requesting an official transcript",
        "Transcribed from the University of Ghana's published procedure. Numbered notes mark "
        "where a student must already know something the process never asks.",
        N, E, 1420, 1200,
    )


# --------------------------------------------------------------------------
# Diagram 2 — the architecture
# --------------------------------------------------------------------------


def architecture_diagram() -> tuple[str, str, list[Node], list[Edge], int, int]:
    N, E = [], []

    def box(nid, x, y, w, h, label, kind="step", sub=None, size=12):
        N.append(Node(nid, x, y, w, h, label, kind, sub, size))

    # Layer frames, drawn behind everything else. The brief's chain reads
    # user -> interface -> AI system -> knowledge -> decision, so the frames are
    # laid out in that order: two bands across the top, then a centre column
    # with knowledge feeding in from the left and action leaving to the right.
    box("g_user", 20, 96, 1460, 100, "Users", "group")
    box("g_ui", 20, 214, 1460, 128, "Interface", "group")
    box("g_ai", 420, 360, 700, 770, "AI system — one conversational turn", "group")
    box("g_know", 20, 470, 390, 400, "Knowledge and data", "group")
    box("g_act", 1150, 940, 320, 280, "Decision and action", "group")

    box("student", 120, 124, 340, 56, "UGBS student", "start")
    box("admin", 560, 124, 340, 56, "UGBS administrative staff", "start")

    box("chat", 120, 244, 340, 80, "Chat interface", "step",
        "Streamed reply, citations, office card, steps")
    box("dash", 560, 244, 340, 80, "Administrative dashboard", "step",
        "Demand, gap register, deflection, forecast")

    box("api", 440, 390, 660, 58, "FastAPI service", "step",
        "/chat/stream · /analytics · /services")
    box("triage", 440, 466, 660, 80, "1. Triage", "model",
        "In scope, small talk or off topic — and rewrite a follow-up into a full question")
    box("router", 440, 562, 660, 80, "2. Route", "step",
        "Question to service and office — a table lookup, never a model")
    box("retrieve", 440, 658, 660, 80, "3. Retrieve", "step",
        "Embeddings and keywords over the document index, fused into one ranking")
    box("gate", 440, 754, 660, 100, "4. Confidence gate", "decision",
        "Too weak a match: the model is not called at all")
    box("compose", 440, 882, 420, 124, "5. Compose the reply", "model",
        "The model phrases an answer from the retrieved text and the verified procedure. "
        "It supplies no facts of its own.")
    box("refuse", 880, 882, 220, 124, "5b. Decline", "pain",
        "Name what is not covered and which office to ask")
    box("redact", 440, 1032, 660, 76, "6. Redact, then log", "step",
        "Names, IDs, phone numbers and emails removed before anything is written")

    box("structured", 40, 500, 350, 160, "Verified procedure catalogue", "data",
        "services.json and offices.json — rooms, fees, contacts and steps, transcribed "
        "by hand from the published sources")
    box("corpus", 40, 690, 350, 150, "Document index", "data",
        "Published UG and UGBS documents, chunked and embedded, each carrying its source, "
        "date and real-or-synthetic label", size=11)

    box("log", 1170, 980, 280, 110, "Enquiry log", "data",
        "Redacted, with a retention limit")
    box("insight", 1170, 1120, 280, 80, "Analytics", "office",
        "What to publish next, where to add staff")

    E += [
        Edge("student", "chat"),
        Edge("admin", "dash"),
        Edge("chat", "api"),
        Edge("dash", "api"),
        Edge("api", "triage"),
        Edge("triage", "router"),
        Edge("router", "retrieve"),
        Edge("retrieve", "gate"),
        Edge("gate", "compose", "answerable"),
        Edge("gate", "refuse", "no verified source"),
        Edge("compose", "redact"),
        Edge("refuse", "redact"),
        Edge("structured", "router", "", "right", "left"),
        Edge("corpus", "retrieve", "", "right", "left"),
        Edge("redact", "log", "", "right", "left"),
        Edge("log", "insight"),
    ]

    return (
        "System architecture: UGBS Service Navigator",
        "The model phrases answers. Offices, rooms, fees and steps come from the verified "
        "catalogue or a cited document, never from the model.",
        N, E, 1510, 1270,
    )


def main() -> int:
    config.DOCS.mkdir(parents=True, exist_ok=True)
    for name, build in (
        ("current-process", process_diagram),
        ("architecture", architecture_diagram),
    ):
        title, subtitle, nodes, edges, w, h = build()
        (config.DOCS / f"{name}.svg").write_text(
            to_svg(title, subtitle, nodes, edges, w, h), encoding="utf-8"
        )
        (config.DOCS / f"{name}.drawio").write_text(
            to_drawio(title, nodes, edges), encoding="utf-8"
        )
        print(f"{name}: {len(nodes)} shapes, {len(edges)} connectors -> docs/{name}.svg + .drawio")
    print("Render the PNGs with: node tools/render_diagrams.mjs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
