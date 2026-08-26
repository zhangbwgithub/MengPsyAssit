#!/usr/bin/env python3
"""examples 目录生成器：按音频分类，文本版(md) + 气泡排版 PDF
用法：python3 build_examples.py <session_id> <audio_label>
产出：/home/houmo/meng/MengPsyAssit/docs/examples/<audio_label>/{全链路产出.md, 全链路产出.pdf}
"""
import json, sqlite3, sys
from datetime import datetime

REPO = "/home/houmo/meng/MengPsyAssit"

def fmt(ms):
    return f"{ms//60000:02d}:{(ms%60000)//1000:02d}"

def build(session_id, audio_label, audio_desc):
    con = sqlite3.connect(f"{REPO}/data/app.db")
    con.row_factory = sqlite3.Row
    segs = con.execute("SELECT seq, speaker, content, start_ms, end_ms FROM segments WHERE session_id=? ORDER BY seq", (session_id,)).fetchall()
    session = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    record = con.execute("SELECT * FROM records WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
    bi = json.loads(record["basic_info"]) if isinstance(record["basic_info"], str) else record["basic_info"]

    # ── 文本版 Markdown ──
    md = []
    md.append(f"# {audio_label} · 全链路产出")
    md.append("")
    md.append(f"> 素材：{audio_desc}")
    md.append(f"> 链路：上传 → paraformer-v2 转写（说话人分离）→ {bi.get('model')} 清理（prompt {bi.get('prompt_version')}）→ {bi.get('model')} 记录生成")
    md.append(f"> 会话 #{session_id} · 生成日期 {datetime.now().strftime('%Y-%m-%d')}")
    md.append("")
    md.append(f"## 一、转写对话稿（{len(segs)} 段，T=咨询师 / P=来访者）")
    md.append("")
    for s in segs:
        md.append(f"**[{fmt(s['start_ms'])}–{fmt(s['end_ms'])}] {s['speaker']}**：{s['content']}")
        md.append("")
    md.append("## 二、清理后文本")
    md.append("")
    md.append(session["cleaned_text"])
    md.append("")
    md.append("## 三、记录卡片")
    md.append("")
    md.append("### 概述")
    md.append("")
    md.append(record["summary"])
    md.append("")
    md.append("### 咨询师的工作")
    md.append("")
    md.append(record["therapist_work"])
    md.append("")
    md.append("### 来访者话题")
    md.append("")
    for t in bi.get("client_reported_topics", []):
        md.append(f"- {t}")
    md.append("")
    md.append("### 元信息")
    md.append("")
    md.append(f"模型：{bi.get('model')} · 提示词版本：{bi.get('prompt_version')} · 会话编号：#{session_id}")
    md.append("")

    import os
    outdir = f"{REPO}/docs/examples/{audio_label}"
    os.makedirs(outdir, exist_ok=True)
    md_path = f"{outdir}/全链路产出.md"
    open(md_path, "w").write("\n".join(md))

    # ── PDF 气泡版 HTML ──
    bubbles = []
    for s in segs:
        cls = "t" if s["speaker"] == "T" else "p"
        who = "咨询师 T" if s["speaker"] == "T" else "来访者 P"
        bubbles.append(
            f'<div class="msg {cls}"><div class="who">{who}'
            f'<span class="ts">#{s["seq"]} · {fmt(s["start_ms"])}–{fmt(s["end_ms"])}</span></div>'
            f'<div class="txt">{s["content"]}</div></div>'
        )
    topics = "".join(f"<li>{t}</li>" for t in bi.get("client_reported_topics", []))
    cleaned_html = "<br>".join(
        line.strip() for line in session["cleaned_text"].splitlines() if line.strip()
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 1.6cm 1.8cm;
  @bottom-center {{ content: counter(page) " / " counter(pages); font-size: 9pt; color: #999; }} }}
body {{ font-family: "Noto Sans CJK SC", sans-serif; font-size: 10pt; color: #222; line-height: 1.55; }}
h1 {{ font-size: 18pt; color: #16213e; border-bottom: 3px solid #3a86ff; padding-bottom: 6px; }}
h2 {{ font-size: 14pt; color: #16213e; border-bottom: 1.5px solid #ddd; padding-bottom: 4px; margin-top: 24px; }}
.meta {{ color: #666; font-size: 9pt; margin: 8px 0 4px; }}
.dialog {{ margin-top: 8px; }}
.msg {{ max-width: 72%; padding: 7px 11px; border-radius: 10px; margin: 7px 0; page-break-inside: avoid; }}
.msg.t {{ background: #eef6ff; border: 1px solid #b6d4fe; margin-right: auto; }}
.msg.p {{ background: #ecfdf5; border: 1px solid #a7f3d0; margin-left: auto; }}
.who {{ font-size: 8.5pt; font-weight: bold; margin-bottom: 2px; }}
.msg.t .who {{ color: #1d4ed8; }}
.msg.p .who {{ color: #047857; }}
.who .ts {{ font-weight: normal; color: #999; margin-left: 6px; }}
.txt {{ font-size: 10pt; }}
.cleaned {{ background: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px; padding: 12px 14px; font-size: 9.5pt; line-height: 1.8; }}
.card {{ border: 1px solid #dbe4f0; border-radius: 10px; background: #f8fafc; padding: 14px 16px; }}
.card h3 {{ font-size: 11pt; color: #1d4ed8; margin: 10px 0 4px; }}
.card h3:first-child {{ margin-top: 0; }}
ul {{ margin: 4px 0; padding-left: 20px; }}
.foot {{ color: #999; font-size: 8.5pt; margin-top: 14px; }}
</style></head><body>
<h1>{audio_label} · 全链路产出</h1>
<p class="meta">素材：{audio_desc}<br>
链路：上传 → paraformer-v2 转写（说话人分离） → {bi.get('model')} 清理（prompt {bi.get('prompt_version')}） → {bi.get('model')} 记录生成 · 会话 #{session_id} · {datetime.now().strftime('%Y-%m-%d')}</p>
<h2>一、转写对话稿（{len(segs)} 段）</h2>
<div class="dialog">{''.join(bubbles)}</div>
<h2>二、清理后文本</h2>
<div class="cleaned">{cleaned_html}</div>
<h2>三、记录卡片</h2>
<div class="card">
<h3>概述</h3><p>{record['summary']}</p>
<h3>咨询师的工作</h3><p>{record['therapist_work']}</p>
<h3>来访者话题</h3><ul>{topics}</ul>
<h3>元信息</h3><p class="meta">模型：{bi.get('model')} · 提示词版本：{bi.get('prompt_version')} · 会话编号：#{session_id}</p>
</div>
<p class="foot">AI 生成内容仅供专业参考 · 测试素材均为合成音频或授权素材，不含真实咨询数据</p>
</body></html>"""

    from weasyprint import HTML
    pdf_path = f"{outdir}/全链路产出.pdf"
    HTML(string=html).write_pdf(pdf_path)
    print(f"OK {audio_label}: {md_path} | {pdf_path}")

if __name__ == "__main__":
    sid, label, desc = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    build(sid, label, desc)
