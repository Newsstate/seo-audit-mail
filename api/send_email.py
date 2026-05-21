"""
/api/send_email  POST {job_id, email}
Fetches audit result from Redis and emails:
  1. Summary HTML email body
  2. Full report as an attached .html file (opens in browser)

Required Vercel env vars:
  SMTP_HOST  SMTP_PORT  SMTP_USER  SMTP_PASS  SMTP_FROM
"""
import json, os, re, smtplib, ssl, urllib.request, urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email.mime.application import MIMEApplication
from email                import encoders
from http.server          import BaseHTTPRequestHandler


# ── Redis ─────────────────────────────────────────────────────────────────────

def get_redis():
    url   = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    try:
        from upstash_redis import Redis
        return Redis(url=url, token=token)
    except Exception:
        return None

def store_get(job_id):
    r = get_redis()
    if not r:
        return None
    try:
        v = r.get(f"seo:{job_id}")
        return json.loads(v) if v else None
    except Exception:
        return None

def valid_email(addr):
    return bool(re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$', addr.strip()))


# ── Summary email body ────────────────────────────────────────────────────────

def build_summary_html(D, name, report_email):
    domain = D.get("domain", "your website")
    ov     = D.get("overall", {})
    grade  = ov.get("grade", "—")
    summary= ov.get("summary", "")
    cats   = D.get("cats", [])
    recs   = D.get("recommendations", [])
    op     = D.get("op", {})

    gc = ("#1e8449" if grade in ["A+","A","A-","B+"] else
          "#b7770d" if grade in ["B","B-","C+","C"] else "#c0392b")

    cat_rows = "".join(
        f'<tr><td style="padding:8px 12px;font-size:13px;color:#1c2b3a">{c.get("lbl","")}</td>'
        f'<td style="padding:8px 12px;font-size:13px;font-weight:700;color:{gc}">{c.get("grade","—")}</td></tr>'
        for c in cats
    )
    rec_rows = "".join(
        f'<tr><td style="padding:6px 0;vertical-align:top;width:24px">'
        f'<span style="display:inline-block;width:20px;height:20px;border-radius:50%;'
        f'background:#b7770d;color:#fff;font-size:10px;font-weight:700;text-align:center;line-height:20px">'
        f'{r.get("priority",i+1)}</span></td>'
        f'<td style="padding:6px 0 6px 10px">'
        f'<div style="font-size:13px;font-weight:600;color:#1c2b3a;margin-bottom:3px">{r.get("title","")}</div>'
        f'<div style="font-size:12px;color:#5d6d7e;line-height:1.6">{r.get("detail","")}</div></td></tr>'
        for i, r in enumerate(recs[:6])
    )
    title_t = (op.get("title") or {}).get("t", "—")
    meta_t  = (op.get("meta")  or {}).get("t", "—")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<title>SEO Audit — {domain}</title></head>
<body style="margin:0;padding:0;background:#eef0f4;font-family:'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef0f4;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

<tr><td style="background:linear-gradient(135deg,#c0392b,#922b21);border-radius:16px 16px 0 0;padding:30px 34px;color:#fff">
  <div style="font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;opacity:.7;margin-bottom:8px">SEO Audit Report</div>
  <div style="font-size:22px;font-weight:700;margin-bottom:6px">Website Report for {domain}</div>
  <div style="font-size:13px;opacity:.8">Prepared for {name}</div>
</td></tr>

<tr><td style="background:#fff;padding:28px 34px;border-bottom:1px solid #eee">
  <table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:middle">
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;color:#95a5a6;margin-bottom:6px">Overall Grade</div>
      <div style="font-size:52px;font-weight:700;color:{gc};line-height:1">{grade}</div>
    </td>
    <td style="vertical-align:middle;padding-left:28px">
      <div style="font-size:13.5px;color:#1c2b3a;line-height:1.65">{summary}</div>
    </td>
  </tr></table>
</td></tr>

<tr><td style="background:#fff;padding:0 34px 24px">
  <div style="font-size:11px;font-weight:600;text-transform:uppercase;color:#95a5a6;margin-bottom:12px">Category Scores</div>
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:10px;overflow:hidden">
    <thead><tr style="background:#f8f9fb">
      <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;color:#95a5a6;font-weight:600">Category</th>
      <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;color:#95a5a6;font-weight:600">Grade</th>
    </tr></thead>
    <tbody>{cat_rows}</tbody>
  </table>
</td></tr>

<tr><td style="background:#fff;padding:0 34px 24px;border-bottom:1px solid #eee">
  <div style="font-size:11px;font-weight:600;text-transform:uppercase;color:#95a5a6;margin-bottom:12px">Key On-Page Findings</div>
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td style="padding:8px 0;border-bottom:1px solid #f0f2f5">
      <div style="font-size:11px;color:#95a5a6;margin-bottom:3px">TITLE TAG</div>
      <div style="font-size:13px;color:#1c2b3a">{title_t[:80]}{"..." if len(title_t)>80 else ""}</div>
    </td></tr>
    <tr><td style="padding:8px 0">
      <div style="font-size:11px;color:#95a5a6;margin-bottom:3px">META DESCRIPTION</div>
      <div style="font-size:13px;color:#1c2b3a">{meta_t[:120]}{"..." if len(meta_t)>120 else ""}</div>
    </td></tr>
  </table>
</td></tr>

<tr><td style="background:#fff;padding:24px 34px;border-bottom:1px solid #eee">
  <div style="font-size:11px;font-weight:600;text-transform:uppercase;color:#95a5a6;margin-bottom:14px">🎯 Priority Recommendations</div>
  <table width="100%" cellpadding="0" cellspacing="0"><tbody>{rec_rows}</tbody></table>
</td></tr>

<tr><td style="background:#fff;padding:20px 34px;text-align:center;border-bottom:1px solid #eee">
  <div style="font-size:13px;color:#5d6d7e;">
    📎 <strong>Your full detailed report is attached</strong> as an HTML file.<br/>
    Download and open it in your browser to view all sections.
  </div>
</td></tr>

<tr><td style="background:#f8f9fb;border-radius:0 0 16px 16px;padding:18px 34px;border-top:1px solid #eee">
  <div style="font-size:12px;color:#95a5a6">
    SEO Audit for <strong style="color:#c0392b">{domain}</strong> · Powered by Claude AI<br/>
    Sent to {report_email}
  </div>
</td></tr>

</table></td></tr></table>
</body></html>"""


def build_summary_text(D, name):
    domain  = D.get("domain", "your website")
    ov      = D.get("overall", {})
    cats    = D.get("cats", [])
    recs    = D.get("recommendations", [])
    cat_str = "\n".join(f"  {c.get('lbl')}: {c.get('grade')}" for c in cats)
    rec_str = "\n".join(
        f"  {i+1}. {r.get('title')}\n     {r.get('detail')}"
        for i, r in enumerate(recs[:6])
    )
    return f"""SEO Audit Report for {domain}
Prepared for {name}

Overall Grade: {ov.get('grade','—')}
{ov.get('summary','')}

Category Scores:
{cat_str}

Priority Recommendations:
{rec_str}

---
Your full report is attached as an HTML file.
Open it in your browser to view all sections.
Powered by Claude AI SEO Audit Tool
"""


# ── Full report HTML attachment ───────────────────────────────────────────────

def build_full_report_html(D, name, email, date):
    """Build the complete report as a standalone HTML file."""
    domain = D.get("domain", "")
    ov     = D.get("overall", {})
    cats   = D.get("cats", [])
    op     = D.get("op", {})
    geo    = D.get("geo", {})
    us     = D.get("us", {})
    pf     = D.get("pf", {})
    tech   = D.get("tech", {})
    loc    = D.get("local", {})
    recs   = D.get("recommendations", [])

    GRADES = ["A+","A","A-","B+","B","B-","C+","C","C-","D+","D","D-","F"]
    def gp(g):
        i = GRADES.index(g) if g in GRADES else 6
        return 1 - (i / len(GRADES))
    def gc(g):
        p = gp(g)
        return "#1e8449" if p > .75 else "#b7770d" if p > .5 else "#e67e22" if p > .3 else "#c0392b"

    def svg_circle(grade, sz=50):
        s, r = sz, sz//2 - 5
        circ = 2 * 3.14159 * r
        c    = gc(grade)
        fs   = int(s * .26) if len(grade) > 2 else int(s * .32)
        off  = circ * (1 - gp(grade))
        return (f'<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}">'
                f'<circle cx="{s//2}" cy="{s//2}" r="{r}" fill="none" stroke="#eee" stroke-width="{int(s*.07)}"/>'
                f'<circle cx="{s//2}" cy="{s//2}" r="{r}" fill="none" stroke="{c}" stroke-width="{int(s*.07)}"'
                f' stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}"'
                f' stroke-linecap="round" transform="rotate(-90 {s//2} {s//2})"/>'
                f'<text x="{s//2}" y="{s//2 + int(fs*.38)}" text-anchor="middle"'
                f' font-family="Arial,sans-serif" font-size="{fs}" font-weight="700" fill="{c}">{grade}</text></svg>')

    def cicon(t):
        colors = {"p":"#1e8449","f":"#c0392b","w":"#b7770d","i":"#1a5276"}
        symbols = {"p":"✓","f":"✕","w":"!","i":"i"}
        bg = colors.get(t,"#999")
        sym = symbols.get(t,"i")
        return (f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                f'width:18px;height:18px;border-radius:50%;background:{bg};color:#fff;'
                f'font-size:9px;font-weight:700;flex-shrink:0;margin-top:2px">{sym}</span>')

    def row(icon_type, title, body_html=""):
        return (f'<div style="padding:12px 0;border-bottom:1px solid #f0f2f5">'
                f'<div style="display:flex;align-items:flex-start;gap:8px">'
                f'{cicon(icon_type)}'
                f'<div style="font-size:13px;font-weight:500;flex:1">{title}</div></div>'
                f'{body_html}</div>')

    def val_box(txt):
        return (f'<div style="margin:6px 0 0 26px;font-size:12px;background:#f8f9fb;'
                f'border:1px solid #dde1e7;border-radius:7px;padding:6px 11px;'
                f'font-family:monospace;word-break:break-all">{txt}</div>')

    def info_box(txt):
        return (f'<div style="margin:6px 0 0 26px;background:#f8f9fb;border-left:3px solid #dde1e7;'
                f'border-radius:0 7px 7px 0;padding:8px 12px;font-size:12px;color:#5d6d7e;line-height:1.6">{txt}</div>')

    def sec_hdr(color1, color2, title, grade_svg=""):
        return (f'<div style="background:linear-gradient(90deg,{color1},{color2});'
                f'padding:13px 24px;display:flex;align-items:center;gap:14px;margin-top:18px">'
                f'{grade_svg}'
                f'<div style="color:#fff;font-size:14px;font-weight:600">{title}</div></div>')

    def cat_grade(k):
        for c in cats:
            if c.get("k") == k:
                return c.get("grade","B")
        return "B"

    # Overall
    ov_grade = ov.get("grade","B")
    ov_color = gc(ov_grade)
    circ58   = 2 * 3.14159 * 58
    ov_off   = circ58 * (1 - gp(ov_grade))

    # On-page data
    title_t   = (op.get("title") or {}).get("t","")
    title_len = (op.get("title") or {}).get("len",0)
    title_ok  = title_len >= 45 and title_len <= 65
    meta_t    = (op.get("meta") or {}).get("t","")
    meta_len  = (op.get("meta") or {}).get("len",0)
    meta_ok   = meta_len >= 120 and meta_len <= 165

    # Category rows for table
    cat_table = "".join(
        f'<tr><td style="padding:7px 10px;font-size:12px;color:#1c2b3a">{c.get("lbl","")}</td>'
        f'<td style="padding:7px 10px">{svg_circle(c.get("grade","B"),40)}</td></tr>'
        for c in cats
    )

    # H1
    h1_list = op.get("h1",[{"tag":"H1","v":"Not found"}])
    h1_rows = "".join(f'<tr><td style="padding:7px 10px;font-size:12px"><strong>{h.get("tag")}</strong></td><td style="padding:7px 10px;font-size:12px">{h.get("v","")}</td></tr>' for h in h1_list)

    # Keywords
    kw_rows = "".join(
        f'<tr><td style="padding:7px 10px;font-size:12px"><strong>{k.get("p","")}</strong></td>'
        f'<td style="text-align:center;padding:7px 10px">{"✓" if k.get("ti") else "—"}</td>'
        f'<td style="text-align:center;padding:7px 10px">{"✓" if k.get("me") else "—"}</td>'
        f'<td style="text-align:center;padding:7px 10px">{"✓" if k.get("hd") else "—"}</td>'
        f'<td style="text-align:center;padding:7px 10px;font-weight:600">{k.get("f","—")}</td></tr>'
        for k in (op.get("kws") or [])
    )

    # Social
    soc_rows = "".join(
        f'<div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #f0f2f5">'
        f'<div style="width:28px;height:28px;border-radius:7px;background:{s.get("bg","#999")};color:{s.get("c","#fff")};'
        f'display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">{s.get("ico","")}</div>'
        f'<div style="flex:1"><div style="font-size:12.5px;font-weight:500">{s.get("name","")} — {"linked" if s.get("linked") else "not linked"}</div>'
        f'<div style="font-size:11px;color:#95a5a6">{s.get("url","")}</div></div>'
        f'<div style="color:{"#1e8449" if s.get("linked") else "#ccc"};font-weight:700">{"✓" if s.get("linked") else "—"}</div></div>'
        for s in (D.get("social") or [])
    )

    # OG tags
    og_rows = "".join(
        f'<tr><td style="padding:6px 10px;font-size:12px"><code>{t.get("t","")}</code></td>'
        f'<td style="padding:6px 10px;font-size:12px;color:#5d6d7e;word-break:break-all">{t.get("v","")}</td></tr>'
        for t in (D.get("ogTags") or [])
    )

    # Recommendations
    rec_rows_full = "".join(
        f'<div style="padding:12px 0;border-bottom:{"none" if i==len(recs)-1 else "1px solid #f0f2f5"}">'
        f'<div style="display:flex;align-items:flex-start;gap:8px">'
        f'<span style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;'
        f'border-radius:50%;background:#b7770d;color:#fff;font-size:9px;font-weight:700">{r.get("priority",i+1)}</span>'
        f'<div style="font-size:13px;font-weight:600;flex:1">{r.get("title","")}</div></div>'
        f'<div style="margin:6px 0 0 26px;background:#fff8e1;border:1px solid #ffe082;border-radius:7px;'
        f'padding:9px 13px;font-size:12px;color:#5d4037;line-height:1.6">{r.get("detail","")}</div></div>'
        for i, r in enumerate(recs)
    )

    # Tech list
    tech_rows = "".join(
        f'<tr><td style="padding:7px 10px;font-size:12px">{t.get("name","")}</td>'
        f'<td style="padding:7px 10px;font-size:12px;color:#95a5a6">{t.get("ver","")}</td></tr>'
        for t in (tech.get("list") or [])
    )

    cwv     = (us.get("cwv") or {})
    mob     = (us.get("mob") or {})
    desk    = (us.get("desk") or {})
    gbp     = (loc.get("gbp") or {})
    rev     = (loc.get("reviews") or {})
    rating  = rev.get("rating", 0)
    stars   = "★" * round(rating) + "☆" * (5 - round(rating))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SEO Report — {domain}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#eef0f4;color:#1c2b3a;font-size:13.5px;line-height:1.6}}
  .wrap{{max-width:860px;margin:0 auto;padding:24px 14px}}
  .toolbar{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}}
  .btn-print{{background:linear-gradient(135deg,#3b82f6,#06b6d4);color:#fff;border:none;border-radius:9px;padding:9px 18px;font-size:12.5px;font-weight:600;cursor:pointer}}
  .rpt{{background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.12)}}
  .rtbl{{width:100%;border-collapse:collapse;font-size:12.5px}}
  .rtbl th{{background:#f8f9fb;padding:7px 10px;text-align:left;font-size:10px;text-transform:uppercase;color:#95a5a6;border-bottom:1px solid #dde1e7;font-weight:600}}
  .rtbl td{{padding:8px 10px;border-bottom:1px solid #f0f2f5}}
  .rtbl tr:last-child td{{border-bottom:none}}
  @media print{{.toolbar{{display:none}}.rpt{{box-shadow:none}}body{{background:#fff}}@page{{margin:12mm;size:A4}}}}
</style>
</head>
<body>
<div class="wrap">

<div class="toolbar">
  <div style="font-size:12px;color:#5d6d7e">🔍 SEO Report — {domain}</div>
  <button class="btn-print" onclick="window.print()">🖨 Print / Save as PDF</button>
</div>

<div class="rpt">

<!-- Header -->
<div style="background:linear-gradient(135deg,#c0392b,#922b21);padding:24px 32px;color:#fff">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:8px">
    <div>
      <div style="font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;opacity:.7;margin-bottom:8px">✦ AI-Powered SEO Audit</div>
      <h2 style="font-size:19px;font-weight:700;margin-bottom:3px">Website Report for {domain}</h2>
      <div style="font-size:12px;opacity:.8">Prepared for {name} · {email}</div>
    </div>
    <div style="font-size:11px;opacity:.72;text-align:right;line-height:1.9">
      <div style="font-weight:600;font-size:13px">SEO Audit Tool</div>
      <div>{date}</div>
    </div>
  </div>
  <div style="font-size:12.5px;opacity:.82;line-height:1.7">{ov.get("summary","")}</div>
</div>

<!-- Summary -->
<div style="display:grid;grid-template-columns:200px 1fr;border-bottom:1px solid #dde1e7">
  <div style="padding:24px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;border-right:1px solid #dde1e7">
    <div style="font-size:12px;color:#5d6d7e;font-weight:500">Overall Score</div>
    <svg width="120" height="120" viewBox="0 0 130 130">
      <circle cx="65" cy="65" r="58" fill="none" stroke="#eee" stroke-width="8"/>
      <circle cx="65" cy="65" r="58" fill="none" stroke="{ov_color}" stroke-width="8"
        stroke-dasharray="{circ58:.1f}" stroke-dashoffset="{ov_off:.1f}"
        stroke-linecap="round" transform="rotate(-90 65 65)"/>
      <text x="65" y="70" text-anchor="middle" font-family="Arial" font-size="26" font-weight="700" fill="{ov_color}">{ov_grade}</text>
    </svg>
  </div>
  <div style="padding:22px 26px">
    <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#95a5a6;margin-bottom:12px">Category Breakdown</div>
    <table class="rtbl" style="margin-bottom:0">
      <thead><tr><th>Category</th><th>Grade</th></tr></thead>
      <tbody>{cat_table}</tbody>
    </table>
  </div>
</div>

<!-- ON-PAGE SEO -->
{sec_hdr("#c0392b","#a93226","On-Page SEO Results", svg_circle(cat_grade("op"),48))}
<div style="padding:0 24px">
  <!-- SERP Preview -->
  <div style="padding:12px 0;border-bottom:1px solid #f0f2f5">
    <div style="display:flex;align-items:flex-start;gap:8px">{cicon("i")}<div style="font-size:13px;font-weight:500">SERP Snippet Preview</div></div>
    <div style="border:1px solid #dde1e7;border-radius:8px;padding:12px 14px;margin:8px 0 0 26px;background:#fff">
      <div style="font-size:11px;color:#188038;margin-bottom:3px">{op.get("serpUrl","https://"+domain)}</div>
      <div style="font-size:15px;color:#1558d6;line-height:1.3;margin-bottom:4px">{op.get("serpTitle",title_t[:57])}</div>
      <div style="font-size:12px;color:#3c4043;line-height:1.55">{op.get("serpDesc",meta_t[:155])}</div>
    </div>
  </div>
  {row("w" if not title_ok else "p", f"Title Tag — {'optimal' if title_ok else 'adjust needed'} — {title_len} chars",
       val_box(title_t) + info_box(op.get("titleAdvice","Aim for 50–60 characters.")))}
  {row("w" if not meta_ok else "p", f"Meta Description — {'optimal' if meta_ok else 'adjust needed'} — {meta_len} chars",
       val_box(meta_t) + info_box(op.get("metaAdvice","Aim for 120–160 characters.")))}
  <div style="padding:12px 0;border-bottom:1px solid #f0f2f5">
    <div style="display:flex;align-items:flex-start;gap:8px">{cicon("p" if len(h1_list)==1 else "w")}<div style="font-size:13px;font-weight:500">H1 Heading — {"one H1 found" if len(h1_list)==1 else str(len(h1_list))+" H1 tags"}</div></div>
    <div style="margin:8px 0 0 26px"><table class="rtbl"><thead><tr><th>Tag</th><th>Content</th></tr></thead><tbody>{h1_rows}</tbody></table></div>
  </div>
  <div style="padding:12px 0;border-bottom:1px solid #f0f2f5">
    <div style="display:flex;align-items:flex-start;gap:8px">{cicon("p")}<div style="font-size:13px;font-weight:500">Keyword Consistency</div></div>
    <div style="margin:8px 0 0 26px"><table class="rtbl"><thead><tr><th>Keyword</th><th>Title</th><th>Meta</th><th>Headings</th><th>Freq.</th></tr></thead><tbody>{kw_rows}</tbody></table></div>
  </div>
  {row("p" if op.get("wcOk") else "w", f"Word Count — {op.get('wc',0):,} words — {'good' if op.get('wcOk') else 'below minimum'}",
       info_box("Good level of content." if op.get("wcOk") else "Add more content — aim for 500+ words."))}
  {row("p" if op.get("imgAlt") else "w", f"Image Alt Attributes — {op.get('imgAltDesc','')}", "")}
  {row("p" if op.get("canonOk") else "w", f"Canonical Tag — {'configured' if op.get('canonOk') else 'missing'}", val_box(op.get("canon","Not detected")))}
  {row("p" if op.get("noindexOk") else "f", f"Noindex — {'page is indexable' if op.get('noindexOk') else 'BLOCKING this page!'}", "")}
  {row("p" if op.get("httpsRedir") else "f", f"HTTPS — {'secure' if op.get('httpsRedir') else 'not secure'}", "")}
  {row("p" if op.get("robotsOk") else "f", f"Robots.txt — {'found' if op.get('robotsOk') else 'missing'}", val_box(op.get("robots","Not found")))}
  {row("p" if op.get("sitemapOk") else "f", f"XML Sitemap — {'found' if op.get('sitemapOk') else 'missing'}", val_box(op.get("sitemap","Not found")))}
  {row("p" if op.get("analytics") else "w", f"Analytics — {'detected' if op.get('analytics') else 'not detected'}", val_box(", ".join(op.get("analyticsTools",[]) or ["None"])))}
  {row("p" if op.get("schema") else "w", f"Schema.org — {'detected' if op.get('schema') else 'not found'}", info_box(("Types: "+", ".join(op.get("schemaTypes",[]))) if op.get("schema") else "Add JSON-LD schema markup."))}
</div>

<!-- GEO / AI -->
{sec_hdr("#1e8449","#27ae60","Generative Engine Optimization (GEO)", svg_circle(cat_grade("geo"),48))}
<div style="padding:0 24px">
  {row("p" if geo.get("renderOk") else "w", f"LLM Readability — {geo.get('renderPct','N/A')}", info_box(geo.get("renderDesc","")))}
  {row("p" if geo.get("llmsTxt") else "w", f"llms.txt — {'found' if geo.get('llmsTxt') else 'not found'}", val_box(geo.get("llmsTxtUrl","Not found")))}
</div>

<!-- USABILITY -->
{sec_hdr("#c0392b","#a93226","Usability", svg_circle(cat_grade("us"),48))}
<div style="padding:0 24px">
  {row("p" if cwv.get("pass") else "f", f"Core Web Vitals — {'passed' if cwv.get('pass') else 'failed'}",
       f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 0 26px">'
       f'<div style="flex:1;min-width:90px;background:#f8f9fb;border:1px solid #dde1e7;border-radius:9px;padding:11px;text-align:center"><div style="font-size:20px;font-weight:600">{cwv.get("lcp","N/A")}</div><div style="font-size:10px;color:#5d6d7e">LCP</div></div>'
       f'<div style="flex:1;min-width:90px;background:#f8f9fb;border:1px solid #dde1e7;border-radius:9px;padding:11px;text-align:center"><div style="font-size:20px;font-weight:600">{cwv.get("inp","N/A")}</div><div style="font-size:10px;color:#5d6d7e">INP</div></div>'
       f'<div style="flex:1;min-width:90px;background:#f8f9fb;border:1px solid #dde1e7;border-radius:9px;padding:11px;text-align:center"><div style="font-size:20px;font-weight:600">{cwv.get("cls","N/A")}</div><div style="font-size:10px;color:#5d6d7e">CLS</div></div>'
       f'</div>')}
  {row("p" if mob.get("score",0)>=70 else "w" if mob.get("score",0)>=50 else "f",
       f"Mobile PageSpeed — {mob.get('score',0)}/100",
       info_box(f"FCP: {mob.get('fcp','N/A')} · LCP: {mob.get('lcp','N/A')} · TTI: {mob.get('tti','N/A')} · CLS: {mob.get('cls','N/A')}"))}
  {row("p" if desk.get("score",0)>=70 else "w" if desk.get("score",0)>=50 else "f",
       f"Desktop PageSpeed — {desk.get('score',0)}/100",
       info_box(f"FCP: {desk.get('fcp','N/A')} · LCP: {desk.get('lcp','N/A')} · TTI: {desk.get('tti','N/A')} · CLS: {desk.get('cls','N/A')}"))}
  {row("p" if us.get("favicon") else "w", f"Favicon — {'found' if us.get('favicon') else 'not found'}", "")}
  {row("p" if us.get("emailPrivacy") else "w", f"Email Privacy — {'no plain-text emails' if us.get('emailPrivacy') else 'emails exposed'}", "")}
</div>

<!-- PERFORMANCE -->
{sec_hdr("#1a5276","#1f618d","Performance Results", svg_circle(cat_grade("pf"),48))}
<div style="padding:0 24px">
  {row("p" if (pf.get("speed") or {}).get("ok") else "w", "Website Load Speed",
       info_box(f"Server: {(pf.get('speed') or {}).get('srv','N/A')} · Content: {(pf.get('speed') or {}).get('cnt','N/A')} · Scripts: {(pf.get('speed') or {}).get('scr','N/A')}"))}
  {row("p" if (pf.get("size") or {}).get("ok") else "w", f"Download Size — {(pf.get('size') or {}).get('tot','N/A')}",
       info_box(f"HTML: {(pf.get('size') or {}).get('html','N/A')} · CSS: {(pf.get('size') or {}).get('css','N/A')} · JS: {(pf.get('size') or {}).get('js','N/A')} · Images: {(pf.get('size') or {}).get('img','N/A')}"))}
  {row("p" if pf.get("http2") else "w", f"HTTP/2 — {'in use' if pf.get('http2') else 'not in use'}", "")}
  {row("f" if pf.get("jsErrors") else "p", f"JavaScript Errors — {'detected' if pf.get('jsErrors') else 'none detected'}",
       val_box(pf.get("jsErrDesc","")) if pf.get("jsErrors") else "")}
</div>

<!-- SOCIAL -->
<div style="background:linear-gradient(90deg,#6c3483,#8e44ad);padding:13px 24px;margin-top:18px">
  <div style="color:#fff;font-size:14px;font-weight:600">Social Results</div>
</div>
<div style="padding:8px 24px">
  {soc_rows}
  {'<div style="padding:12px 0;border-bottom:1px solid #f0f2f5"><div style="display:flex;align-items:flex-start;gap:8px">'+cicon("p")+'<div style="font-size:13px;font-weight:500">Open Graph Tags</div></div><div style="margin:8px 0 0 26px"><table class="rtbl"><thead><tr><th>Tag</th><th>Value</th></tr></thead><tbody>'+og_rows+'</tbody></table></div></div>' if og_rows else ""}
</div>

<!-- LOCAL SEO -->
<div style="background:linear-gradient(90deg,#0e6655,#148f77);padding:13px 24px;margin-top:18px">
  <div style="color:#fff;font-size:14px;font-weight:600">Local SEO</div>
</div>
<div style="padding:0 24px">
  {row("p" if loc.get("hasAddress") else "w", f"Address & Phone — {'visible' if loc.get('hasAddress') else 'not found'}",
       info_box(f"Phone: {loc.get('phone','—')} · Address: {loc.get('addr','—')}") if loc.get("hasAddress") else "")}
  {row("p" if loc.get("localSchema") else "w", f"Local Business Schema — {'found' if loc.get('localSchema') else 'not found'}", "")}
  {row("p" if gbp.get("found") else "w", f"Google Business Profile — {'found' if gbp.get('found') else 'not found'}",
       info_box(f"{gbp.get('name','—')} · {gbp.get('addr','—')} · {gbp.get('phone','—')}") if gbp.get("found") else "")}
  {row("p" if rating>=4 else "w" if rating>=3 else "f",
       f"Google Reviews — {rating} ★ ({rev.get('count',0)} reviews)" if rating else "Google Reviews — not found",
       info_box(stars) if rating else "")}
</div>

<!-- TECHNOLOGY -->
{sec_hdr("#2c3e50","#34495e","Technology Results")}
<div style="padding:0 24px">
  <div style="padding:12px 0;border-bottom:1px solid #f0f2f5">
    <div style="display:flex;align-items:flex-start;gap:8px">{cicon("i")}<div style="font-size:13px;font-weight:500">Technology Stack</div></div>
    <div style="margin:8px 0 0 26px"><table class="rtbl"><thead><tr><th>Technology</th><th>Version</th></tr></thead><tbody>{tech_rows}</tbody></table></div>
  </div>
  {row("f" if not tech.get("dmarc") else "p", f"DMARC — {'found' if tech.get('dmarc') else 'not found'}", info_box(tech.get("dmarcDesc","")))}
  {row("p" if tech.get("spf") else "w", f"SPF — {'found' if tech.get('spf') else 'not found'}", val_box(tech.get("spfRecord","Not found")))}
</div>

<!-- RECOMMENDATIONS -->
<div style="background:linear-gradient(90deg,#935116,#b7770d);padding:13px 24px;margin-top:18px">
  <div style="color:#fff;font-size:14px;font-weight:600">🎯 Priority Recommendations</div>
</div>
<div style="padding:14px 24px">
  {rec_rows_full}
</div>

<!-- Footer -->
<div style="background:#f8f9fb;border-top:1px solid #dde1e7;padding:16px 24px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
  <div style="font-size:12px;color:#5d6d7e">SEO Audit for <strong style="color:#c0392b">{domain}</strong> · Powered by Claude AI</div>
  <div style="font-size:11.5px;color:#95a5a6">{date}</div>
</div>

</div><!-- /.rpt -->
</div><!-- /.wrap -->
</body></html>"""



# ── Convert HTML to PDF via API ───────────────────────────────────────────────

def html_to_pdf(html_content):
    """
    Convert HTML to PDF bytes using html2pdf.app (free, no signup needed).
    Falls back to raw HTML bytes if conversion fails.
    Returns (pdf_bytes, is_pdf).
    """
    try:
        api_key = os.environ.get("HTML2PDF_API_KEY", "")
        
        if api_key:
            # PDFShift — 50 free PDFs/month, high quality
            # Sign up at pdfshift.io to get API key
            payload = json.dumps({
                "source": html_content,
                "landscape": False,
                "use_print": True,
                "margin": {"top": "13mm", "bottom": "13mm", "left": "13mm", "right": "13mm"},
                "format": "A4"
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.pdfshift.io/v3/convert/pdf",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {__import__('base64').b64encode(f'api:{api_key}'.encode()).decode()}"
                }
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read(), True

        else:
            # html2pdf.app — free, no API key needed (100/month limit)
            payload = json.dumps({
                "html": html_content,
                "options": {
                    "format": "A4",
                    "margin": {"top": "13mm", "bottom": "13mm", "left": "13mm", "right": "13mm"},
                    "printBackground": True
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://html2pdf.app/f/pdf",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read(), True

    except Exception:
        # Fallback: send HTML file if PDF conversion fails
        return html_content.encode("utf-8"), False

# ── Send email ────────────────────────────────────────────────────────────────

def send_email_with_attachment(to_addr, subject, html_body, text_body, attachment_html, filename):
    host     = os.environ.get("SMTP_HOST", "")
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ.get("SMTP_USER", "")
    pwd      = os.environ.get("SMTP_PASS", "")
    from_hdr = os.environ.get("SMTP_FROM", user)

    if not host or not user or not pwd:
        raise ValueError("SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS in Vercel env vars.")

    # Convert HTML report to PDF
    att_bytes, is_pdf = html_to_pdf(attachment_html)
    att_filename = filename.replace(".html", ".pdf") if is_pdf else filename

    # Root message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = from_hdr
    msg["To"]      = to_addr

    # Email body (summary)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain"))
    alt.attach(MIMEText(html_body, "html"))
    msg.attach(alt)

    # PDF (or HTML fallback) attachment
    if is_pdf:
        att = MIMEApplication(att_bytes, _subtype="pdf")
    else:
        att = MIMEBase("text", "html")
        att.set_payload(att_bytes)
        encoders.encode_base64(att)

    att.add_header("Content-Disposition", "attachment", filename=att_filename)
    msg.attach(att)

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(user, pwd)
        server.sendmail(user, to_addr, msg.as_string())


# ── Handler ───────────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            length   = int(self.headers.get("Content-Length", 0))
            body     = json.loads(self.rfile.read(length))
            job_id   = body.get("job_id", "").strip()
            to_email = body.get("email",  "").strip()

            if not to_email or not valid_email(to_email):
                return self._json(400, {"error": "Please enter a valid email address."})

            record = store_get(job_id)
            if not record or record.get("status") != "done":
                return self._json(404, {"error": "Report not found. Please run the audit again."})

            D      = record.get("data", {})
            name   = record.get("name", "there")
            domain = D.get("domain", "your website")

            from datetime import datetime
            date = datetime.now().strftime("%d %B %Y")

            # Build email body (summary)
            html_body = build_summary_html(D, name, to_email)
            text_body = build_summary_text(D, name)

            # Build full report as HTML attachment
            full_report = build_full_report_html(D, name, to_email, date)
            filename    = f"seo-report-{domain}-{datetime.now().strftime('%Y%m%d')}.pdf"

            send_email_with_attachment(
                to_email,
                f"Your SEO Audit Report for {domain}",
                html_body,
                text_body,
                full_report,
                filename
            )

            self._json(200, {"ok": True, "message": f"Report sent to {to_email}"})

        except ValueError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": f"Failed to send: {str(e)}"})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *a): pass
