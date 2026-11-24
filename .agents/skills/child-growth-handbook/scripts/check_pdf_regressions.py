#!/usr/bin/env python3
"""Test Chinese ink in two engines, or compare a single-page cover with its master.

Requires PyMuPDF, pypdf, Pillow, and Poppler's pdftoppm on PATH.
ink sample:  ink handbook.pdf --probe '1:家庭育苗手册' --probe '2:家庭判断'
cover test:  cover handbook.pdf homepage.pdf --json report.json
Exit codes: 0 PASS, 1 FAIL, 2 REVIEW. No network access or QR scanning.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urljoin, urlsplit

try:
    import pymupdf as fitz
    from PIL import Image, ImageChops
    from pypdf import PdfReader
    from pypdf.generic import ContentStream, DecodedStreamObject, NumberObject
except ImportError as error:
    missing_dependency = error.name
else:
    missing_dependency = None

DPI = 144
ENGINES = ("MuPDF", "Poppler")


class Inconclusive(Exception):
    """This input needs an independent check, rather than a speculative verdict."""


def verdict(statuses):
    return "FAIL" if "FAIL" in statuses else "REVIEW" if "REVIEW" in statuses else "PASS"


def render(engine, document, number, directory):
    """Use the same crop box, resolution and white paper in both renderers."""
    if engine == "MuPDF":
        pix = document[number - 1].get_pixmap(dpi=DPI, colorspace=fitz.csRGB, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if not shutil.which("pdftoppm"):
        raise Inconclusive("Poppler pdftoppm 未安装。")
    prefix = directory / "raster"
    try:
        subprocess.run(
            ["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile", "-cropbox",
             "-r", str(DPI), "-png", document.name, str(prefix)],
            capture_output=True, timeout=90, check=True,
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise Inconclusive("Poppler 未完成渲染。") from error
    with Image.open(prefix.with_suffix(".png")) as raster:
        return raster.convert("RGB")


def make_control(source, pages, output):
    """Hide PDF text only; preserve the graphics behind it (including images)."""
    unclear = {}
    done = {}
    with fitz.open(source) as doc:
        for number in pages:
            page = doc[number - 1]
            streams = page.get_contents() + [form[0] for form in page.get_xobjects()]
            for xref in set(streams):
                if xref not in done:
                    stream = DecodedStreamObject()
                    stream.set_data(doc.xref_stream(xref))
                    operators = ContentStream(stream, None)
                    ops = operators.operations
                    # A clipping glyph may affect later graphics. Hiding it would change the backdrop.
                    clipped = any(op == b"Tr" and int(args[0]) >= 4 for args, op in ops)
                    done[xref] = clipped
                    if clipped or not any(op == b"BT" for _, op in ops):
                        continue
                    updated = []
                    for args, op in ops:
                        if op == b"Tr":
                            args = [NumberObject(3)]
                        updated.append((args, op))
                        if op == b"BT":
                            updated.append(([NumberObject(3)], b"Tr"))
                    operators.operations = updated
                    doc.update_stream(xref, operators.get_data())
                if done[xref]:
                    unclear[number] = "页面使用文字裁切，去字底图无法可靠区分印迹。"
        doc.save(output, deflate=True)
    return unclear


def is_han(c):
    return len(c) == 1 and any(lo <= ord(c) <= hi for lo, hi in (
        (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x323AF)))


def occurrences(page, phrase):
    """Locate same-line ordered characters; inspect every occurrence of this literal."""
    flags = fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES
    found = []
    for block in page.get_text("rawdict", flags=flags)["blocks"]:
        for line in block.get("lines", []):
            chars = [(c, span["size"]) for span in line["spans"] for c in span["chars"]]
            whole = "".join(c["c"] for c, _ in chars)
            start = whole.find(phrase)
            while start >= 0:
                if tuple(line["dir"]) != (1, 0):
                    raise Inconclusive("选句含旋转或竖排文字，请手工比对。")
                samples = []
                for c, size in chars[start:start + len(phrase)]:
                    if not is_han(c["c"]):
                        continue
                    # Ignore the neighbouring row and tiny antialiased edges; include the ideograph body.
                    box = fitz.Rect(c["bbox"])
                    inset = 0.055 * box.width
                    box = fitz.Rect(box.x0 + inset, max(box.y0, c["origin"][1] - size * 0.88),
                                    box.x1 - inset, min(box.y1, c["origin"][1] + size * 0.10))
                    box = box * page.rotation_matrix
                    if box.is_empty or not page.rect.contains(box):
                        raise Inconclusive("取样超出页面或没有可测面积。")
                    samples.append((c["c"], box))
                found.append(samples)
                start = whole.find(phrase, start + len(phrase))
    return found


def measure(original, control, page_rect, box):
    if original.size != control.size:
        raise Inconclusive("原页与去字对照图尺寸不同。")
    sx, sy = original.width / page_rect.width, original.height / page_rect.height
    rect = (round(box.x0*sx), round(box.y0*sy), round(box.x1*sx), round(box.y1*sy))
    actual, background = original.crop(rect), control.crop(rect)
    if min(actual.size) < 4:
        return "REVIEW"  # A footprint this small is not diagnostic at this resolution.
    delta = ImageChops.difference(actual, background)
    delta = ImageChops.lighter(ImageChops.lighter(*delta.split()[:2]), delta.getchannel("B"))
    distinct = sum(delta.histogram()[12:])
    if distinct >= max(3, 0.004 * actual.width * actual.height):
        return "PASS"
    if distinct or any(high - low > 12 for low, high in actual.getextrema()):
        return "REVIEW"  # A graphic, raster text or another overlay may already occupy this box.
    return "FAIL"  # Virtually uniform patch, with no significant rendered glyph contribution.


def ink(args, directory):
    items = []
    with fitz.open(args.pdf) as doc:
        requests = []
        for probe in args.probe:
            p, separator, phrase = probe.partition(":")
            if not separator or not p.isdigit() or not 1 <= int(p) <= len(doc) or not any(map(is_han, phrase)):
                raise Inconclusive("取样格式须为有效页码:含中文的短语。")
            requests.append((int(p), phrase))
        blank_path = directory / "without-text.pdf"
        unclear = make_control(args.pdf, sorted({n for n, _ in requests}), blank_path)
        with fitz.open(blank_path) as blank:
            for number in sorted({n for n, _ in requests}):
                page = doc[number - 1]
                rasters, errors = {}, {}
                for engine in ENGINES:
                    try:
                        rasters[engine] = (render(engine, doc, number, directory),
                                           render(engine, blank, number, directory))
                    except Inconclusive as error:
                        errors[engine] = str(error)
                for n, phrase in requests:
                    if n != number:
                        continue
                    item = dict(page=n, phrase=phrase, status="REVIEW")
                    items.append(item)
                    try:
                        if n in unclear:
                            raise Inconclusive(unclear[n])
                        matches = occurrences(page, phrase)
                        if not matches:
                            raise Inconclusive("未定位到同一行的文本短语，可能转曲、断行或内容已变。")
                        item["occurrences"] = len(matches)
                        item["engines"] = {}
                        for engine in ENGINES:
                            if engine in errors:
                                item["engines"][engine] = dict(status="REVIEW", reason=errors[engine])
                                continue
                            counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
                            exceptions = []
                            for i, characters in enumerate(matches, 1):
                                for j, (char, box) in enumerate(characters, 1):
                                    mark = measure(*rasters[engine], page.rect, box)
                                    counts[mark] += 1
                                    if mark != "PASS":
                                        exceptions.append(dict(occurrence=i, glyph=j, char=char, status=mark))
                            item["engines"][engine] = dict(status=verdict([k for k,v in counts.items() if v]),
                                                          counts=counts, exceptions=exceptions)
                        item["status"] = verdict([v["status"] for v in item["engines"].values()])
                    except Inconclusive as error:
                        item["reason"] = str(error)
    return dict(status=verdict([i["status"] for i in items]), probes=items,
                scope="仅核选定中文字符有可见笔画；字形是否正确及实际印刷另行目读。")


def target(destination, reader, pages):
    if isinstance(destination, (str, bytes)):
        named = reader.named_destinations.get(str(destination))
        if named is None:
            raise Inconclusive("具名跳转目的地未解析。")
        destination = named.dest_array
    dest = destination.get_object()
    if not isinstance(dest, list) or not dest:
        raise Inconclusive("无法解释页内跳转目的地。")
    ref = dest[0]
    key = (getattr(ref, "idnum", None), getattr(ref, "generation", None))
    if key not in pages:
        raise Inconclusive("页内链接指向本文件无法解析的页面。")
    return ["page", pages[key], *map(str, dest[1:])]


def hotlinks(path):
    """Read actual Link annotations. Match public/private target values in memory only."""
    reader = PdfReader(path)
    refs = {(p.indirect_reference.idnum, p.indirect_reference.generation): i for i,p in enumerate(reader.pages,1)}
    links = []
    annotations = reader.pages[0].get("/Annots")
    for ref in annotations.get_object() if annotations else []:
        a = ref.get_object()
        if a.get("/Subtype") != "/Link":
            continue
        if "/AA" in a or "/PA" in a:
            raise Inconclusive("链接带额外动作，需人工打开复核。")
        action = a.get("/A")
        if action:
            action = action.get_object()
            if "/Next" in action:
                raise Inconclusive("链接含多步动作，需人工核对。")
            kind = str(action.get("/S"))
            if kind == "/URI" and action.get("/URI"):
                uri = str(action["/URI"])
                # PDF allows relative URLs resolved against its document-level /URI /Base.
                base = reader.root_object.get("/URI", {})
                base = str(base.get_object().get("/Base", "")) if base else ""
                resolved = urljoin(base, uri)
                if not urlsplit(resolved).scheme:
                    raise Inconclusive("相对链接无绝对基址；实际目标取决于部署位置。")
                dest = ["uri", resolved, bool(action.get("/IsMap", False))]
            elif kind == "/GoTo":
                dest = target(action.get("/D"), reader, refs)
            else:
                raise Inconclusive("含非常规链接动作，需要独立复核。")
        elif "/Dest" in a:
            dest = target(a["/Dest"], reader, refs)
        else:
            raise Inconclusive("链接没有明确可解析的动作或目的地。")
        rect = a.get("/Rect")
        if not rect or len(rect) != 4 or rect[0] >= rect[2] or rect[1] >= rect[3]:
            raise Inconclusive("链接区域为空或不可解释。")
        fields = [tuple(round(float(v), 4) for v in a.get(k, [])) for k in ("/Rect", "/QuadPoints")]
        links.append(json.dumps([*fields, int(a.get("/F", 0)), dest], ensure_ascii=False))
    return sorted(links)


def cover(args, directory):
    checks = []
    def add(name, status, **details):
        checks.append(dict(check=name, status=status, **details))

    with fitz.open(args.master) as master, fitz.open(args.derived) as single:
        if not len(master) or not len(single):
            raise Inconclusive("输入中存在空文档。")
        add("single_page", "PASS" if len(single)==1 else "FAIL", pages=len(single))
        a, b = master[0], single[0]
        for name in ("mediabox", "cropbox", "rotation", "rect"):
            add(name, "PASS" if getattr(a,name) == getattr(b,name) else "FAIL")
        a_text, b_text = a.get_text(), b.get_text()
        add("text", "PASS" if a_text == b_text and a_text.strip() else
            "REVIEW" if not a_text.strip() and not b_text.strip() else "FAIL")
        for engine in ENGINES:
            try:
                im1, im2 = (render(engine, d, 1, directory) for d in (master,single))
                same = im1.size == im2.size and ImageChops.difference(im1, im2).getbbox() is None
                add("picture_"+engine, "PASS" if same else "FAIL", dpi=DPI)
            except Inconclusive as error:
                add("picture_"+engine, "REVIEW", reason=str(error))
    try:
        links1, links2 = hotlinks(args.master), hotlinks(args.derived)
        add("links", "PASS" if links1 == links2 else "FAIL", master_count=len(links1), derived_count=len(links2),
            compared="链接数量、点击区域、标志和实际目标；报告不回显目标值。")
    except Inconclusive as error:
        add("links", "REVIEW", reason=str(error))
    except Exception as error:
        add("links", "REVIEW", reason="注释无法可靠解析："+type(error).__name__)
    return dict(status=verdict([item["status"] for item in checks]), checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_subparsers(dest="mode", required=True)
    ip = modes.add_parser("ink", help="在两套引擎中验证目标中文落墨")
    ip.add_argument("pdf", type=Path)
    ip.add_argument("--probe", action="append", required=True, metavar="页码:短语")
    cp = modes.add_parser("cover", help="比对完整册P1和派生首页")
    cp.add_argument("master", type=Path)
    cp.add_argument("derived", type=Path)
    for mode in (ip, cp):
        mode.add_argument("--json", type=Path, help="将结果同时保存为JSON")
    args = parser.parse_args()
    inputs = [args.pdf] if args.mode == "ink" else [args.master, args.derived]
    try:
        if args.json:
            for path in inputs:
                same_path = args.json.resolve() == path.resolve()
                same_file = args.json.exists() and path.exists() and args.json.samefile(path)
                if same_path or same_file:
                    raise Inconclusive("JSON 报告路径与输入 PDF 相同，原件未改动。")
    except (Inconclusive, OSError, RuntimeError) as error:
        print(json.dumps(dict(status="REVIEW", mode=args.mode, reason=str(error)), ensure_ascii=False))
        return 2
    try:
        if missing_dependency:
            raise Inconclusive("缺少依赖："+missing_dependency)
        with TemporaryDirectory(prefix="handbook-pdf-") as temp:
            report = (ink if args.mode=="ink" else cover)(args, Path(temp))
    except Inconclusive as error:
        report = dict(status="REVIEW", reason=str(error))
    except Exception as error:
        # PDF parser errors can contain a private URL. Only expose the type.
        report = dict(status="REVIEW", reason="文件打开或解析未能完成："+type(error).__name__)
    report["mode"] = args.mode
    result = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        pending = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.json.parent, delete=False) as f:
                pending = Path(f.name)
                f.write(result + "\n")
            pending.replace(args.json)
        except OSError:
            print("报告文件保存失败。", file=sys.stderr)
            print(result)
            return 1 if report["status"] == "FAIL" else 2
        finally:
            if pending:
                pending.unlink(missing_ok=True)
    print(result)
    return {"PASS":0,"FAIL":1,"REVIEW":2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
