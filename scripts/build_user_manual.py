"""Build the offline user manual with Python's standard library only.

This renderer supports the deliberately small Markdown subset used in USER_GUIDE.md.
Images are embedded so the generated HTML can be shared as a single file.
"""
from pathlib import Path
import base64
import html
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/USER_GUIDE.md'
TARGET = ROOT / 'docs/USER_GUIDE.html'


def inline(value):
    tokens = []

    def hold(text):
        tokens.append(text)
        return f'\x00{len(tokens)-1}\x00'

    def image(match):
        alt, relative = match.groups()
        path = SOURCE.parent / relative
        raw = path.read_bytes()
        width, height = struct.unpack('>II', raw[16:24])
        data = base64.b64encode(raw).decode('ascii')
        return hold(f'<img loading="lazy" width="{width}" height="{height}" src="data:image/png;base64,{data}" alt="{html.escape(alt, quote=True)}">')

    value = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', image, value)
    value = re.sub(r'`([^`]+)`', lambda m: hold('<code>' + html.escape(m[1]) + '</code>'), value)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: hold(f'<a href="{html.escape(m[2], quote=True)}">{html.escape(m[1])}</a>'), value)
    value = html.escape(value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    value = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', value)
    return re.sub(r'\x00(\d+)\x00', lambda m: tokens[int(m[1])], value)


def render(text):
    lines = text.splitlines()
    parts = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if re.fullmatch(r'<a id="[a-z]+"></a>', line):
            parts.append(line)
        elif match := re.match(r'^(#{1,3}) (.+)$', line):
            level = len(match[1])
            parts.append(f'<h{level}>{inline(match[2])}</h{level}>')
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells):
                    rows.append(cells)
                i += 1
            header = '<tr>' + ''.join(f'<th scope="col">{inline(c)}</th>' for c in rows[0]) + '</tr>'
            body = ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in row) + '</tr>' for row in rows[1:])
            parts.append(f'<div class="table-wrap"><table><thead>{header}</thead><tbody>{body}</tbody></table></div>')
            continue
        elif re.match(r'^\d+\. ', line):
            items = []
            while i < len(lines) and (match := re.match(r'^\d+\. (.*)', lines[i].strip())):
                items.append('<li>' + inline(match[1]) + '</li>')
                i += 1
            parts.append('<ol>' + ''.join(items) + '</ol>')
            continue
        elif line.startswith('> '):
            parts.append('<blockquote><p>' + inline(line[2:]) + '</p></blockquote>')
        else:
            parts.append('<p>' + inline(line) + '</p>')
        i += 1
    return '\n'.join(parts)


STYLE = '''
:root{color-scheme:light;--ink:#28343f;--muted:#617080;--paper:#f7f9fb;--line:#d6dfe7;--accent:#386382}
*{box-sizing:border-box}html{scroll-padding-top:28px}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.9 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif}
a{color:var(--accent);text-underline-offset:3px}aside{position:fixed;inset:0 auto 0 0;width:258px;overflow:auto;padding:34px 22px;border-right:1px solid var(--line);background:#edf1f5}aside .brand{font-weight:800;letter-spacing:.12em;font-size:15px}aside .sub{font-size:13px;color:var(--muted);margin:4px 0 26px}nav a{display:block;font-size:13px;text-decoration:none;line-height:1.55;padding:8px 0}nav a:hover{text-decoration:underline}main{max-width:1090px;padding:54px 62px 90px;margin-left:258px}h1{font-size:36px;line-height:1.35;letter-spacing:-.03em;margin:0 0 20px}h2{font-size:25px;line-height:1.45;margin:58px 0 22px;padding-top:22px;border-top:1px solid var(--line)}h3{font-size:19px;line-height:1.6;margin:30px 0 12px}p{margin:14px 0}li{padding-left:4px;margin:8px 0}ol{padding-left:25px}strong{font-weight:650}img{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:8px;margin:24px 0}blockquote{margin:22px 0;padding:5px 20px;border-left:3px solid #9bac9c;background:#f0f1e9;color:#43534a}code{font-family:ui-monospace,monospace;font-size:.88em;background:#eeede7;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere}.table-wrap{overflow-x:auto;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.75}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:12px 14px}th{background:#e9eee6;font-weight:650}th:first-child,td:first-child{min-width:130px}footer{font-size:13px;color:var(--muted);border-top:1px solid var(--line);margin-top:40px;padding-top:18px}.print{border:1px solid #b9c5ba;border-radius:5px;background:transparent;color:var(--accent);padding:8px 14px;font:inherit;font-size:13px;cursor:pointer;margin-top:20px}
@media(min-width:1450px){main{margin-left:calc(258px + (100vw - 1450px)/2)}}
@media(max-width:900px){aside{position:static;width:auto;padding:24px;border-right:0;border-bottom:1px solid var(--line)}aside nav{display:none}aside .sub{margin-bottom:0}main{margin:0;padding:32px 24px 60px}h1{font-size:30px}}
@media print{body{background:white;font-size:10pt;line-height:1.65}aside{display:none}main{max-width:none;margin:0!important;padding:0}h1{font-size:26pt}h2{font-size:18pt;break-before:page;margin-top:0;padding-top:0;border:0}h3{font-size:13pt;break-after:avoid}table{font-size:9pt}tr,img,blockquote{break-inside:avoid}img{max-height:170mm;width:auto;max-width:100%;margin:12px auto}a{color:inherit}p,li{orphans:3;widows:3}.table-wrap{overflow:visible}.print{display:none}@page{size:A4;margin:18mm}}
'''


def main():
    source = SOURCE.read_text(encoding='utf-8')
    toc = re.findall(r'^\d+\. \[([^\]]+)\]\(#([a-z]+)\)$', source, re.M)
    nav = ''.join(f'<a href="#{anchor}">{n}. {html.escape(title)}</a>' for n, (title, anchor) in enumerate(toc, 1))
    document = '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="PostStudio 0.4.1 本地测试版 完整用户手册：按流程学习导入、取样、配色、工作流、导出与项目分享。"><title>PostStudio · 用户手册</title><style>' + STYLE + '</style></head><body>'
    document += '<aside aria-label="手册导航"><div class="brand">POST / STUDIO</div><div class="sub">用户手册 · 0.4.1 本地测试版 · 离线阅读版</div><nav>' + nav + '</nav><button class="print" onclick="window.print()">打印 / 保存为 PDF</button></aside><main>'
    document += render(source)
    document += '<footer>本页由 USER_GUIDE.md 生成。正文与示例图片均内嵌，可离线阅读；外部来源链接需要网络，其他项目文档链接需要保留文档目录。</footer></main></body></html>\n'
    TARGET.write_text(document, encoding='utf-8')
    print(f'Built {TARGET} ({TARGET.stat().st_size:,} bytes; {len(toc)} chapters)')


if __name__ == '__main__':
    main()
