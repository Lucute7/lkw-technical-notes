#!/usr/bin/env python3
"""Build a standalone, offline notebook with native MathML equations."""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VENDOR = Path(__file__).resolve().parent / "vendor"
if sys.version_info < (3, 10):
    bundled_python = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    if not bundled_python.exists():
        raise RuntimeError("公式转换需要 Python 3.10 或更新版本。")
    os.execv(str(bundled_python), [str(bundled_python), *sys.argv])
sys.path.insert(0, str(VENDOR))
sys.dont_write_bytecode = True
from latex2mathml.converter import convert

CSS = """
:root{color-scheme:light;--ink:#202b35;--muted:#667581;--accent:#17665c;--line:#dee6e3;--paper:#fff;--wash:#f4f7f5}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}
body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.85 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}
aside{position:fixed;inset:0 auto 0 0;width:270px;padding:38px 25px;overflow:auto;background:#edf3ef;border-right:1px solid var(--line)}
.brand{font-size:21px;font-weight:700;letter-spacing:.04em}.tagline{font-size:13px;color:var(--muted);margin:8px 0 26px}
nav a{display:block;padding:7px 0;text-decoration:none;font-size:14px}nav .chapter{padding-left:14px;font-size:13px}nav .category{margin-top:14px;font-weight:650}
main{max-width:1160px;padding:36px 42px 100px;margin-left:270px}
.reader-header{padding:8px 4px 26px;color:var(--muted);font-size:14px}.reader-header strong{color:var(--accent)}
article{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:36px 46px;margin-bottom:30px;overflow-wrap:anywhere}
h1,h2,h3{line-height:1.5;scroll-margin-top:28px}h1{font-size:28px;margin:0 0 25px;font-weight:700}h2{font-size:21px;margin:35px 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line)}h3{font-size:17px;margin:25px 0 10px}
p{margin:13px 0}li{margin:7px 0}ul,ol{padding-left:1.6em}blockquote{margin:20px 0;padding:4px 18px;border-left:3px solid #a6c6b9;color:var(--muted);background:#f6f9f7}
.table-wrap{overflow:auto;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:11px 13px;text-align:left;vertical-align:top;border:1px solid var(--line)}th{background:#f0f5f2;font-weight:600}
pre{overflow:auto;padding:20px;background:#f2f5f6;border:1px solid var(--line);border-radius:7px;line-height:1.6;font-size:13px}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#f0f3f3;border-radius:3px;padding:2px 4px}pre code{padding:0;background:none}
.equation{overflow-x:auto;overflow-y:hidden;margin:25px 0;padding:19px 15px;background:#f7faf8;border-radius:7px;text-align:center;font-size:1.18em}
math{font-family:"STIX Two Math","Cambria Math","Latin Modern Math",math;font-size:1.08em}math[display=block]{margin:0;white-space:nowrap}td math,th math{font-size:1.12em}
.back{display:block;font-size:12px;margin-top:28px;color:var(--muted)}
@media(max-width:1000px){aside{width:220px;padding:25px 18px}main{margin-left:220px;padding:24px}article{padding:28px}}
@media(max-width:700px){aside{position:relative;width:100%;max-height:none;border-right:0;border-bottom:1px solid var(--line);padding:22px}nav{display:grid;grid-template-columns:1fr 1fr;gap:0 15px}.tagline{margin-bottom:14px}main{margin-left:0;padding:16px}article{padding:23px 19px}h1{font-size:24px}.equation{padding:15px 8px}}
@media print{aside,.reader-header,.back{display:none}main{max-width:none;margin:0;padding:0}body{background:white;font-size:11pt}article{border:0;padding:0;margin:0;break-before:page}article:first-of-type{break-before:auto}pre{white-space:pre-wrap}h1,h2,h3{break-after:avoid}.equation,tr{break-inside:avoid}}
"""


def section_id(path: Path) -> str:
    return "doc-" + hashlib.sha1(path.relative_to(ROOT).as_posix().encode()).hexdigest()[:12]


def documents() -> list[Path]:
    paths = [ROOT / "README.md", ROOT / "复习清单.md"]
    for folder in sorted(ROOT.iterdir()):
        if folder.is_dir() and re.match(r"^\d+_", folder.name):
            index = folder / "README.md"
            if index.exists():
                paths.append(index)
            paths.extend(sorted(p for p in folder.rglob("*.md") if p != index))
    # Repository usage belongs to documentation, after the technical chapters.
    docs = ROOT / "说明文档"
    index = docs / "README.md"
    if index.exists():
        paths.append(index)
        paths.extend(sorted(p for p in docs.rglob("*.md") if p != index))
    return paths


def prepare_math(text: str) -> tuple[str, dict[str, tuple[str, bool]]]:
    formulas: dict[str, tuple[str, bool]] = {}
    # Preserve actual program examples. Convert display and inline math separately.
    pattern = re.compile(r"```[^\n]*\n[\s\S]*?```|`[^`\n]+`|(?<!\\)\$\$([\s\S]+?)\$\$|(?<![\\$])\$(?!\$)([^\n$]+?)(?<!\\)\$(?!\$)")

    def replace(match: re.Match) -> str:
        if match.group(1) is None and match.group(2) is None:
            return match.group(0)
        display = match.group(1) is not None
        tex = (match.group(1) if display else match.group(2)).strip()
        # GitHub's explicit inline-math delimiters keep adjacent CJK punctuation
        # from leaving individual symbols unrendered. These are not code spans.
        if not display and tex.startswith("`") and tex.endswith("`"):
            tex = tex[1:-1].strip()
        # The web preview rejects this macro even though the local converter accepts it.
        if re.search(r"\\operatorname\b", tex):
            raise ValueError(f"公式含网页预览不兼容的 operatorname，请改用正体名称：{tex}")
        markup = convert(tex, display="block" if display else "inline")
        # Reject untranslated commands instead of silently displaying formula source.
        plain = "".join(ET.fromstring(markup).itertext())
        if re.search(r"\\[a-zA-Z]+", plain):
            raise ValueError(f"公式含未转换命令：{tex}")
        token = f"MATHPLACEHOLDER{len(formulas):06d}END"
        formulas[token] = (markup, display)
        return f"\n\n{token}\n\n" if display else token

    return pattern.sub(replace, text), formulas


def node_runtime() -> str:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    node = str(bundled) if bundled.exists() else shutil.which("node")
    if not node:
        raise RuntimeError("未找到 Node.js，无法生成阅读版。")
    return node


def main() -> None:
    paths = documents()
    prepared = [prepare_math(path.read_text(encoding="utf-8")) for path in paths]
    javascript = """
import {marked} from './tools/vendor/marked.mjs';
let raw = ''; for await (const chunk of process.stdin) raw += chunk;
const results = JSON.parse(raw).map(source => marked.parse(source, {gfm:true}));
process.stdout.write(JSON.stringify(results));
"""
    rendered = json.loads(subprocess.run(
        [node_runtime(), "--input-type=module", "-e", javascript],
        cwd=ROOT, input=json.dumps([item[0] for item in prepared]),
        text=True, capture_output=True, check=True,
    ).stdout)
    known = {p.resolve(): section_id(p) for p in paths}
    articles, navigation = [], []
    for path, markup, (_, formulas) in zip(paths, rendered, prepared):
        for token, (mathml, display) in formulas.items():
            if display:
                exact = f"<p>{token}</p>"
                if exact not in markup:
                    raise ValueError(f"独立公式未能放入正文：{path.name}")
                markup = markup.replace(exact, f'<div class="equation">{mathml}</div>')
            else:
                markup = markup.replace(token, mathml)

        def rewrite_link(match: re.Match) -> str:
            target = unquote(html.unescape(match.group(1)))
            local = target.split("#", 1)[0]
            if local.endswith(".md") and "://" not in local:
                dest = (path.parent / local).resolve()
                if dest not in known:
                    if not dest.exists():
                        raise ValueError(f"链接目标不存在：{path.name} → {target}")
                    return 'href="' + html.escape(dest.relative_to(ROOT).as_posix(), quote=True) + '"'
                return f'href="#{known[dest]}"'
            if local == "阅读版.html":
                return 'href="#top"'
            return match.group(0)

        markup = re.sub(r'href="([^"]+)"', rewrite_link, markup)
        markup = markup.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        if "MATHPLACEHOLDER" in markup:
            raise ValueError(f"残留公式占位符：{path.name}")
        title = re.search(r"^# (.+)$", path.read_text(encoding="utf-8"), re.M).group(1)
        kind = "category" if path.name == "README.md" and path.parent != ROOT else "chapter" if path.parent != ROOT else ""
        navigation.append(f'<a class="{kind}" href="#{section_id(path)}">{html.escape(title)}</a>')
        articles.append(f'<article id="{section_id(path)}">{markup}<a class="back" href="#top">返回目录 ↑</a></article>')

    output = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>个人技术栈笔记 · 阅读版</title><style>' + CSS + '</style></head><body id="top">'
    output += '<aside><div class="brand">个人技术栈笔记</div><p class="tagline">持续整理 · 理解原理 · 随时复习</p><nav>' + "".join(navigation) + '</nav></aside>'
    output += '<main><div class="reader-header"><strong>笔记阅读版</strong>　公式已排版 · 离线可读</div>' + "".join(articles) + '</main></body></html>'
    target = ROOT / "阅读版.html"
    target.write_text(output, encoding="utf-8")
    count = sum(len(item[1]) for item in prepared)
    print(f"已生成 {target.name}：{len(paths)} 篇文档，{count} 处数学表达式。")


if __name__ == "__main__":
    main()
