#!/usr/bin/env python3
"""检查分龄手册的备选覆盖、资产引用及编辑审签。仅使用 Python 标准库。"""
import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MINIMUM = {"info": 10, "image": 10, "resource": 10, "icon": 3, "reuse": 1}
STAGES = ["content", "visual", "digital"]
PLACEHOLDERS = {"example.org", "example.com", "example.net", "localhost"}


def label_key(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def locator_key(ref, base):
    """Return a canonical locator or a file digest, failing closed on missing local files."""
    if not nonempty(ref):
        raise ValueError("缺少真实网址或文件位置")
    pathpart, _, fragment = ref.strip().partition("#")
    parsed = urlsplit(pathpart)
    if parsed.scheme in {"http", "https"}:
        if (not parsed.hostname or parsed.hostname.lower() in PLACEHOLDERS
                or any(parsed.hostname.lower().endswith("." + n) for n in PLACEHOLDERS)):
            raise ValueError("来源网址无效")
        params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                  if not k.lower().startswith("utm_")]
        if Path(parsed.path).suffix.lower() in {".png", ".webp", ".jpg", ".jpeg", ".svg", ".gif"}:
            fragment = ""
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"),
                           urlencode(sorted(params)), fragment))
    path = (base / pathpart).resolve()
    if not pathpart or not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"本地文件不存在或为空 {ref}")
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(262144), b""):
            digest.update(chunk)
    # A named item in a contact sheet or bibliography can be checked by its locator.
    # A single image file remains the same artwork despite alternate anchors.
    if path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg", ".svg", ".gif", ".tif", ".tiff"}:
        fragment = ""
    return f"{digest.hexdigest()}#{fragment}"


def check_slots(items, base, errors):
    if not isinstance(items, list) or not items:
        errors.append("缺少非空 slots 列表")
        return {}
    inventory = {}
    for pos, slot in enumerate(items, 1):
        if not isinstance(slot, dict):
            errors.append(f"位置{pos}格式错误")
            continue
        sid, kind = slot.get("id"), slot.get("kind")
        if not nonempty(sid) or sid in inventory or kind not in MINIMUM:
            errors.append(f"位置{pos}编号重复、缺失或分类错误")
            continue
        inventory[sid] = kind
        if not nonempty(slot.get("prompt")) or not nonempty(slot.get("why")):
            errors.append(f"{sid} 缺少栏目要解决的问题或采用理由")
        rows = slot.get("candidates")
        if not isinstance(rows, list):
            errors.append(f"{sid} 缺少 candidates 列表")
            continue
        ids, labels, refs = set(), set(), set()
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict) or not all(nonempty(row.get(k)) for k in ("id", "label", "reason", "ref")):
                errors.append(f"{sid}/{index} 缺少候选编号、图样或动作名称、取舍理由或来源")
                continue
            ident, name = row["id"], label_key(row["label"])
            if ident in ids or name in labels or not name:
                errors.append(f"{sid}/{ident} 编号或规范化名称重复或为空")
            ids.add(ident)
            labels.add(name)
            try:
                key = locator_key(row["ref"], base)
            except (ValueError, OSError) as exc:
                errors.append(f"{sid}/{ident} {exc}")
                continue
            if kind in {"image", "resource", "icon"} and key in refs:
                errors.append(f"{sid}/{ident} 使用了与本位置其他候选相同的图样或资源定位")
            refs.add(key)
        if len(ids) < MINIMUM[kind]:
            errors.append(f"{sid} 需要至少{MINIMUM[kind]}个有效候选，现有{len(ids)}个")
        if not nonempty(slot.get("winner")) or slot["winner"] not in ids:
            errors.append(f"{sid} winner 必须是唯一选中候选的编号")
    return inventory


def check_release(data, actual, base, errors):
    listed = data.get("inventory")
    if not isinstance(listed, list) or not all(isinstance(x, dict) and nonempty(x.get("id"))
                                               and x.get("kind") in MINIMUM for x in listed):
        errors.append("缺少预先编好的有效 inventory")
    else:
        expected = {i["id"]: i["kind"] for i in listed}
        if expected != actual or len(expected) != len(listed):
            errors.append("预列与实审位置的编号、类型或数量不一致")
    if not nonempty(data.get("author")):
        errors.append("缺少编者标识")
    reviews = data.get("reviews")
    if not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews):
        errors.append("缺少审签记录")
    elif [r.get("stage") for r in reviews] != STAGES:
        errors.append("请依次提交内容、视觉、数字终检三次审签结果")
    else:
        for r in reviews:
            stage = r["stage"]
            reviewer = r.get("reviewer")
            if r.get("status") != "pass" or not nonempty(reviewer):
                errors.append(f"{stage} 未获通过或缺少复核人")
            elif stage in {"content", "visual"} and label_key(reviewer) == label_key(data.get("author") or ""):
                errors.append(f"{stage} 应由独立于本册制作者的复核者签核")
            try:
                locator_key(r.get("evidence"), base)
            except (ValueError, OSError) as exc:
                errors.append(f"{stage} 审签记录无可定位证据：{exc}")
    fieldwork = data.get("fieldwork", {})
    if not isinstance(fieldwork, dict):
        errors.append("fieldwork 应分别记录实印、微信实扫和家长试读")
        return
    for test, result in fieldwork.items():
        if not isinstance(result, dict) or result.get("status") not in {"pending", "done"}:
            errors.append(f"{test} 实测状态无效")
        elif result["status"] == "done":
            try:
                locator_key(result.get("evidence"), base)
            except (ValueError, OSError) as exc:
                errors.append(f"{test} 实测缺证：{exc}")


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+", help="按授权顺序传入各龄 JSON")
    parser.add_argument("--release", action="store_true", help="同时检查预列位置与独立审签")
    parser.add_argument("--order", help="指定项目要求的顺序，例如 3,4,5")
    args = parser.parse_args()
    ages, failed = [], False
    for file in args.files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("根记录须为对象")
            errors = []
            age = data.get("age")
            if type(age) is not int or not 3 <= age <= 18:
                errors.append("age 须为3至18周岁整数")
            if not all(nonempty(data.get(k)) for k in ("previous", "next")):
                errors.append("缺少上龄承接或下龄方向")
            ages.append(str(age))
            actual = check_slots(data.get("slots"), file.parent, errors)
            if args.release:
                check_release(data, actual, file.parent, errors)
        except (ValueError, OSError, TypeError) as exc:
            errors = [str(exc)]
        if errors:
            print(f"[BLOCK] {file}: " + "；".join(errors))
            failed = True
        else:
            print(f"[OK] {age}岁 {len(actual)}个位置。表内记录通过；语义质量须独立评读，家庭实测以实证为准。")
    if args.order and ages != [x.strip() for x in args.order.split(",")]:
        print("[BLOCK] 文件顺序或年龄与 --order 的项目清单不一致")
        failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(run())
