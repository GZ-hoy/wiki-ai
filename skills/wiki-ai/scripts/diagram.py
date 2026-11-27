#!/usr/bin/env python3
"""wiki-ai 구조도 도구 — JSON 사양을 일관된 디자인의 SVG 로 그린다 (Python 표준 라이브러리만 사용).

  diagram.py build  spec.json out.svg     사양 → SVG (아이콘은 내려받아 SVG 안에 넣음) + 자동 검사
  diagram.py check  spec.json             겹침·글자 넘침·화살표 관통 검사만
  diagram.py render out.svg [out.png]     Chrome/Edge/Chromium 이 있으면 PNG 로 (Claude 가 직접 보고 고치는 용도)
  diagram.py icons  lu|si <검색어>        아이콘 이름 찾기 (lu = Lucide 일반 아이콘, si = Simple Icons 로고)

아이콘 출처 (버전 고정, 캐시: ~/.cache/gz-airesearch-wiki/icons):
  Lucide  (ISC)   https://lucide.dev          — 일반 아이콘 (서버, DB, 파일, 사용자 …)
  Simple Icons (CC0) https://simpleicons.org  — 기술·제품 로고 (Python, PyTorch, Docker …)
사양 형식과 디자인 규칙은 ../reference/diagram-guide.md 참고.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

LUCIDE_VER = "1.81.0"
SIMPLE_VER = "16.38.1"
CDN = "https://cdn.jsdelivr.net/npm"
CACHE = Path(os.environ.get("GZ_WIKI_ICON_CACHE", "~/.cache/gz-airesearch-wiki/icons")).expanduser()

# ---------------------------------------------------------------- design tokens
INK, SUB, LINE, BORDER, PANEL = "#0F172A", "#64748B", "#94A3B8", "#E2E8F0", "#F8FAFC"
NEUTRAL = "#475569"
FONT = "'Pretendard','Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif"
PALETTE = {  # 이름으로 쓸 수 있는 강조색 (브랜드 색이 없을 때)
    "blue": "#2563EB", "indigo": "#4F46E5", "violet": "#7C3AED", "teal": "#0D9488", "green": "#16A34A",
    "amber": "#D97706", "orange": "#EA580C", "red": "#DC2626", "pink": "#DB2777", "slate": NEUTRAL,
}
CARD_PAD, ICON_BOX, BADGE_R = 14, 36, 9
TITLE_FS, SUB_FS, GROUP_FS = 13.5, 11.5, 15


class Fail(Exception):
    pass


# ---------------------------------------------------------------- icons
def _fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "wiki-ai-diagram"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return data


def _cached(rel, url):
    p = CACHE / rel
    if p.is_file() and p.stat().st_size > 0:
        return p.read_bytes()
    return _fetch(url, p)


def icon_svg(kind, name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or ""):
        raise Fail(f"아이콘 이름 형식 오류: {kind}:{name}")
    if kind == "lu":
        return _cached(f"lucide-{LUCIDE_VER}/{name}.svg", f"{CDN}/lucide-static@{LUCIDE_VER}/icons/{name}.svg").decode("utf-8")
    if kind == "si":
        return _cached(f"simple-{SIMPLE_VER}/{name}.svg", f"{CDN}/simple-icons@{SIMPLE_VER}/icons/{name}.svg").decode("utf-8")
    raise Fail(f"아이콘 종류는 lu 또는 si: {kind}:{name}")


def simple_data():
    raw = _cached(f"simple-{SIMPLE_VER}/_data.json", f"{CDN}/simple-icons@{SIMPLE_VER}/data/simple-icons.json")
    d = json.loads(raw.decode("utf-8"))
    return d if isinstance(d, list) else d.get("icons", [])


def lucide_tags():
    return json.loads(_cached(f"lucide-{LUCIDE_VER}/_tags.json", f"{CDN}/lucide-static@{LUCIDE_VER}/tags.json").decode("utf-8"))


def brand_hex(slug):
    for x in simple_data():
        if x.get("slug") == slug:
            return "#" + x["hex"]
    return None


def parse_icon(ref):
    if not ref:
        return None
    kind, _, name = ref.partition(":")
    if not name:
        raise Fail(f"아이콘은 'lu:이름' 또는 'si:이름' 형식: {ref}")
    return kind, name


def symbol_for(kind, name, warnings):
    sid = f"{kind}-{name}"
    try:
        raw = icon_svg(kind, name)
        raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
        m = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.S)
        if not m:
            raise Fail("svg 파싱 실패")
        inner = re.sub(r"<title>.*?</title>", "", m.group(1), flags=re.S).strip()
        if re.search(r"<(script|foreignObject|image)\b|\bon\w+=|href=", inner, re.I):
            raise Fail("허용되지 않는 요소 포함")
    except Exception as e:  # 오프라인 등 → 대체 도형
        warnings.append(f"아이콘 {kind}:{name} 을 가져오지 못해 대체 도형 사용 ({e})")
        letter = escape(name[:1].upper())
        inner = (f'<rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                 f'<text x="12" y="16" font-size="10" font-weight="700" text-anchor="middle" fill="currentColor" '
                 f'stroke="none">{letter}</text>')
        return f'<symbol id="{sid}" viewBox="0 0 24 24">{inner}</symbol>'
    if kind == "lu":
        attrs = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    else:
        attrs = 'fill="currentColor"'
    return f'<symbol id="{sid}" viewBox="0 0 24 24" {attrs}>{inner}</symbol>'


# ---------------------------------------------------------------- text metrics (근사)
def text_width(s, fs, bold=False):
    w = 0.0
    for ch in str(s):
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F or 0x4E00 <= o <= 0x9FFF:
            w += 0.95
        elif ch in "il.,:;|!'`":
            w += 0.3
        elif ch in "mwMW@":
            w += 0.85
        elif ch.isupper() or ch.isdigit():
            w += 0.64
        elif ch == " ":
            w += 0.3
        else:
            w += 0.55
    return w * fs * (1.05 if bold else 1.0)


# ---------------------------------------------------------------- spec helpers
def color_of(v, default):
    if not v:
        return default
    if v in PALETTE:
        return PALETTE[v]
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        return v
    raise Fail(f"색상은 #RRGGBB 또는 {sorted(PALETTE)} 중 하나: {v}")


def rect(o):
    return (o["x"], o["y"], o["x"] + o["w"], o["y"] + o["h"])


def inside(inner, outer, m=0):
    return inner[0] >= outer[0] + m and inner[1] >= outer[1] + m and inner[2] <= outer[2] - m and inner[3] <= outer[3] - m


def overlap(a, b, m=0):
    return a[0] < b[2] + m and b[0] < a[2] + m and a[1] < b[3] + m and b[1] < a[3] + m


def load_spec(path):
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Fail(f"사양 JSON 오류 (UTF-8 JSON 이어야 함): {e}")
    except OSError as e:
        raise Fail(f"사양 파일을 읽을 수 없음: {e}")
    for k in ("width", "height"):
        if not isinstance(spec.get(k), (int, float)):
            raise Fail(f"사양에 {k} (숫자) 필요")
    spec.setdefault("groups", [])
    spec.setdefault("nodes", [])
    spec.setdefault("edges", [])
    spec.setdefault("notes", [])
    ids = {}
    for kind in ("groups", "nodes"):
        for o in spec[kind]:
            for k in ("id", "x", "y", "w", "h"):
                if k not in o:
                    raise Fail(f"{kind} 항목에 '{k}' 없음: {o}")
            if o["id"] in ids:
                raise Fail(f"id 중복: {o['id']}")
            ids[o["id"]] = o
    return spec, ids


def resolve_colors(spec, warnings):
    for g in spec["groups"]:
        default = NEUTRAL
        ic = parse_icon(g.get("logo"))
        if ic and ic[0] == "si" and not g.get("color"):
            try:
                default = brand_hex(ic[1]) or NEUTRAL
            except Exception as e:
                warnings.append(f"브랜드 색을 가져오지 못함 ({ic[1]}): {e}")
        g["_color"] = color_of(g.get("color"), default)
    for n in spec["nodes"]:
        grp = next((g for g in spec["groups"] if g["id"] == n.get("group")), None)
        if grp is None:
            grp = next((g for g in spec["groups"] if inside(rect(n), rect(g))), None)
            if grp is not None:
                n["group"] = grp["id"]
        n["_color"] = color_of(n.get("color"), grp["_color"] if grp else NEUTRAL)


# ---------------------------------------------------------------- edges
SIDES = ("left", "right", "top", "bottom")


def anchor(o, side):
    x0, y0, x1, y1 = rect(o)
    return {"left": (x0, (y0 + y1) / 2), "right": (x1, (y0 + y1) / 2),
            "top": ((x0 + x1) / 2, y0), "bottom": ((x0 + x1) / 2, y1)}[side]


def auto_sides(a, b):
    ax0, ay0, ax1, ay1 = rect(a)
    bx0, by0, bx1, by1 = rect(b)
    if bx0 >= ax1:
        return "right", "left"
    if ax0 >= bx1:
        return "left", "right"
    if by0 >= ay1:
        return "bottom", "top"
    return "top", "bottom"


def edge_points(e, ids):
    if e.get("points"):
        return [tuple(p) for p in e["points"]]
    a, b = ids.get(e["from"]), ids.get(e["to"])
    if a is None or b is None:
        raise Fail(f"edge 의 from/to id 없음: {e}")
    s1, s2 = auto_sides(a, b)
    s1, s2 = e.get("from_side", s1), e.get("to_side", s2)
    if s1 not in SIDES or s2 not in SIDES:
        raise Fail(f"side 는 {SIDES} 중 하나: {e}")
    (x1, y1), (x2, y2) = anchor(a, s1), anchor(b, s2)
    h1, h2 = s1 in ("left", "right"), s2 in ("left", "right")
    if h1 and h2:
        if abs(y1 - y2) < 0.5:
            pts = [(x1, y1), (x2, y2)]
        else:
            xm = e.get("via", (x1 + x2) / 2)
            pts = [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
    elif not h1 and not h2:
        if abs(x1 - x2) < 0.5:
            pts = [(x1, y1), (x2, y2)]
        else:
            ym = e.get("via", (y1 + y2) / 2)
            pts = [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]
    elif h1:
        pts = [(x1, y1), (x2, y1), (x2, y2)]
    else:
        pts = [(x1, y1), (x1, y2), (x2, y2)]
    return pts


def shorten_end(pts, d=3):
    (xa, ya), (xb, yb) = pts[-2], pts[-1]
    L = ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5
    if L <= d:
        return pts
    return pts[:-1] + [(xb - (xb - xa) * d / L, yb - (yb - ya) * d / L)]


def label_pos(e, pts):
    if e.get("label_at"):
        return tuple(e["label_at"])
    segs = list(zip(pts, pts[1:]))
    (xa, ya), (xb, yb) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
    return ((xa + xb) / 2, (ya + yb) / 2)


def pill_rect(cx, cy, label):
    w = text_width(label, 11) + 16
    return (cx - w / 2, cy - 9, cx + w / 2, cy + 9)


def seg_hits_rect(p, q, r, m=1):
    (x1, y1), (x2, y2) = p, q
    x0, y0, x3, y3 = r[0] + m, r[1] + m, r[2] - m, r[3] - m
    if abs(y1 - y2) < 0.5:  # 수평
        return y0 < y1 < y3 and max(min(x1, x2), x0) < min(max(x1, x2), x3)
    if abs(x1 - x2) < 0.5:  # 수직
        return x0 < x1 < x3 and max(min(y1, y2), y0) < min(max(y1, y2), y3)
    return False


# ---------------------------------------------------------------- check
def check(spec, ids):
    errors, warns = [], []
    W, H = spec["width"], spec["height"]
    canvas = (0, 0, W, H)
    groups, nodes = spec["groups"], spec["nodes"]
    for o in groups + nodes:
        if not inside(rect(o), canvas):
            errors.append(f"'{o['id']}' 가 캔버스({W}x{H}) 밖으로 나감")
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            ra, rb = rect(a), rect(b)
            if overlap(ra, rb) and not (inside(ra, rb) or inside(rb, ra)):
                errors.append(f"그룹 '{a['id']}' 와 '{b['id']}' 가 겹침")
        if text_width(a.get("title", ""), GROUP_FS, True) + 46 + 12 > a["w"]:
            warns.append(f"그룹 '{a['id']}' 제목이 폭보다 김")
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if overlap(rect(a), rect(b), 8):
                errors.append(f"노드 '{a['id']}' 와 '{b['id']}' 가 겹치거나 간격 8px 미만")
        if a.get("group"):
            g = ids.get(a["group"])
            if g is None:
                errors.append(f"노드 '{a['id']}' 의 group '{a['group']}' 없음")
            elif not inside(rect(a), rect(g), 8):
                errors.append(f"노드 '{a['id']}' 가 그룹 '{g['id']}' 안쪽(여백 8px)을 벗어남")
            elif a["y"] < g["y"] + 44:
                errors.append(f"노드 '{a['id']}' 가 그룹 '{g['id']}' 제목 줄(위 44px)을 가림")
        left = CARD_PAD + ICON_BOX + 12 if a.get("icon") else CARD_PAD
        right = CARD_PAD + (BADGE_R * 2 + 6 if a.get("num") is not None else 0)
        avail = a["w"] - left - right
        for key, fs, bold in (("title", TITLE_FS, True), ("sub", SUB_FS, False)):
            if a.get(key) and text_width(a[key], fs, bold) > avail:
                errors.append(f"노드 '{a['id']}' 의 {key} 글자가 넘침 (약 {text_width(a[key], fs, bold):.0f}px > {avail:.0f}px): '{a[key]}'")
        if a["h"] < (52 if a.get("sub") else 36):
            warns.append(f"노드 '{a['id']}' 높이가 작음 ({a['h']})")
    pills = []
    for e in spec["edges"]:
        try:
            pts = edge_points(e, ids)
        except Fail as ex:
            errors.append(str(ex))
            continue
        ends = {e.get("from"), e.get("to")}
        for n in nodes:
            if n["id"] in ends:
                continue
            if any(seg_hits_rect(p, q, rect(n)) for p, q in zip(pts, pts[1:])):
                errors.append(f"화살표 {e.get('from')}→{e.get('to')} 가 노드 '{n['id']}' 를 관통")
        if e.get("label"):
            pr = pill_rect(*label_pos(e, pts), e["label"])
            for n in nodes:
                if overlap(pr, rect(n)):
                    warns.append(f"화살표 라벨 '{e['label']}' 가 노드 '{n['id']}' 와 겹침 → label_at 으로 옮기기")
            for other in pills:
                if overlap(pr, other[1]):
                    warns.append(f"화살표 라벨 '{e['label']}' 와 '{other[0]}' 가 겹침")
            pills.append((e["label"], pr))
    if spec.get("title") and text_width(spec["title"], 18, True) + 24 > W:
        errors.append("제목이 캔버스 폭보다 김")
    # 빈 공간: 캔버스·그룹이 내용보다 지나치게 큼
    boxes = [rect(o) for o in groups + nodes]
    if boxes:
        r = max(b[2] for b in boxes)
        bottom = max([b[3] for b in boxes] + [nt["y"] for nt in spec["notes"]])
        if W - r > 60:
            warns.append(f"오른쪽 빈 공간 {W - r:.0f}px → width 를 {r + 24:.0f} 정도로")
        if H - bottom > 60:
            warns.append(f"아래쪽 빈 공간 {H - bottom:.0f}px → height 를 {bottom + 24:.0f} 정도로")
    edge_pts = []
    for e in spec["edges"]:
        try:
            edge_pts += edge_points(e, ids)
        except Fail:
            pass
    for g in groups:
        gr = rect(g)
        kids = [rect(n) for n in nodes if n.get("group") == g["id"] or (not n.get("group") and inside(rect(n), gr))]
        if not kids:
            continue
        gx0, gy0, gx1, gy1 = gr
        inner = [p for p in edge_pts if gx0 < p[0] < gx1 and gy0 < p[1] < gy1]
        low = max([k[3] for k in kids] + [p[1] for p in inner])
        right = max([k[2] for k in kids] + [p[0] for p in inner])
        same_row = any(o is not g and o["y"] == g["y"] and o["h"] == g["h"] for o in groups)  # 높이 맞춘 줄
        same_col = any(o is not g and o["x"] == g["x"] and o["w"] == g["w"] for o in groups)
        if gy1 - low > 70 and not same_row:
            warns.append(f"그룹 '{g['id']}' 아래쪽이 {gy1 - low:.0f}px 비어 있음 → h 줄이기")
        if gx1 - right > 70 and not same_col:
            warns.append(f"그룹 '{g['id']}' 오른쪽이 {gx1 - right:.0f}px 비어 있음 → w 줄이기")
    return errors, warns


# ---------------------------------------------------------------- render svg
def t(x, y, s, fs, weight=400, color=INK, anchor_="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor_}">{escape(str(s))}</text>')


def use(kind, name, x, y, size, color, used):
    used.add((kind, name))
    return f'<use href="#{kind}-{name}" x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" style="color:{color}"/>'


def build(spec, ids):
    warnings = []
    resolve_colors(spec, warnings)
    W, H = spec["width"], spec["height"]
    used, body = set(), [f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    if spec.get("title"):
        body.append(t(24, 36, spec["title"], 18, 800))
        if spec.get("subtitle"):
            body.append(t(24 + text_width(spec["title"], 18, True) + 18, 36, spec["subtitle"], 12.5, 400, SUB))
    for i, g in enumerate(spec["groups"]):
        x, y, w, h, c = g["x"], g["y"], g["w"], g["h"], g["_color"]
        body += [f'<clipPath id="gc{i}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16"/></clipPath>',
                 f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{PANEL}" stroke="{BORDER}"/>',
                 f'<rect x="{x}" y="{y}" width="{w}" height="4" fill="{c}" clip-path="url(#gc{i})"/>']
        tx = x + 18
        ic = parse_icon(g.get("logo"))
        if ic:
            body.append(use(*ic, x + 18, y + 18, 20, c, used))
            tx = x + 46
        body.append(t(tx, y + 33, g.get("title", ""), GROUP_FS, 700))
    for n in spec["nodes"]:
        x, y, w, h, c = n["x"], n["y"], n["w"], n["h"], n["_color"]
        fill = "#FFFFFF" if not n.get("fill") else color_of(n["fill"], "#FFFFFF")
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{BORDER}" filter="url(#sh)"/>')
        tx = x + CARD_PAD
        ic = parse_icon(n.get("icon"))
        if ic:
            iy = y + (h - ICON_BOX) / 2
            body += [f'<rect x="{x + CARD_PAD}" y="{iy:.1f}" width="{ICON_BOX}" height="{ICON_BOX}" rx="10" fill="{c}" fill-opacity="0.12"/>',
                     use(*ic, x + CARD_PAD + 8, iy + 8, 20, c, used)]
            tx = x + CARD_PAD + ICON_BOX + 12
        if n.get("align") == "center" and not ic:
            cx = x + w / 2
            if n.get("sub"):
                body += [t(cx, y + h / 2 - 3, n.get("title", ""), TITLE_FS, 700, INK, "middle"),
                         t(cx, y + h / 2 + 15, n["sub"], SUB_FS, 400, SUB, "middle")]
            else:
                body.append(t(cx, y + h / 2 + 5, n.get("title", ""), TITLE_FS, 700, INK, "middle"))
        elif n.get("sub"):
            body += [t(tx, y + h / 2 - 3, n.get("title", ""), TITLE_FS, 700),
                     t(tx, y + h / 2 + 15, n["sub"], SUB_FS, 400, SUB)]
        else:
            body.append(t(tx, y + h / 2 + 5, n.get("title", ""), TITLE_FS, 700))
        if n.get("num") is not None:
            body += [f'<circle cx="{x + w - 16}" cy="{y + 16}" r="{BADGE_R}" fill="{c}"/>',
                     t(x + w - 16, y + 20, n["num"], 10.5, 700, "#FFFFFF", "middle")]
    labels = []
    for e in spec["edges"]:
        pts = edge_points(e, ids)
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in shorten_end(pts))
        dash = ' stroke-dasharray="5 4"' if e.get("style") == "dashed" else ""
        col = color_of(e.get("color"), LINE)
        mk = "ah" if col == LINE else f"ah{col[1:]}"
        if mk != "ah":
            used.add(("marker", col))
        both = ' marker-start="url(#{0})"'.format(mk) if e.get("both") else ""
        body.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.6"{dash} marker-end="url(#{mk})"{both}/>')
        if e.get("label"):
            cx, cy = label_pos(e, pts)
            x0, y0, x1, _ = pill_rect(cx, cy, e["label"])
            labels += [f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="18" rx="9" fill="#FFFFFF" stroke="{BORDER}"/>',
                       t(cx, cy + 4, e["label"], 11, 500, SUB, "middle")]
    body += labels
    for nt in spec["notes"]:
        body.append(t(nt["x"], nt["y"], nt["text"], nt.get("size", 12), nt.get("weight", 400),
                      color_of(nt.get("color"), SUB), nt.get("anchor", "start")))
    defs = ['<filter id="sh" x="-10%" y="-10%" width="120%" height="140%"><feDropShadow dx="0" dy="1" '
            'stdDeviation="1.6" flood-color="#0F172A" flood-opacity="0.08"/></filter>']

    def marker(mid, col):
        return (f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" '
                f'orient="auto-start-reverse"><path d="M1,1.5 L8.5,5 L1,8.5" fill="none" stroke="{col}" '
                f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></marker>')

    defs.append(marker("ah", LINE))
    for kind, name in sorted(used):
        if kind == "marker":
            defs.append(marker(f"ah{name[1:]}", name))
        else:
            defs.append(symbol_for(kind, name, warnings))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="{FONT}">\n<defs>{"".join(defs)}</defs>\n' + "\n".join(body) + "\n</svg>\n")
    return svg, warnings


# ---------------------------------------------------------------- browser render
def find_browser():
    env = os.environ.get("GZ_WIKI_BROWSER")
    cands = [env] if env else []
    cands += [shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge")]
    cands += [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    return next((c for c in cands if c and Path(c).is_file()), None)


def render_png(svg_path, png_path):
    b = find_browser()
    if not b:
        return None
    txt = Path(svg_path).read_text(encoding="utf-8")
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', txt)
    w, h = (int(float(m.group(1))), int(float(m.group(2)))) if m else (1200, 600)
    with tempfile.TemporaryDirectory() as prof:
        cmd = [b, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               f"--user-data-dir={prof}", "--force-device-scale-factor=2", f"--window-size={w},{h}",
               f"--screenshot={Path(png_path).resolve()}", Path(svg_path).resolve().as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    return png_path if Path(png_path).is_file() else None


# ---------------------------------------------------------------- commands
def report(errors, warns):
    for e in errors:
        print(f"  ✗ {e}")
    for w in warns:
        print(f"  ! {w}")
    if not errors and not warns:
        print("  ✓ 겹침·넘침·관통 없음")


def cmd_check(a):
    spec, ids = load_spec(a.spec)
    errors, warns = check(spec, ids)
    print(f"검사: {a.spec}")
    report(errors, warns)
    return 1 if errors else 0


def cmd_build(a):
    spec, ids = load_spec(a.spec)
    errors, warns = check(spec, ids)
    svg, w2 = build(spec, ids)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"SVG: {out} ({len(svg.encode('utf-8')) // 1024} KB, {spec['width']}x{spec['height']})")
    report(errors, warns + w2)
    if a.png:
        png = render_png(out, out.with_suffix(".png"))
        print(f"PNG 미리보기: {png}" if png else "PNG 미리보기: 브라우저(Chrome/Edge/Chromium) 없음 → 웹 검토 화면에서 확인")
    if errors:
        print("→ ✗ 항목을 고친 뒤 다시 build 하세요.")
    return 1 if errors else 0


def cmd_render(a):
    png = a.png or str(Path(a.svg).with_suffix(".png"))
    r = render_png(a.svg, png)
    if not r:
        print("브라우저(Chrome/Edge/Chromium)를 찾지 못함. GZ_WIKI_BROWSER=경로 로 지정 가능. 웹 검토 화면에서 확인하세요.")
        return 2
    print(f"PNG: {r}")
    return 0


def cmd_icons(a):
    q = a.query.lower()
    if a.kind == "si":
        hits = [x for x in simple_data()
                if q in x.get("title", "").lower() or q in x.get("slug", "")
                or any(q in str(v).lower() for v in (x.get("aliases") or {}).get("aka", []))]
        for x in hits[:25]:
            print(f"si:{x['slug']:<28} #{x['hex']}  {x['title']}")
    elif a.kind == "lu":
        tags = lucide_tags()
        hits = [n for n, tg in tags.items() if q in n or any(q in s.lower() for s in tg)]
        hits.sort(key=lambda n: (q not in n, len(n)))
        for n in hits[:40]:
            print(f"lu:{n}")
    else:
        raise Fail("종류는 lu 또는 si")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="사양 JSON → SVG (+ 검사)")
    b.add_argument("spec")
    b.add_argument("out")
    b.add_argument("--png", action="store_true", help="브라우저가 있으면 같은 이름의 PNG 미리보기도 생성")
    b.set_defaults(fn=cmd_build)
    c = sub.add_parser("check", help="사양 검사만")
    c.add_argument("spec")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("render", help="SVG → PNG (Chrome/Edge/Chromium 필요)")
    r.add_argument("svg")
    r.add_argument("png", nargs="?")
    r.set_defaults(fn=cmd_render)
    i = sub.add_parser("icons", help="아이콘 이름 검색")
    i.add_argument("kind", choices=["lu", "si"])
    i.add_argument("query")
    i.set_defaults(fn=cmd_icons)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except Fail as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
