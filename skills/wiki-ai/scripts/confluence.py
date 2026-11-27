#!/usr/bin/env python3
"""Confluence Data Center helper for the /wiki-ai skill (Python stdlib only).

Commands
  init                      create a key file template (chmod 600) if none exists
  check                     verify credentials, space, parent page and reference page
  templates                 list reference pages (CONFLUENCE_TEMPLATE_PAGE_ID, comma-separated)
  get PAGE_ID|URL|template|parent [--mode text|outline|skeleton|storage]
  render FILE [--mode text|skeleton]   view a local draft the same way as `get`
  suggest --keywords K ... [--state F]   rank upload-location candidates with reasons
  search QUERY [--all-spaces]   find pages by title (to pick an upload location)
  where PAGE_ID|URL         show a page's path and children
  find --title TITLE        exact title lookup in the configured space
  validate FILE [--attach PATH[=NAME] ...]
  check-draft FILE --project DIR [--evidence F] [--state F]   automatic review checks
  review-stamp REVIEW --body FILE   bind the review record (review.json) to the current draft
  review-mark REVIEW [--full-read] [--answer QID TEXT] [--body FILE]   record the human review
  preview FILE [--attach PATH=NAME ...] [--title T]   static HTML preview file
  serve FILE [--attach ...] [--title T] [--stop]   review web server (opens the browser; drag-to-comment, answer questions)
  feedback [FILE] [--resolve FID ... --note T] [--applied QID ...]   read/resolve web review comments
  publish --title T --body FILE [--attach PATH[=NAME] ...] [--state FILE]
          [--page-id ID] [--parent ID] [--adopt] [--force] [--dry-run]

Config: KEY=VALUE lines read from $GZ_WIKI_KEY_FILE, else
~/.config/gz-airesearch-wiki/key. Environment variables of the same name win.
Secret values are never printed.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from base64 import b64encode
from datetime import datetime, timezone
from html.entities import name2codepoint
from pathlib import Path

DEFAULT_KEY_FILE = Path("~/.config/gz-airesearch-wiki/key").expanduser()
KEYS = [
    "CONFLUENCE_BASE_URL",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_EMAIL",
    "CONFLUENCE_SPACE_KEY",
    "CONFLUENCE_TEMPLATE_PAGE_ID",
]
REQUIRED = ["CONFLUENCE_BASE_URL", "CONFLUENCE_API_TOKEN", "CONFLUENCE_SPACE_KEY"]
KEY_TEMPLATE = """# GZ-airesearch-wiki 설정 파일. 이 파일은 절대 공유/커밋하지 마세요.
CONFLUENCE_BASE_URL=https://docs.golfzon.company
# 프로필 > 설정 > 개인 액세스 토큰 에서 발급
CONFLUENCE_API_TOKEN=
# Atlassian Cloud일 때만 입력 (사내 Data Center는 비워둠)
CONFLUENCE_EMAIL=
CONFLUENCE_SPACE_KEY=airesearch
# 스타일 참고 페이지 ID, 쉼표로 여러 개 가능 (기본: 팀 레퍼런스 페이지)
CONFLUENCE_TEMPLATE_PAGE_ID=161383239
"""
NS_DECL = (
    'xmlns:ac="http://atlassian.com/content" '
    'xmlns:ri="http://atlassian.com/resource/identifier" '
    'xmlns:at="http://atlassian.com/template"'
)
NS = {
    "http://atlassian.com/content": "ac",
    "http://atlassian.com/resource/identifier": "ri",
    "http://atlassian.com/template": "at",
}


class Fail(Exception):
    pass


# ----------------------------------------------------------------- config / http
def key_file_path():
    env = os.environ.get("GZ_WIKI_KEY_FILE")
    return Path(env).expanduser() if env else DEFAULT_KEY_FILE


def parse_dotenv(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = re.split(r"\s+#", v.strip(), maxsplit=1)[0].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load_config():
    path = key_file_path()
    cfg = parse_dotenv(path) if path.is_file() else {}
    for k in KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        raise Fail(
            f"설정 누락: {', '.join(missing)}\n"
            f"키 파일: {path} ({'있음' if path.is_file() else '없음'})\n"
            f"`confluence.py init` 으로 템플릿을 만든 뒤 값을 채워주세요."
        )
    cfg["CONFLUENCE_BASE_URL"] = cfg["CONFLUENCE_BASE_URL"].rstrip("/")
    cfg["_key_file"] = str(path) if path.is_file() else "(environment)"
    return cfg


class Client:
    def __init__(self, cfg):
        self.base = cfg["CONFLUENCE_BASE_URL"]
        token = cfg["CONFLUENCE_API_TOKEN"]
        if cfg.get("CONFLUENCE_EMAIL"):
            self.auth = "Basic " + b64encode(f"{cfg['CONFLUENCE_EMAIL']}:{token}".encode()).decode()
            self.mode = "basic (Cloud)"
        else:
            self.auth = "Bearer " + token
            self.mode = "bearer PAT (Data Center)"

    def call(self, method, path, params=None, json_body=None, data=None, headers=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        h = {"Authorization": self.auth, "Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("message", detail)
            except Exception:
                pass
            raise Fail(f"HTTP {e.code} {method} {path}: {str(detail)[:600]}")
        except urllib.error.URLError as e:
            raise Fail(f"연결 실패 {self.base}: {e.reason}")
        return json.loads(raw) if raw else {}

    def page(self, page_id, expand="version,space,ancestors"):
        return self.call("GET", f"/rest/api/content/{page_id}", {"expand": expand})

    def page_url(self, page):
        links = page.get("_links", {})
        if links.get("webui"):
            return (links.get("base") or self.base) + links["webui"]
        return f"{self.base}/pages/viewpage.action?pageId={page['id']}"


# ----------------------------------------------------------------- storage xml
def fix_entities(s):
    def sub(m):
        n = m.group(1)
        if n in ("amp", "lt", "gt", "quot", "apos") or n not in name2codepoint:
            return m.group(0)
        return f"&#{name2codepoint[n]};"

    return re.sub(r"&([A-Za-z][A-Za-z0-9]*);", sub, s)


def parse_storage(s):
    return ET.fromstring(f"<root {NS_DECL}>{fix_entities(s)}</root>")


def qn(tag):
    if isinstance(tag, str) and tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        return f"{NS.get(uri, '?')}:{local}"
    return tag


def attr(el, name):
    for k, v in el.attrib.items():
        if qn(k) == name:
            return v
    return None


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


BLOCK_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "tbody", "thead",
    "tr", "div", "blockquote", "pre", "hr", "colgroup", "ac:structured-macro", "ac:layout",
    "ac:layout-section", "ac:layout-cell", "ac:rich-text-body", "ac:task-list",
}


def inline(el):
    s = el.text or ""
    for c in el:
        s += inline_child(c) + (c.tail or "")
    return s


def inline_child(c):
    t = qn(c.tag)
    if t == "ac:image":
        for d in c.iter():
            if qn(d.tag) == "ri:attachment":
                return f"[이미지: {attr(d, 'ri:filename')}]"
            if qn(d.tag) == "ri:url":
                return f"[이미지: {attr(d, 'ri:value')}]"
        return "[이미지]"
    if t in ("strong", "b"):
        x = norm(inline(c))
        return f"**{x}**" if x else ""
    if t in ("em", "i"):
        return f"*{inline(c)}*"
    if t == "code":
        return f"`{inline(c)}`"
    if t == "a":
        return f"[{norm(inline(c))}]({c.get('href')})"
    if t == "ac:link":
        for d in c.iter():
            if qn(d.tag) == "ri:page":
                return f"[위키링크: {attr(d, 'ri:content-title')}]"
        return "[링크]"
    if t == "br":
        return " "
    if t == "ac:structured-macro":
        return " " + " ".join(block(c, 0)) + " "
    return inline(c)


def blocks(el, ind):
    out, buf = [], el.text or ""

    def flush():
        nonlocal buf
        if norm(buf):
            out.append("  " * ind + norm(buf))
        buf = ""

    for c in el:
        if qn(c.tag) in BLOCK_TAGS:
            flush()
            out += block(c, ind)
        else:
            buf += inline_child(c)
        buf += c.tail or ""
    flush()
    return out


def block(c, ind):
    t = qn(c.tag)
    pad = "  " * ind
    if re.fullmatch(r"h[1-6]", t):
        return ["", "#" * int(t[1]) + " " + norm(inline(c))]
    if t in ("ul", "ol", "ac:task-list"):
        out = []
        for li in c:
            lines = blocks(li, ind + 1)
            if lines:
                lines[0] = pad + "- " + lines[0].lstrip()
            out += lines
        return out
    if t == "table":
        rows = [r for r in c.iter() if qn(r.tag) == "tr"]
        out = []
        for i, r in enumerate(rows):
            cells = [" / ".join(x.strip() for x in blocks(cell, 0)) for cell in r if qn(cell.tag) in ("td", "th")]
            out.append(pad + "| " + " | ".join(cells) + " |")
            if i == 0:
                out.append(pad + "|" + "---|" * len(cells))
        return out
    if t == "colgroup" or t == "hr":
        return []
    if t == "ac:structured-macro":
        name = attr(c, "ac:name")
        params = {attr(p, "ac:name"): norm(inline(p)) for p in c if qn(p.tag) == "ac:parameter"}
        plain = next((p.text or "" for p in c if qn(p.tag) == "ac:plain-text-body"), None)
        rich = next((p for p in c if qn(p.tag) == "ac:rich-text-body"), None)
        if name == "mathjax":
            return [pad + "$$ " + (plain or "").strip() + " $$"]
        if name == "code":
            return [pad + "```" + params.get("language", "")] + [pad + x for x in (plain or "").splitlines()] + [pad + "```"]
        head = pad + f"[{name}" + (f": {params.get('title')}" if params.get("title") else "") + "]"
        out = [head]
        if plain is not None:
            out += [pad + "  " + x for x in plain.splitlines()]
        if rich is not None:
            out += blocks(rich, ind + 1)
        return out + ([pad + f"[/{name}]"] if rich is not None else [])
    return blocks(c, ind)


def storage_to_text(s):
    lines = blocks(parse_storage(s), 0)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def storage_skeleton(s, text_len=40):
    """참고 페이지의 실제 마크업 양식만 남긴다.
    글자는 줄이고, 편집기 메타데이터는 지우고, 문서 안에서 이미 보여준 구조(같은 표/접기/행 패턴)는 생략한다."""
    import copy
    root = copy.deepcopy(parse_storage(s))
    drop_attrs = {"data-uuid", "ac:macro-id", "ac:local-id", "local-id", "data-local-id", "ac:schema-version"}

    def short(t):
        if not t:
            return t
        t2 = re.sub(r"\s+", " ", t)
        return t2 if len(t2) <= text_len else t2[:text_len] + "…"

    def is_blank_p(e):
        return e.tag == "p" and not norm(inline(e)) and all(c.tag == "br" for c in e)

    def struct(e):
        keep = tuple(sorted((qn(k), v) for k, v in e.attrib.items() if qn(k) in ("ac:name", "class")))
        return (qn(e.tag), keep, tuple(struct(c) for c in e if not is_blank_p(c)))

    def size(e):
        return sum(1 for _ in e.iter())

    seen = set()

    def mark(prev, text):
        prev.tail = (prev.tail or "") + f" ⟪{text}⟫ "

    def walk(e):
        for k in list(e.attrib):
            if qn(k) in drop_attrs or (k == "class" and not e.attrib[k].strip()):
                del e.attrib[k]
        if qn(e.tag) != "ac:plain-text-body":
            e.text = short(e.text)
        kids = list(e)
        prev, run, run_kind = None, 0, None

        def flush():
            nonlocal run, run_kind
            if run and prev is not None:
                mark(prev, f"빈 문단 {run}개" if run_kind == "blank" else f"앞에 나온 구조와 같은 블록 {run}개 생략")
            elif run:
                e.text = (e.text or "") + (f" ⟪빈 문단 {run}개⟫ " if run_kind == "blank" else f" ⟪앞에 나온 구조와 같은 블록 {run}개 생략⟫ ")
            run, run_kind = 0, None

        for c in kids:
            kind = None
            if is_blank_p(c):
                kind = "blank"
            elif size(c) >= 4:
                st = struct(c)
                if st in seen:
                    kind = "dup"
                else:
                    seen.add(st)
            if kind:
                if run_kind not in (None, kind):
                    flush()
                run_kind = kind
                run += 1
                e.remove(c)
                continue
            flush()
            walk(c)
            c.tail = short(c.tail)
            prev = c
        flush()

    walk(root)
    for prefix, uri in (("ac", "http://atlassian.com/content"), ("ri", "http://atlassian.com/resource/identifier")):
        ET.register_namespace(prefix, uri)
    ET.indent(root, space=" ")
    out = ET.tostring(root, encoding="unicode")
    out = re.sub(r"^<root[^>]*>\s*|\s*</root>\s*$", "", out)
    out = re.sub(r'\s+xmlns:\w+="[^"]+"', "", out)
    out = re.sub(r"(<ac:plain-text-body>)(.*?)(</ac:plain-text-body>)",
                 lambda m: m.group(1) + "<![CDATA[" + html_unescape(m.group(2)) + "]]>" + m.group(3), out, flags=re.S)
    return out


def html_unescape(t):
    import html
    return html.unescape(t)


def analyze(storage):
    """Local structural check. Returns (report dict, errors list)."""
    errors = []
    try:
        root = parse_storage(storage)
    except ET.ParseError as e:
        return {}, [f"XML 파싱 실패: {e} (태그 닫힘, & 이스케이프(&amp;), CDATA 확인)"]
    headings, attachments, macros = [], [], {}
    for el in root.iter():
        t = qn(el.tag)
        if re.fullmatch(r"h[1-6]", t):
            headings.append((int(t[1]), norm(inline(el).replace("**", ""))))
        elif t == "ri:attachment":
            fn = attr(el, "ri:filename")
            if fn and fn not in attachments:
                attachments.append(fn)
        elif t == "ac:structured-macro":
            n = attr(el, "ac:name")
            macros[n] = macros.get(n, 0) + 1
            if n == "mathjax":
                body = next((p for p in el if qn(p.tag) == "ac:plain-text-body"), None)
                if body is None or not (body.text or "").strip():
                    errors.append("mathjax 매크로에 ac:plain-text-body(CDATA 수식)가 없음")
            if n == "expand":
                if not any(qn(p.tag) == "ac:rich-text-body" for p in el):
                    errors.append("expand 매크로에 ac:rich-text-body가 없음")
    if not headings:
        errors.append("제목(h1~h3)이 하나도 없음")
    tables = sum(1 for el in root.iter() if el.tag == "table")
    return {"headings": headings, "attachments": attachments, "macros": macros, "tables": tables}, errors


def attach_specs(specs, draft_file):
    """명시한 --attach + 초안 옆 attach.txt (한 줄에 '프로젝트 기준 경로=첨부이름'). 같은 첨부이름은 명시한 것이 우선."""
    out = list(specs or [])
    f = Path(draft_file).parent / "attach.txt"
    if f.is_file():
        project = f.parent.parent
        names = {s.partition("=")[2] or Path(s.partition("=")[0]).name for s in out}
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            path, _, name = line.partition("=")
            name = name or Path(path).name
            if name in names:
                continue
            pp = Path(path).expanduser()
            out.append(f"{pp if pp.is_absolute() else project / pp}={name}")
            names.add(name)
    return out


def parse_attach(specs):
    out = []
    for spec in specs or []:
        path, _, name = spec.partition("=")
        p = Path(path).expanduser()
        if not p.is_file():
            raise Fail(f"첨부 파일 없음: {path}")
        out.append((p, name or p.name))
    names = [n for _, n in out]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise Fail(f"첨부 파일 이름 중복: {sorted(dup)} → PATH=고유이름 형식으로 이름을 지정하세요")
    return out


def check_body(storage, attach, existing=()):
    report, errors = analyze(storage)
    warnings = []
    if report:
        provided = {n for _, n in attach}
        for fn in report["attachments"]:
            if fn not in provided and fn not in existing:
                errors.append(f"본문이 참조하는 첨부 '{fn}' 가 --attach 목록에 없음")
        for n in sorted(provided - set(report["attachments"])):
            warnings.append(f"첨부 '{n}' 는 본문에서 참조되지 않음 (업로드는 됨)")
    return report, errors, warnings


def print_report(report):
    print("구성:")
    for lvl, title in report.get("headings", []):
        print("  " + "  " * (lvl - 1) + f"h{lvl} {title}")
    print(f"표 {report.get('tables', 0)}개, 이미지 참조 {len(report.get('attachments', []))}개, 매크로 {report.get('macros', {})}")


# ----------------------------------------------------------------- attachments
def multipart(fields, filename, data, ctype):
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    fn = filename.replace('"', "_")
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{fn}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
    )
    parts += [data, b"\r\n", f"--{b}--\r\n".encode()]
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def existing_attachments(cl, page_id):
    out, start = {}, 0
    while True:
        r = cl.call("GET", f"/rest/api/content/{page_id}/child/attachment", {"start": start, "limit": 200})
        for a in r.get("results", []):
            out[a["title"]] = a["id"]
        if r.get("size", 0) < 200:
            return out
        start += 200


def upload(cl, page_id, path, name, existing):
    data = path.read_bytes()
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    body, ct = multipart({"minorEdit": "true"}, name, data, ctype)
    headers = {"X-Atlassian-Token": "no-check", "Content-Type": ct}
    if name in existing:
        cl.call("POST", f"/rest/api/content/{page_id}/child/attachment/{existing[name]}/data", data=body, headers=headers)
    else:
        r = cl.call("POST", f"/rest/api/content/{page_id}/child/attachment", data=body, headers=headers)
        if r.get("results"):
            existing[name] = r["results"][0]["id"]


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ----------------------------------------------------------------- commands
def resolve_id(cl, cfg, ref):
    """page id | page URL (/pages/<id>/, pageId=<id>, /display/<space>/<title>) | 'template'."""
    ref = ref.strip()
    if ref == "template":
        ids = template_ids(cfg)
        if not ids:
            raise Fail("CONFLUENCE_TEMPLATE_PAGE_ID 가 설정되지 않음")
        return ids[0]
    if ref.isdigit():
        return ref
    m = re.search(r"/pages/(\d+)", ref) or re.search(r"pageId=(\d+)", ref)
    if m:
        return m.group(1)
    m = re.search(r"/display/([^/?#]+)/([^?#]+)", ref)
    if m:
        space, title = m.group(1), urllib.parse.unquote_plus(m.group(2))
        res = find_by_title(cl, space, title)
        if res:
            return res[0]["id"]
        raise Fail(f"페이지를 찾을 수 없음: {space} / {title}")
    raise Fail(f"페이지 ID/URL 로 인식할 수 없음: {ref} → `search` 로 이름 검색하세요")


def template_ids(cfg):
    return [x for x in re.split(r"[,\s]+", cfg.get("CONFLUENCE_TEMPLATE_PAGE_ID", "")) if x]


def page_path(page):
    return " > ".join([x["title"] for x in page.get("ancestors", [])] + [page["title"]])


def cmd_init(a):
    path = key_file_path()
    if path.exists():
        print(f"이미 있음: {path} (덮어쓰지 않음)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(KEY_TEMPLATE, encoding="utf-8")
    path.chmod(0o600)
    print(f"생성함: {path} (권한 600). 토큰을 채워주세요.")


def cmd_check(a):
    cfg = load_config()
    cl = Client(cfg)
    print(f"키 파일: {cfg['_key_file']}")
    print(f"서버: {cl.base} / 인증: {cl.mode}")
    me = cl.call("GET", "/rest/api/user/current")
    if me.get("type") == "anonymous" or not (me.get("username") or me.get("accountId")):
        raise Fail("인증 실패: 토큰이 유효하지 않음 (anonymous)")
    print(f"사용자: {me.get('displayName')}")
    sp = cl.call("GET", f"/rest/api/space/{cfg['CONFLUENCE_SPACE_KEY']}")
    print(f"스페이스: {sp.get('key')} ({sp.get('name')})")
    for tid in template_ids(cfg):
        tp = cl.page(tid)
        print(f"참고 페이지: {tp['title']} ({tp['id']})")
    if not template_ids(cfg):
        print("참고 페이지: (미설정 — reference/style-guide.md 만 사용)")
    print("OK")


def cmd_get(a):
    cfg = load_config()
    cl = Client(cfg)
    pid = resolve_id(cl, cfg, a.page)
    p = cl.page(pid, "body.storage,version,space,ancestors")
    s = p["body"]["storage"]["value"]
    print(f"# [{p['title']}] id={p['id']} v{p['version']['number']} space={p['space']['key']}")
    print(f"# 경로: {' > '.join(x['title'] for x in p.get('ancestors', []))}")
    print(f"# URL: {cl.page_url(p)}\n")
    if a.mode == "storage":
        out = s
    elif a.mode == "skeleton":
        out = storage_skeleton(s)
    else:
        out = storage_to_text(s)
        if a.mode == "outline":
            out = "\n".join(l for l in out.splitlines() if l.startswith("#") or re.match(r"\s*\[expand", l))
    if a.max_chars and len(out) > a.max_chars:
        out = out[: a.max_chars] + f"\n... (생략, 전체 {len(out)}자)"
    print(out)


def cmd_templates(a):
    cfg = load_config()
    cl = Client(cfg)
    ids = template_ids(cfg)
    if not ids:
        print("참고 페이지 미설정 (CONFLUENCE_TEMPLATE_PAGE_ID)")
    for tid in ids:
        p = cl.page(tid, "body.storage,version,space,ancestors")
        heads = [norm(inline(h).replace("**", "")) for h in parse_storage(p["body"]["storage"]["value"]).iter() if h.tag == "h1"]
        print(f"{p['id']}\t{page_path(p)}\n    목차: {' / '.join(heads)}")


def cmd_render(a):
    storage = Path(a.file).read_text(encoding="utf-8")
    print(storage_skeleton(storage) if a.mode == "skeleton" else storage_to_text(storage))


def find_by_title(cl, space, title):
    r = cl.call("GET", "/rest/api/content", {"spaceKey": space, "title": title, "type": "page", "expand": "version,ancestors"})
    return r.get("results", [])


def cmd_find(a):
    cfg = load_config()
    cl = Client(cfg)
    res = find_by_title(cl, cfg["CONFLUENCE_SPACE_KEY"], a.title)
    if not res:
        print("없음")
    for p in res:
        print(f"{p['id']} v{p['version']['number']} {' > '.join(x['title'] for x in p['ancestors'])} > {p['title']}  {cl.page_url(p)}")


def cmd_validate(a):
    storage = Path(a.file).read_text(encoding="utf-8")
    attach = parse_attach(attach_specs(a.attach, a.file))
    report, errors, warnings = check_body(storage, attach)
    if report:
        print_report(report)
    for w in warnings:
        print("경고:", w)
    if not errors and not a.offline:
        try:
            cl = Client(load_config())
            cl.call("POST", "/rest/api/contentbody/convert/view", json_body={"value": storage, "representation": "storage"})
            print("서버 변환 검사: 통과")
        except Fail as e:
            errors.append(f"서버 변환 검사 실패: {e}")
    if errors:
        for e in errors:
            print("오류:", e)
        raise Fail(f"검증 실패 ({len(errors)}건)")
    print("검증 통과")


def load_state(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def cmd_search(a):
    cfg = load_config()
    cl = Client(cfg)
    q = a.query.replace("\\", "\\\\").replace('"', '\\"')
    spaces = [cfg["CONFLUENCE_SPACE_KEY"]] if not a.all_spaces else []
    cql = f'type = page and title ~ "{q}"' + (f' and space = "{spaces[0]}"' if spaces else "")
    r = cl.call("GET", "/rest/api/content/search", {"cql": cql, "limit": a.limit, "expand": "ancestors,space"})
    res = r.get("results", [])
    if not res:
        print("검색 결과 없음")
    for p in res:
        print(f"{p['id']}\t[{p['space']['key']}] {page_path(p)}\t{cl.page_url(p)}")


def cmd_where(a):
    cfg = load_config()
    cl = Client(cfg)
    p = cl.page(resolve_id(cl, cfg, a.page))
    print(f"{p['id']}\t[{p['space']['key']}] {page_path(p)}\t{cl.page_url(p)}")
    kids = cl.call("GET", f"/rest/api/content/{p['id']}/child/page", {"limit": 50}).get("results", [])
    if kids:
        print("하위 페이지: " + ", ".join(k["title"] for k in kids))


HISTORY_FILE = DEFAULT_KEY_FILE.parent / "history.json"


def record_history(parent_id, path, space):
    try:
        h = json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    except Exception:
        h = []
    h = [x for x in h if x.get("parent_id") != parent_id] + [{
        "parent_id": parent_id, "path": path, "space": space,
        "count": 1 + next((x.get("count", 0) for x in h if x.get("parent_id") == parent_id), 0),
        "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }]
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(h[-30:], ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_suggest(a):
    """업로드 위치(부모 페이지) 후보를 근거와 함께 순위로 보여준다. 결정은 사용자가 한다."""
    cfg = load_config()
    cl = Client(cfg)
    space = cfg["CONFLUENCE_SPACE_KEY"]
    skip = set(template_ids(cfg))
    cands = {}

    def add(pid, path, sp, score, reason):
        c = cands.setdefault(pid, {"path": path, "space": sp, "score": 0.0, "reasons": []})
        c["score"] += score
        if reason not in c["reasons"]:
            c["reasons"].append(reason)

    # (a) 이전 업로드 위치 (업데이트 모드)
    state = load_state(Path(a.state)) if a.state else {}
    if state.get("parent_id"):
        try:
            par = cl.page(state["parent_id"])
            add(par["id"], page_path(par), par["space"]["key"], 100, "현재 위치 (이 프로젝트를 이전에 올린 곳)")
        except Fail:
            pass

    # (b) 키워드 관련 페이지가 모여 있는 곳
    for kw in a.keywords:
        q = kw.replace("\\", "\\\\").replace('"', '\\"')
        cql = f'type = page and (title ~ "{q}" or text ~ "{q}")' + ("" if a.all_spaces else f' and space = "{space}"')
        try:
            res = cl.call("GET", "/rest/api/content/search", {"cql": cql, "limit": 25, "expand": "ancestors,space,children.page"}).get("results", [])
        except Fail:
            continue
        for hit in res:
            if hit["id"] in skip:
                continue
            in_title = kw.lower() in hit["title"].lower()
            if hit.get("ancestors"):
                par = hit["ancestors"][-1]
                add(par["id"], " > ".join(x["title"] for x in hit["ancestors"]), hit["space"]["key"],
                    2.0 if in_title else 1.0, f"'{kw}' 관련 페이지 「{hit['title']}」 가 있는 곳")
            if in_title and hit.get("children", {}).get("page", {}).get("size", 0) > 0:
                add(hit["id"], page_path(hit), hit["space"]["key"], 2.5, f"'{kw}' 섹션 페이지 (하위 페이지 있음)")

    # (c) 이 플러그인으로 최근 올린 위치
    try:
        hist = json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    except Exception:
        hist = []
    for h in hist[-10:]:
        add(h["parent_id"], h["path"], h.get("space", "?"), min(1.0 + 0.5 * h.get("count", 1), 3.0), f"최근 /wiki-ai 업로드 위치 ({h.get('count', 1)}회)")

    # (d) 내가 최근 작업한 페이지들이 있는 곳
    try:
        mine = cl.call("GET", "/rest/api/content/search", {"cql": "type = page and contributor = currentUser() order by lastmodified desc", "limit": 15, "expand": "ancestors,space"}).get("results", [])
    except Fail:
        mine = []
    for pg in mine:
        if pg["id"] in skip or not pg.get("ancestors"):
            continue
        par = pg["ancestors"][-1]
        add(par["id"], " > ".join(x["title"] for x in pg["ancestors"]), pg["space"]["key"], 0.7, f"내가 최근 작업한 「{pg['title']}」 가 있는 곳")

    # 구체성 보정: 하위 섹션 점수가 상위 후보의 절반 이상이면 하위 섹션을 앞에 (더 정확한 위치 우선)
    base = {pid: c["score"] for pid, c in cands.items()}
    for pid, c in cands.items():
        for qid, q in cands.items():
            if qid != pid and c["path"].startswith(q["path"] + " > ") and base[pid] >= 0.5 * base[qid] and base[pid] < 100:
                c["score"] = max(c["score"], base[qid] + 0.1)
    ranked = sorted(cands.items(), key=lambda kv: (-kv[1]["score"], -base[kv[0]]))[: a.limit]
    if not ranked:
        print("추천 후보 없음 → 사용자에게 위치(URL 또는 페이지 이름)를 직접 물어보세요")
    for pid, c in ranked:
        reasons = c["reasons"][:3] + ([f"외 {len(c['reasons']) - 3}건"] if len(c["reasons"]) > 3 else [])
        print(f"{pid}\t[{c['space']}] {c['path']}\tscore {c['score']:.1f}\n    근거: " + " / ".join(reasons) + f"\n    {cl.base}/pages/viewpage.action?pageId={pid}")


# ----------------------------------------------------------------- review (검수)
SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private key"),
    (r"(?i)\b(api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-.]{8,}", "키/토큰/비밀번호 값"),
    (r"\bgh[pousr]_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"\bsk-[A-Za-z0-9]{20,}", "API key (sk-)"),
    (r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b", "사내 IP"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "이메일 주소"),
]
NUM_RE = re.compile(r"(?<![\w.])[+\-−]?\d[\d,]*(?:\.\d+)?%?")
TEXT_EXT = {".py", ".md", ".txt", ".json", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".log",
            ".ipynb", ".sh", ".xml", ".html", ".tex", ".rst", ".js", ".ts", ".java", ".cpp", ".h", ".c", ".r", ".sql"}
SKIP_DIRS = {".git", ".wiki-ai", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", ".mypy_cache", ".pytest_cache"}


def norm_num(t):
    return t.replace("−", "-").replace(",", "").rstrip("%").lstrip("+")


def significant(t):
    n = norm_num(t).lstrip("-")
    return "." in n or len(n.replace(".", "")) >= 3 or t.endswith("%")


def decimals(t):
    n = norm_num(t)
    return len(n.split(".", 1)[1]) if "." in n else 0


class NumIndex:
    """원본 수치를 자릿수(0~6)별 반올림 값으로 색인. 초안 수치는 '자기 자릿수로 반올림한 원본'과 같을 때만 일치."""
    def __init__(self, tokens=()):
        self.by_k = {k: set() for k in range(7)}
        for t in tokens:
            self.add(t)

    def add(self, t):
        try:
            x = abs(float(norm_num(t)))
        except ValueError:
            return
        for k in range(min(decimals(t), 6) + 1):
            self.by_k[k].add(f"{x:.{k}f}")

    def has(self, t):
        try:
            x = abs(float(norm_num(t)))
        except ValueError:
            return False
        k = min(decimals(t), 6)
        return f"{x:.{k}f}" in self.by_k[k]


def project_numbers(root, max_total=200_000_000):
    nums, total = NumIndex(), 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in TEXT_EXT:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > 5_000_000 or total + size > max_total:
                continue
            total += size
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in NUM_RE.findall(txt):
                nums.add(m)
    return nums


def draft_text_for_numbers(storage):
    text = storage_to_text(storage)
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("$$"):
            continue  # 수식은 독립 검수 에이전트가 본다
        line = re.sub(r"^(\s*#+ \**)\d+(?:\.\d+)*", r"\1", line)
        line = re.sub(r"\[이미지:[^\]]*\]|\(https?://[^)]*\)|https?://\S+", "", line)
        lines.append(line)
    return "\n".join(lines)


def parse_evidence(path):
    rows = []
    if not path or not Path(path).is_file():
        return rows
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|") or re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("#", "번호"):
            continue
        rows.append({"id": cells[0], "claim": cells[1], "source": cells[2], "status": cells[3]})
    return rows


def cmd_check_draft(a):
    storage = Path(a.file).read_text(encoding="utf-8")
    project = Path(a.project).resolve()
    ev_path = a.evidence or str(Path(a.file).parent / "evidence.md")
    ev = parse_evidence(ev_path)
    out = [f"# 자동 검사 결과", f"- 초안: `{a.file}`", f"- 프로젝트: `{project}`", f"- 근거 장부: `{ev_path}` ({len(ev)}건)", ""]
    warn = 0

    # 1) 근거 장부 검사
    out.append("## 1. 근거 장부")
    if not ev:
        out.append("- ⚠ 근거 장부가 없거나 비어 있음 → 주장·수치마다 근거를 적어야 함"); warn += 1
    status_cnt = {}
    for r in ev:
        st = r["status"].replace(" ", "")
        status_cnt[st] = status_cnt.get(st, 0) + 1
        for m in re.finditer(r"([\w./\-]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?", r["source"]):
            f, l1, l2 = project / m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            if not f.is_file():
                out.append(f"- ⚠ #{r['id']} 근거 파일 없음: `{m.group(0)}`"); warn += 1; continue
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            if l2 > len(lines) or l1 < 1:
                out.append(f"- ⚠ #{r['id']} 줄 범위 초과: `{m.group(0)}` (파일 {len(lines)}줄)"); warn += 1; continue
            claim_nums = [n for n in NUM_RE.findall(r["claim"]) if significant(n)]
            if claim_nums and "계산" not in r["source"]:
                seg = NumIndex(NUM_RE.findall("\n".join(lines[max(0, l1 - 3):l2 + 2])))
                miss = [n for n in claim_nums if not seg.has(n)]
                if miss:
                    out.append(f"- ⚠ #{r['id']} 근거 줄에서 수치 확인 안 됨: {', '.join(miss)} (`{m.group(0)}`)"); warn += 1
    out.append("- 상태별: " + (", ".join(f"{k} {v}건" for k, v in status_cnt.items()) or "없음"))
    inferred = [r for r in ev if "추론" in r["status"]]
    if inferred:
        out.append(f"- 추론 항목 {len(inferred)}건 (사람 확인 필요): " + "; ".join(f"#{r['id']} {r['claim'][:40]}" for r in inferred[:10]))
    out.append("")

    # 2) 근거 없는 수치
    out.append("## 2. 근거를 찾지 못한 수치")
    proj_nums = project_numbers(project)
    ev_nums = NumIndex(n for r in ev for n in NUM_RE.findall(r["claim"] + " " + r["source"]))
    missing = []
    for line in draft_text_for_numbers(storage).splitlines():
        for n in NUM_RE.findall(line):
            if significant(n) and not (proj_nums.has(n) or ev_nums.has(n)):
                missing.append((n, line.strip()[:90]))
    if missing:
        warn += len(missing)
        for n, ctx in missing[:40]:
            out.append(f"- ⚠ `{n}` — {ctx}")
        if len(missing) > 40:
            out.append(f"- … 외 {len(missing) - 40}건")
        out.append("- → 프로젝트 파일에 있는 값이면 근거 장부에 위치를, 계산값이면 `계산: 식` 을 적는다.")
    else:
        out.append("- 없음")
    out.append("")

    # 3) 민감 정보
    out.append("## 3. 민감 정보 패턴")
    text = storage_to_text(storage)
    hits = []
    for pat, label in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            hits.append(f"- ⚠ {label}: `{m.group(0)[:40]}`")
    out += hits or ["- 없음"]
    warn += len(hits)
    out.append("")

    # 4) 위키 현재 버전과의 변경점 (업데이트 모드)
    page_id = a.page_id
    if not page_id and a.state and Path(a.state).is_file():
        page_id = load_state(Path(a.state)).get("page_id")
    if page_id:
        import difflib
        cl = Client(load_config())
        cur = cl.page(page_id, "body.storage,version")
        old = storage_to_text(cur["body"]["storage"]["value"]).splitlines()
        new = text.splitlines()
        diff = [l for l in difflib.unified_diff(old, new, lineterm="", n=0) if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        out.append(f"## 4. 위키 현재 버전(v{cur['version']['number']}) 대비 변경점: +{sum(l[0] == '+' for l in diff)} / -{sum(l[0] == '-' for l in diff)} 줄")
        out += [f"    {l[:110]}" for l in diff[:60]]
        if len(diff) > 60:
            out.append(f"    … 외 {len(diff) - 60}줄")
        out.append("")

    out.append(f"**경고 {warn}건**")
    report = "\n".join(out)
    dest = Path(a.out) if a.out else Path(a.file).parent / "check-draft.md"
    dest.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n(저장: {dest})")


def draft_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def load_review(path):
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Fail(f"검수 기록 JSON 오류 ({p}): {e}")


def save_review(path, rv):
    Path(path).write_text(json.dumps(rv, ensure_ascii=False, indent=2), encoding="utf-8")


def review_status(review_path, body_path):
    rv = load_review(review_path)
    if rv is None:
        return {"exists": False}
    qs = rv.get("questions", [])
    return {
        "exists": True,
        "full_read": bool(rv.get("full_read")),
        "questions": len(qs),
        "open_questions": sum(1 for q in qs if q.get("status", "open") == "open"),
        "auto_fixes": len(rv.get("auto_fixes", [])),
        "hash_match": rv.get("draft_sha256") == draft_hash(body_path),
    }


def review_warnings(st, review_path):
    if not st["exists"]:
        return [f"검수 기록 없음 ({review_path})"]
    w = []
    if st["open_questions"]:
        w.append(f"남은 의문점 {st['open_questions']}개")
    if not st["full_read"]:
        w.append("사용자가 전체를 읽지 않음")
    if not st["hash_match"]:
        w.append("검수 이후 초안이 바뀜 → 바뀐 부분 재검수 권장")
    return w


def cmd_review_stamp(a):
    rv = load_review(a.review) or {"full_read": False, "questions": [], "auto_fixes": []}
    rv["draft_sha256"] = draft_hash(a.body)
    save_review(a.review, rv)
    st = review_status(a.review, a.body)
    print(f"검수 기록에 초안 해시 기록: {a.review} (의문점 {st['open_questions']}/{st['questions']} 남음, 자동 수정 {st['auto_fixes']}건, 전체 읽기 {'완료' if st['full_read'] else '안 함'})")


def cmd_review_mark(a):
    rv = load_review(a.review)
    if rv is None:
        raise Fail(f"검수 기록 없음: {a.review}")
    if a.full_read:
        rv["full_read"] = True
    for qid, text in a.answer or []:
        q = next((q for q in rv.get("questions", []) if q.get("id") == qid), None)
        if q is None:
            raise Fail(f"의문점 {qid} 없음")
        q["status"], q["answer"] = "answered", text
    if a.body:
        rv["draft_sha256"] = draft_hash(a.body)
    save_review(a.review, rv)
    st = review_status(a.review, a.body) if a.body else None
    print("검수 기록 갱신" + (f": 의문점 {st['open_questions']}/{st['questions']} 남음, 전체 읽기 {'완료' if st['full_read'] else '안 함'}" if st else ""))



# ----------------------------------------------------------------- local preview
PREVIEW_CSS = """
body{font-family:-apple-system,'Segoe UI','Malgun Gothic','Apple SD Gothic Neo',sans-serif;font-size:14px;line-height:1.6;color:#172b4d;background:#fff;max-width:1200px;margin:0 auto;padding:24px 32px}
h1{font-size:24px;margin:32px 0 12px;border-bottom:1px solid #dfe1e6;padding-bottom:6px}h2{font-size:20px;margin:28px 0 10px}h3{font-size:16px;margin:22px 0 8px}
table{border-collapse:collapse;margin:10px 0;max-width:100%}th,td{border:1px solid #c1c7d0;padding:6px 10px;vertical-align:top}th{background:#f4f5f7}
img{max-width:100%;height:auto}details{border:1px solid #dfe1e6;border-radius:3px;margin:8px 0;padding:4px 10px}summary{cursor:pointer;color:#0052cc}
pre{background:#f4f5f7;padding:10px;overflow-x:auto}code{background:#f4f5f7;padding:1px 4px}.panel{background:#deebff;border-radius:3px;padding:8px 12px;margin:8px 0}
.math{overflow-x:auto;margin:8px 0}.banner{background:#fffae6;border:1px solid #ffe380;padding:8px 12px;margin-bottom:16px;font-size:13px}
.missing{display:inline-block;border:1px dashed #de350b;color:#de350b;padding:20px;font-size:12px}
mark.q{background:#fff0b3;padding:0 2px}mark.q sup{color:#ff8b00;font-weight:bold;margin-left:2px}
.qnote{display:block;background:#fffae6;border-left:3px solid #ff991f;padding:6px 10px;margin:4px 0 8px;font-size:12.5px;color:#172b4d}
.qpanel{background:#fffae6;border:1px solid #ffe380;padding:8px 14px;margin-bottom:16px}.qpanel ul{margin:6px 0 0}
.fixlog{margin-top:40px;background:#f4f5f7}
"""


def storage_to_html(storage, images):
    """storage format → 브라우저용 HTML. images: {첨부이름: 로컬 이미지 경로(상대)}"""
    import html as _html
    root = parse_storage(storage)
    AC, RI = "{http://atlassian.com/content}", "{http://atlassian.com/resource/identifier}"

    def ser(e):
        t = e.tag
        kids = "".join(ser(c) + _html.escape(c.tail or "") for c in e)
        text = _html.escape(e.text or "")
        if t == AC + "image":
            a = next((x for x in e.iter() if x.tag in (RI + "attachment", RI + "url")), None)
            name = a.get(RI + "filename") if a is not None and a.tag == RI + "attachment" else (a.get(RI + "value") if a is not None else "")
            style = ";".join(f"{k}:{e.get(AC + k)}px" for k in ("width", "height") if e.get(AC + k))
            src = images.get(name, name if name.startswith("http") else None)
            if not src:
                return f'<span class="missing">첨부 없음: {_html.escape(name)}</span>'
            return f'<img src="{_html.escape(src)}" style="{style}" alt="{_html.escape(name)}">'
        if t == AC + "structured-macro":
            name = e.get(AC + "name")
            params = {p.get(AC + "name"): (p.text or "") for p in e if p.tag == AC + "parameter"}
            plain = next((p.text or "" for p in e if p.tag == AC + "plain-text-body"), "")
            rich = next((p for p in e if p.tag == AC + "rich-text-body"), None)
            inner = (_html.escape(rich.text or "") + "".join(ser(c) + _html.escape(c.tail or "") for c in rich)) if rich is not None else ""
            if name == "mathjax":
                return f'<div class="math">\\[{_html.escape(plain)}\\]</div>'
            if name == "expand":
                return f"<details><summary>{_html.escape(params.get('title', '펼치기'))}</summary>{inner}</details>"
            if name == "code":
                return f"<pre><code>{_html.escape(plain)}</code></pre>"
            if name in ("info", "note", "warning", "tip", "panel"):
                return f'<div class="panel">{inner}</div>'
            if name == "toc":
                return ""
            return f"<div>[{_html.escape(name or '')}] {inner}</div>"
        if t == AC + "link":
            pg = next((x for x in e.iter() if x.tag == RI + "page"), None)
            return f"<u>{_html.escape(pg.get(RI + 'content-title', '위키 링크') if pg is not None else '위키 링크')}</u>"
        if t.startswith("{"):
            return text + kids
        attrs = "".join(f' {k}="{_html.escape(v)}"' for k, v in e.attrib.items() if not k.startswith("{"))
        if t in ("br", "hr", "col"):
            return f"<{t}{attrs}>"
        return f"<{t}{attrs}>{text}{kids}</{t}>"

    return (root.text and _html.escape(root.text) or "") + "".join(ser(c) + _html.escape(c.tail or "") for c in root)


def annotate_questions(html_doc, questions):
    """열린 의문점의 anchor 문구를 본문에서 찾아 형광 표시 + 댓글 상자를 붙인다. 못 찾은 것은 목록으로 돌려준다."""
    import html as _html
    parts = re.split(r"(<[^>]+>)", html_doc)
    unplaced = []
    for q in questions:
        anchor = _html.escape(q.get("anchor", "").strip(), quote=False)
        placed = False
        if anchor:
            for i, seg in enumerate(parts):
                if seg.startswith("<") or anchor not in seg:
                    continue
                note = (f'<span class="qnote" id="q-{_html.escape(q["id"])}"><b>❓ {_html.escape(q["id"])}</b> {_html.escape(q.get("question", ""))}'
                        + (f'<br><i>{_html.escape(q["why"])}</i>' if q.get("why") else "")
                        + ("<br>선택지: " + " / ".join(_html.escape(o) for o in q.get("options", [])) if q.get("options") else "")
                        + "</span>")
                parts[i] = seg.replace(anchor, f'<mark class="q">{anchor}<sup>❓{_html.escape(q["id"])}</sup></mark>{note}', 1)
                placed = True
                break
        if not placed:
            unplaced.append(q)
    return "".join(parts), unplaced


INTERACTIVE_CSS = r"""
#content{margin-right:330px}
#side{position:fixed;top:0;right:0;width:310px;height:100vh;overflow-y:auto;background:#fafbfc;border-left:1px solid #dfe1e6;padding:14px;box-sizing:border-box;font-size:13px}
#side h3{margin:4px 0 8px;font-size:14px}#side .item{background:#fff;border:1px solid #dfe1e6;border-radius:4px;padding:8px;margin:6px 0}
#side .item.done{opacity:.55}#side .quote{color:#5e6c84;font-style:italic;display:block;margin-bottom:4px}
#side .st{float:right;font-size:11px;padding:1px 6px;border-radius:8px;background:#ffe380}#side .item.done .st{background:#abf5d1}
#side button,.qopt,#selbtn,.modal button{cursor:pointer;border:1px solid #c1c7d0;background:#fff;border-radius:3px;padding:4px 10px;font-size:13px;margin:2px}
#side button.primary,.modal button.primary{background:#0052cc;color:#fff;border-color:#0052cc}
#selbtn{position:absolute;display:none;z-index:20;background:#0052cc;color:#fff;border-color:#0052cc;box-shadow:0 2px 6px rgba(0,0,0,.2)}
mark.fb{background:#ffd6e0;padding:0 1px}mark.fb.done{background:#e3fcef}
.qopt.chosen{background:#36b37e;color:#fff;border-color:#36b37e}
.modal{position:fixed;inset:0;background:rgba(9,30,66,.4);display:none;align-items:center;justify-content:center;z-index:30}
.modal .box{background:#fff;border-radius:6px;padding:16px;width:min(520px,92vw)}.modal textarea{width:100%;height:110px;box-sizing:border-box;margin:8px 0;font-family:inherit}
#toast{position:fixed;bottom:16px;left:16px;background:#172b4d;color:#fff;padding:8px 14px;border-radius:4px;display:none;z-index:40}
@media (max-width:900px){#content{margin-right:0}#side{position:static;width:auto;height:auto;border:none}}
"""

INTERACTIVE_JS = r"""
(function(){
const $=s=>document.querySelector(s);
let state={items:[],answers:[],done_reading:false}, ver=null, pendingQuote="", pendingQid=null, submitted=null;
function toast(t){const e=$('#toast');e.textContent=t;e.style.display='block';setTimeout(()=>e.style.display='none',2200)}
async function api(p,body,ms){const c=new AbortController();const t=setTimeout(()=>c.abort(),ms||5000);
  try{const r=await fetch(p,Object.assign({signal:c.signal,cache:'no-store'},body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}));return await r.json()}finally{clearTimeout(t)}}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function highlight(quote,id,done){
  if(!quote) return; const root=$('#content'); const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  let n; while((n=w.nextNode())){ const i=n.nodeValue.indexOf(quote); if(i<0) continue;
    if(n.parentElement.closest('mark.fb')) continue;
    const r=document.createRange(); r.setStart(n,i); r.setEnd(n,i+quote.length);
    const m=document.createElement('mark'); m.className='fb'+(done?' done':''); m.title=id; m.id='fb-'+id; r.surroundContents(m); return; }
}
function render(){
  document.querySelectorAll('mark.fb').forEach(m=>{const p=m.parentNode;while(m.firstChild)p.insertBefore(m.firstChild,m);p.removeChild(m);p.normalize()});
  state.items.forEach(it=>highlight(it.quote,it.id,it.status==='done'));
  const open=state.items.filter(i=>i.status!=='done').length;
  let h=`<h3>검토 의견 <span style="font-weight:normal">(대기 ${open} / 전체 ${state.items.length})</span></h3>
  <div style="color:#5e6c84;margin-bottom:6px">문장을 드래그하면 <b>💬 수정 요청</b>을 남길 수 있어요. 다 보셨으면 <b>검수 완료</b>를 누르세요 — 의견이 있으면 Claude가 바로 반영하고 화면이 새로 고쳐집니다.</div>
  <button onclick="window.__general()">＋ 의견 추가</button>
  <button class="primary" onclick="window.__done()">검수 완료</button>`;
  state.items.slice().reverse().forEach(it=>{h+=`<div class="item ${it.status==='done'?'done':''}"><span class="st">${it.status==='done'?'반영됨':'대기'}</span><b>${esc(it.id)}</b>
   ${it.quote?`<a href="#fb-${esc(it.id)}" class="quote">“${esc(it.quote.slice(0,80))}”</a>`:'<span class="quote">(전체 의견)</span>'}${esc(it.comment)}
   ${it.resolution?`<div style="color:#006644;margin-top:4px">→ ${esc(it.resolution)}</div>`:''}</div>`});
  if(state.answers.length){h+='<h3 style="margin-top:14px">의문점 답변</h3>';state.answers.forEach(a=>{h+=`<div class="item ${a.status==='applied'?'done':''}"><span class="st">${a.status==='applied'?'반영됨':'대기'}</span><b>${esc(a.qid)}</b> ${esc(a.answer)}</div>`})}
  $('#side').innerHTML=h;
  document.querySelectorAll('.qopt').forEach(b=>{const a=state.answers.find(x=>x.qid===b.dataset.q);b.classList.toggle('chosen',!!a&&a.answer===b.dataset.a)});
}
async function load(){state=await api('/api/state');render()}
function openModal(title,quote){$('#mtitle').textContent=title;$('#mquote').textContent=quote?('“'+quote+'”'):'';$('#mtext').value='';$('#modal').style.display='flex';setTimeout(()=>$('#mtext').focus(),50)}
window.__general=()=>{pendingQuote='';pendingQid=null;openModal('의견 추가','')};
function overlay(msg){const o=$('#overlay');o.querySelector('div').innerHTML=msg;o.style.display='flex'}
window.__done=async()=>{
  const n=state.items.filter(i=>i.status!=='done').length+state.answers.filter(a=>a.status!=='applied').length;
  if(!confirm(n?`의견·답변 ${n}건을 Claude에게 보내 바로 반영할까요?`:'남긴 의견 없이 검수를 완료할까요?'))return;
  submitted=n; try{await api('/api/done',{})}catch(e){}
  overlay(n?`<b>Claude가 의견 ${n}건을 반영하고 있어요…</b><br>끝나면 이 화면이 자동으로 새로 고쳐집니다.`:'<b>✓ 검수 완료</b><br>Claude 채팅으로 돌아가 업로드를 진행하세요. 이 창은 닫아도 됩니다.');};
$('#mcancel').onclick=()=>$('#modal').style.display='none';
$('#msave').onclick=async()=>{const t=$('#mtext').value.trim();if(!t)return;
  if(pendingQid){state=await api('/api/answer',{qid:pendingQid,answer:t})}else{state=await api('/api/feedback',{quote:pendingQuote,comment:t})}
  $('#modal').style.display='none';render();toast('저장했어요');};
document.addEventListener('mouseup',e=>{
  if(e.target.closest('#side')||e.target.closest('.modal')||e.target.id==='selbtn')return;
  const s=window.getSelection();const t=s.toString().trim();const b=$('#selbtn');
  if(t.length<2||!s.rangeCount||!$('#content').contains(s.anchorNode)){b.style.display='none';return}
  const r=s.getRangeAt(0).getBoundingClientRect();b.style.left=(window.scrollX+r.left)+'px';b.style.top=(window.scrollY+r.bottom+6)+'px';b.style.display='block';b.dataset.q=t.slice(0,300);});
$('#selbtn').onclick=()=>{pendingQuote=$('#selbtn').dataset.q;pendingQid=null;$('#selbtn').style.display='none';openModal('💬 수정 요청',pendingQuote)};
document.addEventListener('click',async e=>{const b=e.target.closest('.qopt');if(!b)return;
  if(b.dataset.a==='__custom'){pendingQid=b.dataset.q;pendingQuote='';openModal('❓ '+b.dataset.q+' 직접 답변','');return}
  state=await api('/api/answer',{qid:b.dataset.q,answer:b.dataset.a});render();toast(b.dataset.q+' 답변 저장')});
let busy=false, failSince=null, sawDown=false;
function reloadKeep(){try{sessionStorage.setItem('wikiai-scroll',String(window.scrollY))}catch(e){}location.reload()}
async function poll(){ if(busy) return; busy=true;
  try{const v=(await api('/api/version',null,3000)).v; failSince=null;
    if((ver&&v!==ver)||(submitted&&sawDown)){reloadKeep();return}
    ver=v; if(submitted===null){const s=await api('/api/state',null,4000);if(JSON.stringify(s)!==JSON.stringify(state)){state=s;render()}}
  }catch(e){ sawDown=true; if(!failSince) failSince=Date.now();
    if(submitted===null) toast('검토 서버 연결 끊김 — Claude 채팅을 확인하세요');
    else if(submitted>0 && Date.now()-failSince>20000) overlay(`<b>Claude가 의견 ${submitted}건을 반영하고 있어요…</b><br>끝나면 자동으로 새로 고쳐집니다.<br><span style="color:#5e6c84;font-size:12px">오래 걸리거나 화면이 안 바뀌면 F5(새로고침)를 눌러 주세요.</span>`);
  }finally{busy=false}}
setInterval(poll,3000);
try{const y=sessionStorage.getItem('wikiai-scroll');if(y){window.scrollTo(0,+y);sessionStorage.removeItem('wikiai-scroll')}}catch(e){}
load();poll();
})();
"""


def build_preview_html(body, images, title, review_path, interactive=False):
    import html as _html
    rv = load_review(review_path) or {}
    open_q = [q for q in rv.get("questions", []) if q.get("status", "open") == "open"]
    content = storage_to_html(body.read_text(encoding="utf-8"), images)
    content, unplaced = annotate_questions(content, open_q)
    if interactive:  # 의문점 댓글에 답변 버튼
        for q in open_q:
            btns = "".join(f'<button class="qopt" data-q="{_html.escape(q["id"])}" data-a="{_html.escape(o)}">{_html.escape(o)}</button>' for o in q.get("options", []))
            btns += f'<button class="qopt" data-q="{_html.escape(q["id"])}" data-a="__custom">직접 입력</button>'
            content = content.replace(f'<span class="qnote" id="q-{_html.escape(q["id"])}">', f'<span class="qnote" id="q-{_html.escape(q["id"])}"><span style="float:right">{btns}</span>', 1)
    top = ""
    if open_q:
        items = "".join(f'<li><a href="#q-{_html.escape(q["id"])}">❓ {_html.escape(q["id"])}</a> {_html.escape(q.get("question", ""))}'
                        + (" <i>(본문 위치 못 찾음)</i>" if q in unplaced else "") + "</li>" for q in open_q)
        hint = "댓글의 선택지를 누르거나 직접 입력해 주세요." if interactive else "본문의 노란 표시 옆 댓글을 보고 채팅으로 답해 주세요."
        top = f'<div class="qpanel"><b>남은 의문점 {len(open_q)}개</b> — {hint}<ul>{items}</ul></div>'
    fixes = rv.get("auto_fixes", [])
    bottom = ""
    if fixes:
        li = "".join(f"<li><b>({_html.escape(f.get('severity', ''))})</b> {_html.escape(f.get('finding', ''))} → {_html.escape(f.get('fix', ''))}</li>" for f in fixes)
        bottom = f'<details class="fixlog"><summary>자동 수정 내역 — 검수 에이전트 지적 {len(fixes)}건 (참고)</summary><ul>{li}</ul></details>'
    extra_css = INTERACTIVE_CSS if interactive else ""
    banner = ("업로드 전 검토 화면 — 전체를 읽으면서 고치고 싶은 문장을 드래그해 의견을 남기고, 다 보셨으면 오른쪽의 \"검수 완료\" 를 누르세요."
              if interactive else f"업로드 전 로컬 미리보기 — {_html.escape(str(body))} · 위키 실제 모양과 약간 다를 수 있음")
    doc = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
           f"<title>{_html.escape(title)}</title><style>{PREVIEW_CSS}{extra_css}</style>"
           '<script>window.MathJax={tex:{displayMath:[["\\\\[","\\\\]"]]}};</script>'
           '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js"></script></head><body>'
           f'<div id="content"><div class="banner">{banner}</div>'
           + top + f"<h1 style='border:none;font-size:28px'>{_html.escape(title)}</h1>" + content + bottom + "</div>")
    if interactive:
        doc += ('<div id="side"></div><button id="selbtn">💬 수정 요청</button><div id="toast"></div><div class="modal" id="overlay"><div class="box" style="text-align:center;line-height:1.8"></div></div>'
                '<div class="modal" id="modal"><div class="box"><b id="mtitle"></b><div id="mquote" style="color:#5e6c84;font-style:italic;margin-top:6px"></div>'
                '<textarea id="mtext" placeholder="어떻게 고치면 좋을지 적어 주세요"></textarea>'
                '<div style="text-align:right"><button id="mcancel">취소</button><button id="msave" class="primary">저장</button></div></div></div>'
                f"<script>{INTERACTIVE_JS}</script>")
    return doc + "</body></html>", open_q, unplaced, fixes


def cmd_preview(a):
    body = Path(a.file)
    out = Path(a.out) if a.out else body.parent / "preview.html"
    images = {name: os.path.relpath(p.resolve(), out.parent.resolve()) for p, name in parse_attach(attach_specs(a.attach, body))}
    review_path = Path(a.review) if a.review else body.parent / "review.json"
    doc, open_q, unplaced, fixes = build_preview_html(body, images, a.title or "미리보기", review_path)
    out.write_text(doc, encoding="utf-8")
    missing = [n for n in re.findall(r'ri:filename="([^"]+)"', body.read_text(encoding="utf-8")) if n not in images]
    print(f"미리보기 파일: {out.resolve()}  (웹으로 보려면 `serve`)")
    print(f"  의문점 {len(open_q)}개 표시" + (f" (본문 위치 못 찾음 {len(unplaced)}개)" if unplaced else "") + f", 자동 수정 내역 {len(fixes)}건")
    if missing:
        print(f"  ⚠ 이미지 경로가 없는 첨부 {len(set(missing))}개 (--attach 로 지정): {', '.join(sorted(set(missing))[:5])}")


def load_feedback(path):
    p = Path(path)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"items": [], "answers": [], "done_reading": False}


def save_feedback(path, fb):
    Path(path).write_text(json.dumps(fb, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_serve(a):
    import http.server, threading, time, webbrowser, signal
    body = Path(a.file).resolve()
    wd = body.parent
    fb_path = Path(a.feedback) if a.feedback else wd / "feedback.json"
    review_path = Path(a.review) if a.review else wd / "review.json"
    info_path = wd / "serve.json"
    if a.stop:
        if info_path.is_file():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            if info.get("running", True):
                try:
                    os.kill(info["pid"], signal.SIGTERM); print(f"검토 서버 종료 (pid {info['pid']}, {info['url']})")
                except ProcessLookupError:
                    print("이미 종료됨")
            else:
                print("이미 종료됨")
            info["running"] = False
            info_path.write_text(json.dumps(info), encoding="utf-8")
        else:
            print("실행 중인 검토 서버 정보 없음")
        return
    files = {name: p.resolve() for p, name in parse_attach(attach_specs(a.attach, body))}
    title = a.title or "미리보기"
    lock = threading.Lock()
    last = {"t": time.time()}
    done_event = threading.Event()
    fb0 = load_feedback(fb_path)
    fb0["done_reading"] = False  # 새 검토 라운드
    fb0.pop("submitted_at", None)
    save_feedback(fb_path, fb0)
    prev_port = None
    if info_path.is_file():
        try:
            prev_port = json.loads(info_path.read_text(encoding="utf-8")).get("port")
        except Exception:
            pass

    def version():
        m = [body.stat().st_mtime_ns]
        if review_path.is_file():
            m.append(review_path.stat().st_mtime_ns)
        return "-".join(map(str, m))

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, data, ctype):
            if isinstance(data, str):
                data = data.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            last["t"] = time.time()
            path = urllib.parse.urlparse(self.path).path
            if path == "/":
                imgs = {n: "/att/" + urllib.parse.quote(n) for n in files}
                doc = build_preview_html(body, imgs, title, review_path, interactive=True)[0]
                return self.send(200, doc, "text/html; charset=utf-8")
            if path.startswith("/att/"):
                name = urllib.parse.unquote(path[5:])
                if name in files and files[name].is_file():
                    return self.send(200, files[name].read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream")
                return self.send(404, "not found", "text/plain")
            if path == "/api/state":
                with lock:
                    return self.send(200, json.dumps(load_feedback(fb_path), ensure_ascii=False), "application/json")
            if path == "/api/version":
                return self.send(200, json.dumps({"v": version()}), "application/json")
            self.send(404, "not found", "text/plain")

        def do_POST(self):
            last["t"] = time.time()
            path = urllib.parse.urlparse(self.path).path
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or b"{}")
            except json.JSONDecodeError:
                return self.send(400, "bad json", "text/plain")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with lock:
                fb = load_feedback(fb_path)
                if path == "/api/feedback":
                    n = 1 + max([int(i["id"][1:]) for i in fb["items"] if i["id"][1:].isdigit()] or [0])
                    fb["items"].append({"id": f"F{n}", "quote": str(data.get("quote", ""))[:300], "comment": str(data.get("comment", ""))[:4000],
                                        "status": "open", "created": now})
                elif path == "/api/answer":
                    fb["answers"] = [x for x in fb["answers"] if x["qid"] != data.get("qid")]
                    fb["answers"].append({"qid": str(data.get("qid")), "answer": str(data.get("answer", ""))[:2000], "status": "open", "created": now})
                elif path == "/api/done":
                    fb["done_reading"] = True
                    fb["submitted_at"] = now
                    done_event.set()
                else:
                    return self.send(404, "not found", "text/plain")
                save_feedback(fb_path, fb)
            self.send(200, json.dumps(fb, ensure_ascii=False), "application/json")

    server = None
    for port in ([prev_port] if prev_port else []) + list(range(a.port, a.port + 30)):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if server is None:
        raise Fail(f"빈 포트를 찾지 못함 ({a.port}~{a.port + 29})")
    url = f"http://localhost:{server.server_address[1]}/"
    info_path.write_text(json.dumps({"pid": os.getpid(), "url": url, "port": server.server_address[1], "file": str(body), "running": True}), encoding="utf-8")
    print(f"검토 서버: {url}", flush=True)
    print(f"  의견 저장: {fb_path}", flush=True)
    if not a.no_open:
        try:
            if os.environ.get("BROWSER"):  # VS Code 원격: 사용자 PC 브라우저로 열고 포트 자동 연결
                import subprocess
                ok = subprocess.run([os.environ["BROWSER"], url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20).returncode == 0
            else:
                ok = webbrowser.open(url)
            print("  브라우저를 열었어요" if ok else "  브라우저 자동 열기 실패 → 위 주소를 직접 여세요 (VS Code 포트 탭에서도 열 수 있음)", flush=True)
        except Exception:
            print("  브라우저 자동 열기 실패 → 위 주소를 직접 여세요", flush=True)

    def idle_watch():
        while True:
            time.sleep(30)
            if time.time() - last["t"] > a.idle_minutes * 60:
                print(f"{a.idle_minutes}분 동안 접속이 없어 검토 서버 종료", flush=True)
                server.shutdown()
                return
    def done_watch():
        done_event.wait()
        time.sleep(0.8)  # 브라우저 응답이 나간 뒤 종료
        fb = load_feedback(fb_path)
        n_items = sum(1 for i in fb["items"] if i["status"] != "done")
        n_ans = sum(1 for x in fb["answers"] if x["status"] != "applied")
        print(f"검수 완료 제출: 대기 의견 {n_items}건, 의문점 답변 {n_ans}건 → `feedback` 으로 읽어 반영"
              + ("" if n_items + n_ans else " (반영할 것 없음 — 검수 끝)"), flush=True)
        server.shutdown()
    threading.Thread(target=idle_watch, daemon=True).start()
    threading.Thread(target=done_watch, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            info["running"] = False
            info_path.write_text(json.dumps(info), encoding="utf-8")
        except Exception:
            pass


def cmd_feedback(a):
    fb = load_feedback(a.file)
    changed = False
    for fid in a.resolve or []:
        for it in fb["items"]:
            if it["id"] == fid:
                it["status"], it["resolution"] = "done", a.note or "반영함"
                changed = True
    for qid in a.applied or []:
        for x in fb["answers"]:
            if x["qid"] == qid:
                x["status"] = "applied"
                changed = True
    if changed:
        save_feedback(a.file, fb)
    open_items = [i for i in fb["items"] if i["status"] != "done"]
    open_ans = [x for x in fb["answers"] if x["status"] != "applied"]
    print(f"검토 의견: 대기 {len(open_items)} / 전체 {len(fb['items'])}, 의문점 답변 대기 {len(open_ans)}, 다 읽음: {'예' if fb.get('done_reading') else '아니오'}")
    for i in open_items:
        print(f"- {i['id']}: " + (f"“{i['quote'][:120]}” → " if i.get("quote") else "(전체 의견) ") + i["comment"])
    for x in open_ans:
        print(f"- 답변 {x['qid']}: {x['answer']}")


def cmd_publish(a):
    cfg = load_config()
    cl = Client(cfg)
    state_path = Path(a.state)
    state = load_state(state_path)
    storage = Path(a.body).read_text(encoding="utf-8")
    attach = parse_attach(attach_specs(a.attach, a.body))

    # 1) 대상 페이지 결정: --page-id > state > (새 위치의 같은 제목)
    page, how = None, None
    if a.page_id:
        page, how = cl.page(resolve_id(cl, cfg, a.page_id)), "--page-id"
    elif state.get("page_id"):
        try:
            page, how = cl.page(state["page_id"]), "state"
        except Fail as e:
            if "HTTP 404" not in str(e):
                raise
            print(f"경고: 이전에 올린 페이지({state['page_id']})가 삭제됨 → 새로 생성")
            state = {}

    # 2) 위치 결정: --parent (사용자가 고른 위치) > 업데이트면 현재 위치 유지. 기본 위치는 없음.
    if a.parent:
        parent = cl.page(resolve_id(cl, cfg, a.parent))
    elif page is not None:
        parent = cl.page(page["ancestors"][-1]["id"]) if page.get("ancestors") else None
    else:
        raise Fail("새 페이지의 업로드 위치가 지정되지 않음 → `suggest` 로 후보를 보고 사용자가 고른 위치를 --parent 로 지정")
    space = parent["space"]["key"] if parent else page["space"]["key"]

    if page is None:
        same = find_by_title(cl, space, a.title)
        if same:
            p = same[0]
            if not a.adopt:
                raise Fail(
                    f"같은 제목의 페이지가 이미 있음: {p['id']} {cl.page_url(p)}\n"
                    f"이 페이지를 덮어쓰려면 --adopt, 아니면 제목을 바꾸세요."
                )
            page, how = cl.page(p["id"]), "--adopt"
    elif a.title != page["title"]:
        clash = [p for p in find_by_title(cl, space, a.title) if p["id"] != page["id"]]
        if clash:
            raise Fail(f"바꾸려는 제목의 페이지가 이미 있음: {cl.page_url(clash[0])} → 다른 제목을 쓰세요")

    # 3) 동시 수정 보호
    if page is not None:
        cur = page["version"]["number"]
        last = state.get("version") if state.get("page_id") == page["id"] else None
        if not a.force and last is not None and cur > last:
            who = page["version"].get("by", {}).get("displayName", "?")
            raise Fail(
                f"위키에서 수정된 페이지임: 서버 v{cur} (마지막 업로드 v{last}, 수정자 {who}).\n"
                f"그대로 올리면 위키에서 직접 고친 내용이 사라짐. 먼저 `get {page['id']}` 로 반영 후 --force 로 업로드."
            )

    # 4) 본문 검증
    existing = existing_attachments(cl, page["id"]) if page is not None else {}
    report, errors, warnings = check_body(storage, attach, existing)
    for w in warnings:
        print("경고:", w)
    if errors:
        for e in errors:
            print("오류:", e)
        raise Fail("본문 검증 실패 — 업로드하지 않음")

    hashes = {n: sha256(p) for p, n in attach}
    prev = state.get("attachments", {}) if page is not None and state.get("page_id") == page["id"] else {}
    todo = [(p, n) for p, n in attach if not (n in existing and prev.get(n) == hashes[n])]

    cur_parent_id = page["ancestors"][-1]["id"] if page is not None and page.get("ancestors") else None
    move = page is not None and parent is not None and a.parent and parent["id"] != cur_parent_id
    if page is None:
        print(f"대상: [{a.title}] 새로 생성")
        print(f"위치: [{space}] {page_path(parent)} > (새 페이지)")
    else:
        print(f"대상: [{a.title}] 업데이트 (id {page['id']}, v{page['version']['number']} → v{page['version']['number'] + 1}, {how})")
        if page["title"] != a.title:
            print(f"제목 변경: {page['title']} → {a.title}")
        if move:
            print(f"위치 이동: {' > '.join(x['title'] for x in page['ancestors'])} → {page_path(parent)}")
        else:
            print(f"위치: [{space}] {' > '.join(x['title'] for x in page.get('ancestors', []))} (유지)")
    print(f"첨부: 업로드 {len(todo)}개 / 변경 없음 {len(attach) - len(todo)}개")
    print_report(report)
    review_path = Path(a.review) if a.review else state_path.parent / "review.json"
    rv = review_status(review_path, a.body)
    rv_warn = review_warnings(rv, review_path)
    print("검수: " + ("완료" if not rv_warn else "⚠ " + " / ".join(rv_warn) + " — 경고만 하고 진행"))
    if a.dry_run:
        print("(dry-run: 아무것도 업로드하지 않음)")
        return

    body = {"storage": {"value": storage, "representation": "storage"}}
    msg = a.message or "updated by /wiki-ai"
    if page is None:
        page = cl.call("POST", "/rest/api/content", json_body={
            "type": "page", "title": a.title, "space": {"key": space},
            "ancestors": [{"id": parent["id"]}], "body": body,
        })
    else:
        for p, n in todo:
            upload(cl, page["id"], p, n, existing)
            print(f"  첨부 업로드: {n}")
        todo = []
        payload = {
            "id": page["id"], "type": "page", "title": a.title, "space": {"key": space}, "body": body,
            "version": {"number": page["version"]["number"] + 1, "message": msg},
        }
        if move:
            payload["ancestors"] = [{"id": parent["id"]}]
        page = cl.call("PUT", f"/rest/api/content/{page['id']}", json_body=payload)
    for p, n in todo:
        upload(cl, page["id"], p, n, existing)
        print(f"  첨부 업로드: {n}")

    final = cl.page(page["id"])  # 첨부 업로드 후 최종 버전/위치 기록
    url = cl.page_url(final)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    gi = state_path.parent / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    state_path.write_text(json.dumps({
        "page_id": final["id"], "title": a.title, "url": url, "version": final["version"]["number"],
        "space": space, "parent_id": final["ancestors"][-1]["id"] if final.get("ancestors") else None,
        "location": " > ".join(x["title"] for x in final.get("ancestors", [])),
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attachments": {**prev, **hashes},
        "review": {**rv, "warnings": rv_warn, "draft_sha256": draft_hash(a.body)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if final.get("ancestors"):
        record_history(final["ancestors"][-1]["id"], " > ".join(x["title"] for x in final["ancestors"]), final["space"]["key"] if final.get("space") else space)
    print(f"완료: v{final['version']['number']} [{space}] {page_path(final)}\n{url}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("templates", help="참고 페이지 목록과 목차").set_defaults(fn=cmd_templates)
    rd = sub.add_parser("render", help="로컬 초안을 참고 페이지와 같은 형태로 보기")
    rd.add_argument("file")
    rd.add_argument("--mode", choices=["text", "skeleton"], default="text")
    rd.set_defaults(fn=cmd_render)
    g = sub.add_parser("get")
    g.add_argument("page", help="page id, page URL, 'template' or 'parent'")
    g.add_argument("--mode", choices=["text", "outline", "skeleton", "storage"], default="text")
    g.add_argument("--max-chars", type=int, default=0)
    g.set_defaults(fn=cmd_get)
    se = sub.add_parser("search", help="제목으로 페이지 검색 (업로드 위치 찾기)")
    se.add_argument("query")
    se.add_argument("--all-spaces", action="store_true")
    se.add_argument("--limit", type=int, default=15)
    se.set_defaults(fn=cmd_search)
    sg = sub.add_parser("suggest", help="업로드 위치 후보 추천 (근거 포함)")
    sg.add_argument("--keywords", nargs="+", default=[], help="프로젝트 이름·핵심 시스템/모델·도메인 용어")
    sg.add_argument("--state", help="업데이트 모드면 .wiki-ai/state.json (현재 위치를 1순위로)")
    sg.add_argument("--all-spaces", action="store_true")
    sg.add_argument("--limit", type=int, default=5)
    sg.set_defaults(fn=cmd_suggest)
    cd = sub.add_parser("check-draft", help="초안 자동 검사: 근거 장부, 근거 없는 수치, 민감 정보, 위키 대비 변경점")
    cd.add_argument("file")
    cd.add_argument("--project", required=True)
    cd.add_argument("--evidence")
    cd.add_argument("--state")
    cd.add_argument("--page-id")
    cd.add_argument("--out")
    cd.set_defaults(fn=cmd_check_draft)
    pv = sub.add_parser("preview", help="초안을 브라우저용 HTML 로 (사람이 전체를 읽는 용도)")
    pv.add_argument("file")
    pv.add_argument("--attach", nargs="*", default=[])
    pv.add_argument("--title")
    pv.add_argument("--out")
    pv.add_argument("--review", help="검수 기록 (기본: 초안 옆 review.json) — 열린 의문점을 본문에 댓글로 표시")
    pv.set_defaults(fn=cmd_preview)
    sv = sub.add_parser("serve", help="검토용 웹 서버: 브라우저로 미리보기를 열고 드래그로 수정 요청·의문점 답변을 받음")
    sv.add_argument("file", nargs="?", default=".wiki-ai/page.xhtml")
    sv.add_argument("--attach", nargs="*", default=[])
    sv.add_argument("--title")
    sv.add_argument("--review")
    sv.add_argument("--feedback")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--idle-minutes", type=int, default=120)
    sv.add_argument("--no-open", action="store_true")
    sv.add_argument("--stop", action="store_true", help="이 초안 폴더의 검토 서버 종료")
    sv.set_defaults(fn=cmd_serve)
    fbp = sub.add_parser("feedback", help="웹 검토 의견 보기/처리 표시")
    fbp.add_argument("file", nargs="?", default=".wiki-ai/feedback.json")
    fbp.add_argument("--resolve", nargs="*", metavar="FID")
    fbp.add_argument("--note", help="--resolve 에 붙일 처리 내용")
    fbp.add_argument("--applied", nargs="*", metavar="QID", help="반영한 의문점 답변")
    fbp.set_defaults(fn=cmd_feedback)
    rm = sub.add_parser("review-mark", help="검수 기록 갱신: 전체 읽기 완료, 의문점 답변")
    rm.add_argument("review")
    rm.add_argument("--full-read", action="store_true")
    rm.add_argument("--answer", nargs=2, action="append", metavar=("QID", "TEXT"))
    rm.add_argument("--body", help="주면 현재 초안 해시도 갱신")
    rm.set_defaults(fn=cmd_review_mark)
    rs = sub.add_parser("review-stamp", help="검수 기록에 현재 초안 해시 기록")
    rs.add_argument("review")
    rs.add_argument("--body", required=True)
    rs.set_defaults(fn=cmd_review_stamp)
    w = sub.add_parser("where", help="페이지 경로/하위 페이지 확인")
    w.add_argument("page")
    w.set_defaults(fn=cmd_where)
    f = sub.add_parser("find")
    f.add_argument("--title", required=True)
    f.set_defaults(fn=cmd_find)
    v = sub.add_parser("validate")
    v.add_argument("file")
    v.add_argument("--attach", nargs="*", default=[])
    v.add_argument("--offline", action="store_true")
    v.set_defaults(fn=cmd_validate)
    p = sub.add_parser("publish")
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--attach", nargs="*", default=[])
    p.add_argument("--state", default=".wiki-ai/state.json")
    p.add_argument("--page-id")
    p.add_argument("--parent", help="사용자가 고른 업로드 위치(부모 페이지 URL/ID). 새 페이지는 필수, 업데이트 시 지정하면 이동")
    p.add_argument("--message")
    p.add_argument("--adopt", action="store_true", help="같은 제목의 기존 페이지를 덮어쓰기 대상으로 사용")
    p.add_argument("--force", action="store_true", help="위키에서 수정된 페이지라도 덮어쓰기")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--review", help="검수 기록 (기본: state 옆 review.json). 의문점·전체 읽기 미완료면 경고만 출력")
    p.set_defaults(fn=cmd_publish)
    a = ap.parse_args()
    try:
        a.fn(a)
    except Fail as e:
        print(f"실패: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
