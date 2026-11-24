#!/usr/bin/env python3
"""Read-only editorial-label check. 0 clear, 1 label, 2 review, 3 read error."""

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from xml.etree import ElementTree


EXPLICIT = re.compile(
    r"排版提案|重排提案|排版草稿|内部(?:讨论稿|审阅稿|校样|草稿|初稿|样[稿张册]|稿件)|"
    r"纸面试读|排版试读|排版样[张稿]|试排版|(?:内部|送审|待审|评审|校对)版|仅供(?:审阅|校对|评审|内部传阅)|"
    r"待(?:排版|校对|定稿|终审|补(?:插图|图))|草稿版|征求意见稿|排版校样|占位(?:文字|文案|文本|图片|图)|"
    r"预览版|测试版|校对稿"
)
AMBIGUOUS = re.compile(r"草稿|初稿|样稿|样张|样页|样册|试行稿|评审稿|送审稿|校样|讨论稿|审阅稿|试读稿|校对稿|待审|试读版|试排稿")
# These words also appear in ordinary instructions about writing or art.
LEARNING = re.compile(r"草稿(?:纸|本|箱)|(?:打|写|画|修改|自己的|作文的)草稿")
LABEL = re.compile(
    r"^(?:版本|状态|文件状态)?[：:_/｜|（(\[【\s\-]*"
    r"(?:草稿|初稿|样稿|样张|样页|样册|校样|待审|提案|试读|试行稿|评审稿|送审稿|审阅稿|讨论稿|试读稿|试读版)"
    r"[.\d\s_vV版）)\]】\-]*$"
)
EN_EXPLICIT = re.compile(
    r"\b(?:internal\s+(?:draft|proof)|draft\s+(?:version|copy)|"
    r"for\s+(?:internal\s+)?review\s+only|layout\s+proposal|work\s+in\s+progress)\b",
    re.I,
)
EN_DRAFT = re.compile(r"(?<![A-Za-z])draft(?![A-Za-z])", re.I)
EN_LABEL = re.compile(r"^\W*(?:status\s*[:=]\s*)?(?:draft|wip|proof)\s*[-_.v\d\s]*$", re.I)
INVISIBLE = str.maketrans("", "", "\u200b\u200c\u200d\ufeff\u00ad")
STATUS = ["CLEAR", "BLOCK", "REVIEW", "ERROR"]


def clean(text):
    return unicodedata.normalize("NFKC", text).translate(INVISIBLE).strip()


def classify(value, *, title=False):
    line = clean(value)
    if not line:
        return
    compact = "".join(line.split())
    english = re.sub(r"(?<![a-z])d\s+r\s+a\s+f\s+t(?![a-z])", "draft", line, flags=re.I)
    if EXPLICIT.search(compact) or LABEL.fullmatch(compact) or EN_EXPLICIT.search(english) or EN_LABEL.fullmatch(english):
        return 1
    if AMBIGUOUS.search(LEARNING.sub("", compact)) or EN_DRAFT.search(english):
        if title and (re.search(r"(?:手册|指南|版本)[_·./()【】: -]*(?:草稿|初稿|样[稿册]|校样|审阅稿)(?!纸|本|箱)", compact)
                      or re.search(r"(?:^|[ /_\-.])draft(?:$|[ /_\-.])", english, re.I)):
            return 1
        return 2


def scan_pdf(path, fitz):
    issues = []

    def add(level, location, value):
        snippet = " ".join(str(value).split())
        if len(snippet) > 125:
            snippet = snippet[:122] + "..."
        issues.append((level, location, snippet))

    def check(location, value, *, title=False):
        if isinstance(value, str) and (level := classify(value, title=title)):
            add(level, location, value)

    # Treat filename tokens separated by common version delimiters as labels, too.
    check("文件名", path.stem, title=True)
    for token in re.split(r"[_\[\]()（）【】｜|\-]", path.stem):
        if token != path.stem and classify(token) == 1:
            add(1, "文件名标记", token)

    with fitz.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass or doc.page_count < 1:
            raise ValueError("文件不是可读取的非空、免密码 PDF")
        for key, value in (doc.metadata or {}).items():
            check("属性/" + key, value, title=key in ("title", "subject"))
        raw_xmp = doc.get_xml_metadata()
        if raw_xmp:
            try:
                xml = ElementTree.fromstring(raw_xmp)
            except ElementTree.ParseError:
                add(2, "XMP", "属性结构异常，需人工核对")
            else:
                for node in xml.iter():
                    name = node.tag.rsplit("}", 1)[-1]
                    check("XMP/" + name, node.text, title=name in ("title", "subject", "li"))
                    for key, value in node.attrib.items():
                        check("XMP/" + name + "/@" + key.rsplit("}", 1)[-1], value)

        for _, heading, page_number in doc.get_toc():
            check(f"书签/第{page_number}页", heading, title=True)
        for index, page in enumerate(doc, start=1):
            prefix = f"第{index}页"
            body = page.get_text("text")
            for line in body.splitlines():
                check(prefix + "/文字", line)
            # Some PDFs split individual Han glyphs into separate text lines.
            compact_body = "".join(clean(body).split())
            for match in set(EXPLICIT.findall(compact_body)):
                if not any(match in "".join(clean(line).split()) for line in body.splitlines()):
                    add(1, prefix + "/跨行文字", match)
            if not body.strip():
                add(2, prefix, "无可提取正文，须渲染人工检查")
            elif any(fitz.Rect(info["bbox"]).get_area() >= 0.75 * page.rect.get_area()
                     for info in page.get_image_info()):
                add(2, prefix, "含近整页图片，须人工读图确认水印与页眉页脚")
            for annot in page.annots() or ():
                for key in ("content", "title", "subject"):
                    check(prefix + "/批注/" + key, annot.info.get(key))
            for widget in page.widgets() or ():
                check(prefix + "/表单标签", widget.field_label)
                check(prefix + "/表单文字", widget.field_value)
    return list(dict.fromkeys(issues))


def main():
    parser = argparse.ArgumentParser(
        description="扫描 PDF 中的制作状态词。人工逐页渲染核验仍需独立完成。"
    )
    parser.add_argument("pdf", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        import fitz
    except ImportError:
        print("缺少 PyMuPDF，请在当前 Python 环境安装 PyMuPDF。", file=sys.stderr)
        return 3

    levels = set()
    for path in args.pdf:
        try:
            issues = scan_pdf(path, fitz)
        except Exception as exc:
            issues = [(3, "读取失败", str(exc))]
        found = {item[0] for item in issues}
        status = next((i for i in (3, 1, 2) if i in found), 0)
        levels.add(status)
        print(f"[{STATUS[status]}] {path.name}")
        for level, location, message in issues:
            print(f"  {STATUS[level]} {location}  {message}")
    print("文字检查之外，须逐页查看渲染图，核对插图或轮廓字中的水印和边角文字。")
    return next((i for i in (3, 1, 2) if i in levels), 0)


if __name__ == "__main__":
    sys.exit(main())
