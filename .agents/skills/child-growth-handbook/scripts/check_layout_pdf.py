#!/usr/bin/env python3
"""Compare a handbook's editorial geometry with the actual typeset PDF pages."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import fitz
from PIL import Image, ImageChops


ZOOM = 3
LEFT_LIMIT = 1.0
CENTER_LIMIT = 1.5
SIZE_LIMIT = 0.12


def font_name(name):
    return re.sub(r"^[A-Z]{6}\+", "", name).casefold()


def font_matches(name, wanted):
    wanted = font_name(wanted)
    bold = any(x in font_name(name) for x in ("bold", "heavy", "semibold", "demi", "black"))
    if wanted in ("b", "bold", "r", "regular"):
        return bold == (wanted in ("b", "bold"))
    return font_name(name) == wanted


def tidy(text):
    return "".join(text.split())


def inside(rect, x, y, pad=0.08):
    return rect.x0 - pad <= x <= rect.x1 + pad and rect.y0 - pad <= y <= rect.y1 + pad


def rect_ok(rect):
    return rect.is_valid and not rect.is_empty and not rect.is_infinite


@dataclass
class Glyph:
    char: str
    box: fitz.Rect
    x: float
    y: float
    size: float
    font: str
    color: tuple


class Page:
    def __init__(self, page):
        self.page = page
        raster = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
        self.raster = Image.frombytes("RGB", (raster.width, raster.height), raster.samples)
        self.paths = page.get_drawings()
        self.images = [fitz.Rect(im["bbox"]) for im in page.get_image_info()]
        self.rows = defaultdict(list)
        for span in page.get_texttrace():
            if span["type"] not in (0, 1) or span.get("opacity", 1) < 0.1:
                continue
            color = span["color"]
            rgb = (color,) * 3 if isinstance(color, (int, float)) else tuple(color)
            if len(rgb) == 1:
                rgb *= 3
            if len(rgb) != 3:
                raise ValueError("请先将灰度或RGB以外的印刷色转换成同色预览再检查")
            color = tuple(round(c * 255) for c in rgb)
            for cp, _, (x, y), bbox in span["chars"]:
                glyph = Glyph(chr(cp), fitz.Rect(bbox), x, y, span["size"], span["font"], color)
                self.rows[round(y, 1)].append(glyph)
        for row in self.rows.values():
            row.sort(key=lambda g: g.x)

    def lines(self, box):
        found = []
        for y, row in sorted(self.rows.items()):
            if not box.y0 - 2 <= y <= box.y1 + 2:
                continue
            group = [g for g in row if inside(box, (g.box.x0+g.box.x1)/2, g.y - 0.28*g.size)
                     and not g.char.isspace()]
            if group:
                found.append(group)
        return found

    def visible_ink(self, glyphs):
        """Measure the final page pixels matching the actual text paint, including mixed runs."""
        runs = []
        for g in glyphs:
            if not runs or runs[-1][-1].color != g.color:
                runs.append([])
            runs[-1].append(g)
        bounds = None
        for run in runs:
            rect = fitz.Rect(run[0].box)
            for g in run[1:]:
                rect |= g.box
            rect.y0 -= 1.5
            rect.y1 += 1.5
            pixel = (rect * fitz.Matrix(ZOOM, ZOOM)).irect
            image = self.raster.crop(tuple(pixel))
            channels = image.split()
            masks = [band.point([255 if abs(value-target) <= 32 else 0 for value in range(256)])
                     for band, target in zip(channels, run[0].color)]
            mask = ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2])
            ext = mask.getbbox()
            if ext:
                r = fitz.Rect((ext[0]+pixel.x0)/ZOOM,(ext[1]+pixel.y0)/ZOOM,
                              (ext[2]+pixel.x0)/ZOOM,(ext[3]+pixel.y0)/ZOOM)
                bounds = r if bounds is None else bounds | r
        return bounds

    def icon_visible(self, rect):
        # A full-width rule, a zone background or merely declaring an asset is insufficient.
        expanded = rect + (-1.8,-1.8,1.8,1.8)
        placed = any(expanded.contains(r) and r.get_area() >= 0.15*rect.get_area()
                     for r in self.images)
        paths = [p for p in self.paths if expanded.contains(p["rect"]) and len(p["items"])>0]
        vector = any((p["rect"].width >= 0.16*rect.width and p["rect"].height >= 0.16*rect.height)
                     and (p["type"] in ("s", "fs") or len(p["items"])>2) for p in paths)
        pix = self.raster.crop(tuple((rect * fitz.Matrix(ZOOM, ZOOM)).irect)).convert("L")
        hist = pix.histogram()
        # An icon must carry a small but distributed dark detail at its printed size.
        dark = pix.point([255 if v < 175 else 0 for v in range(256)]).getbbox()
        inked = (dark and dark[2]-dark[0]>=pix.width*0.18 and dark[3]-dark[1]>=pix.height*0.18
                 and sum(hist[:175])>=pix.width*pix.height*0.018)
        return bool((placed or vector) and inked)


def compare_source_pages(source, output, changes, errors):
    """Ignore line wrapping / table reading order while guarding per-page character coverage."""
    def glyphs(page):
        return Counter(tidy(page.get_text("text")))

    with fitz.open(source) as original:
        if len(original) != len(output):
            errors.append("页数与原稿不同；页次调整须另作内容映射复核")
            return
        planned = defaultdict(list)
        for item in changes:
            if not item.get("reason") or not (item.get("before") or item.get("after")):
                raise ValueError("计划内文字改动须注明原句、新句和原因")
            if type(item["page"]) is not int or not 1 <= item["page"] <= len(output):
                raise ValueError("计划内文字改动页码无效")
            planned[item["page"]].append(item)
        for n, (before, after) in enumerate(zip(original, output), 1):
            predicted = glyphs(before)
            for item in planned[n]:
                predicted.subtract(tidy(item.get("before", "")))
                predicted.update(tidy(item.get("after", "")))
            observed = glyphs(after)
            if predicted != observed:
                missing = "".join((predicted-observed).elements())
                extra = "".join((observed-predicted).elements())
                errors.append(f"P{n} 与输入稿文字出入：少{missing[:45]!r}，多{extra[:45]!r}")


def check(manifest_path, pdf_path, source_pdf=None):
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {"pdf": pdf_path.name, "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
              "headings": 0, "cells": 0, "max_left_error_pt": 0.0, "max_center_error_pt": 0.0,
              "roles": {}, "errors": []}
    errors = result["errors"]
    metrics = {
        "max_left_error_pt": LEFT_LIMIT,
        "max_center_error_pt": CENTER_LIMIT,
    }
    def measure(name, error, where):
        result[name] = max(result[name], round(error, 3))
        if error > metrics[name]:
            errors.append(f"{where} {name}={error:.2f} pt，允许{metrics[name]:g} pt")
    with fitz.open(pdf_path) as doc:
        if source_pdf is not None:
            compare_source_pages(source_pdf, doc, spec.get("text_changes", []), errors)
            result["source_comparison"] = {"pages": len(doc),
                                           "sha256": hashlib.sha256(source_pdf.read_bytes()).hexdigest()}
        pages = [Page(p) for p in doc]
        registered = defaultdict(list)
        allowed = defaultdict(list)
        for exc in spec.get("exceptions", []):
            if not exc.get("reason"):
                raise ValueError("例外须写明年龄标记、刻度等用途")
            number = int(exc["page"])
            exclusion = fitz.Rect(exc["box"])
            if not 1 <= number <= len(pages) or not rect_ok(exclusion):
                raise ValueError("例外的页码或位置无效")
            if not pages[number-1].page.rect.contains(exclusion):
                raise ValueError("例外区域超出页面")
            if exclusion.get_area() > 0.25 * pages[number-1].page.rect.get_area():
                raise ValueError("请将例外限定为单一标记或刻度")
            allowed[number].append(exclusion)
        if not spec["headings"] or not spec["cells"]:raise ValueError("缺标题或单元格清单")
        def actual(item):
            num = item["page"]
            if type(num) is not int or not 1 <= num <= len(pages):raise ValueError("页码错误")
            p, rect = pages[num-1], fitz.Rect(item["box"])
            if not rect_ok(rect) or not p.page.rect.contains(rect):raise ValueError("区域无效或超出纸边")
            return p, rect
        seen_headings = set()
        for h in spec["headings"]:
            p, rect = actual(h)
            key = (h["page"], h["text"], tuple(rect))
            if key in seen_headings:
                raise ValueError("同一标题重复登记")
            seen_headings.add(key)
            where = f"P{h['page']} 标题“{h['text']}”"
            glyphs = [g for line in p.lines(rect) for g in line]
            if "".join(g.char for g in glyphs) != tidy(h["text"]):
                errors.append(where + " 没有正确排入声明位置")
                continue
            for g in glyphs:
                if abs(g.size-h["size"]) > SIZE_LIMIT or not font_matches(g.font, h["font"]):
                    errors.append(where + " 实际字号/字体与角色声明不符")
                    break
            style = {(round(g.size, 2),font_name(g.font)) for g in glyphs}
            if len(style)!=1:errors.append(where + " 标题内部字号或字体不一致")
            current = sorted(style)
            if result["roles"].setdefault(h["role"], current) != current:
                errors.append(where + " 与相同层级的其它标题字号或字体不同")
            registered[h["page"]].append(rect)
            icon = h.get("icon") or {}
            if not icon.get("name") or not icon.get("box"):
                errors.append(where + " 缺少标题前图标")
                continue
            ir = fitz.Rect(icon["box"])
            if not rect_ok(ir) or not p.page.rect.contains(ir):
                errors.append(where + " 图标框无效")
            elif not glyphs or not p.icon_visible(ir):
                errors.append(where + " 实际页面未找到清晰的图标")
            else:
                optical = p.visible_ink(glyphs)
                if optical is None:errors.append(where + " 标题墨迹不可见")
                else:
                    dx = min(g.x for g in glyphs) - ir.x1
                    dy = abs((ir.y0+ir.y1-optical.y0-optical.y1)/2)
                    if not -0.15 <= dx <= 17 or dy > max(4, h["size"]*.34):
                        errors.append(where + f" 图文间隙/中心偏差异常（{dx:.1f}/{dy:.1f} pt）")
            result["headings"] += 1
        column_anchors = {}
        seen_cells = set()
        for c in spec["cells"]:
            p, rect = actual(c)
            where=f"P{c['page']} {c['table']}/{c.get('row','')}/{c.get('col','')}"
            lines=p.lines(rect)
            wish=[{"text":x} if isinstance(x,str) else x for x in c["lines"]]
            if not wish or ["".join(g.char for g in ln) for ln in lines] != [tidy(ln["text"]) for ln in wish]:
                errors.append(where+" 文字、折行或格内额外文字与清单不符")
                continue
            left=c["left"]
            if not rect.x0 <= left < rect.x1:
                raise ValueError(where + " 左侧锚点越界")
            if not c.get("table") or "row" not in c or "col" not in c:
                raise ValueError(where + " 缺表名、行或列")
            address = (c["page"], c["table"], c["row"], c["col"])
            if address in seen_cells:
                errors.append(where + " 单元格重复登记")
            seen_cells.add(address)
            # Coordinates are measurements, never identifiers. Shifting a whole cell must fail.
            column = (c["page"], c["table"], c["col"], c.get("grid", ""))
            expected_left, expected_edge = column_anchors.setdefault(column, (left, rect.x0))
            if abs(left - expected_left) > LEFT_LIMIT or abs(rect.x0 - expected_edge) > LEFT_LIMIT:
                errors.append(where + " 同一逻辑列的左边界或文字起笔不齐")
            ink=None
            for actual_line, declared in zip(lines,wish):
                measure("max_left_error_pt",abs(actual_line[0].x-left),where)
                visible=p.visible_ink(actual_line)
                if visible is None:
                    errors.append(where+" 实际字色在纸面不可辨")
                    continue
                ink=visible if ink is None else ink|visible
                if 'size' in declared and any(abs(g.size-declared['size'])>SIZE_LIMIT for g in actual_line):
                    errors.append(where+" 格内字号与记录不符")
                if 'font' in declared and any(not font_matches(g.font,declared['font']) for g in actual_line):
                    errors.append(where+" 格内字体与记录不符")
            if ink:
                measure("max_center_error_pt",abs((ink.y0+ink.y1-rect.y0-rect.y1)/2),where)
                if not (rect+(-.5,-.5,.5,.5)).contains(ink):errors.append(where+" 文字画出单元格边界")
            result["cells"]+=1
        for n,p in enumerate(pages,1):
            for row in p.rows.values():
                if any(g.char in ("\ufffd", "\x00") for g in row):
                    errors.append(f"P{n} 含丢字或替代字，核对本龄嵌入字体字库")
                unregistered=[g for g in row if g.size>=15 and font_matches(g.font,'bold') and not g.char.isspace()
                              and not any(inside(r,g.x+.15*g.size,g.y-.33*g.size,1)
                                          for r in registered[n]+allowed[n])]
                if unregistered:
                    errors.append(f"P{n} 未列入标题或图表/年龄例外的大字："+''.join(g.char for g in unregistered))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest',type=Path)
    ap.add_argument('pdf',type=Path)
    ap.add_argument('--also',nargs=2,metavar=('JSON','PDF'),action='append',type=Path,default=[])
    ap.add_argument('--json',type=Path,metavar='REPORT')
    ap.add_argument('--source-pdf', action='append', type=Path, default=[],
                    help='样式改版：按输入册顺序各传一次已确认原稿，用于逐页核对文字数量')
    args=ap.parse_args()
    results=[]; roles={}
    inputs = [(args.manifest, args.pdf)] + args.also
    if args.source_pdf and len(args.source_pdf) != len(inputs):
        ap.error("请按输入顺序为每份成品分别给一个 --source-pdf")
    sources = args.source_pdf or [None] * len(inputs)
    for (manifest, pdf), source in zip(inputs, sources):
        try:
            record=check(manifest,pdf,source)
            for role,style in record['roles'].items():
                if roles.setdefault(role,style)!=style:
                    record['errors'].append(f'跨册同级字号或字体不一致：{role}')
        except (KeyError,TypeError,IndexError,OSError,RuntimeError,ValueError) as ex:
            record={'pdf':pdf.name,'errors':[str(ex)]}
        results.append(record)
        print(('[BLOCK]' if record['errors'] else '[OK]'),pdf.name,record.get('headings',0),'处标题，',
              record.get('cells',0),'个单元格')
        for error in record['errors']:print('  '+error)
    if args.json:
        args.json.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return int(any(r['errors'] for r in results))


if __name__=='__main__':
    raise SystemExit(main())
