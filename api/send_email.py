"""
/api/send_email  POST {job_id, email}
Fetches the audit result from Redis and emails a summary report to the user.
Uses Python's built-in smtplib — set SMTP env vars in Vercel dashboard.

Required env vars:
  SMTP_HOST     e.g. smtp.gmail.com
  SMTP_PORT     e.g. 587
  SMTP_USER     e.g. your@gmail.com
  SMTP_PASS     e.g. your-app-password   (Gmail: use App Password, not account password)
  SMTP_FROM     e.g. SEO Audit Tool <your@gmail.com>
"""

import json, os, re, smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
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
    v = r.get(f"seo:{job_id}")
    return json.loads(v) if v else None


# ── Email validator ───────────────────────────────────────────────────────────

def valid_email(addr):
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$', addr.strip()))


# ── Build HTML email body ─────────────────────────────────────────────────────

def build_email_html(D, name, report_email):
    domain = D.get("domain", "your website")
    ov     = D.get("overall", {})
    grade  = ov.get("grade", "—")
    summary= ov.get("summary", "")
    cats   = D.get("cats", [])
    recs   = D.get("recommendations", [])
    op     = D.get("op", {})

    grade_color = "#1e8449" if grade in ["A+","A","A-","B+"] else \
                  "#b7770d" if grade in ["B","B-","C+","C"]  else "#c0392b"

    cat_rows = "".join(
        f"""<tr>
              <td style="padding:8px 12px;font-size:13px;color:#1c2b3a">{c.get('lbl','')}</td>
              <td style="padding:8px 12px;font-size:13px;font-weight:700;color:{grade_color}">{c.get('grade','—')}</td>
            </tr>"""
        for c in cats
    )

    rec_rows = "".join(
        f"""<tr>
              <td style="padding:6px 0;vertical-align:top;width:24px">
                <span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#b7770d;
                  color:#fff;font-size:10px;font-weight:700;text-align:center;line-height:20px">{r.get('priority',i+1)}</span>
              </td>
              <td style="padding:6px 0 6px 10px">
                <div style="font-size:13px;font-weight:600;color:#1c2b3a;margin-bottom:3px">{r.get('title','')}</div>
                <div style="font-size:12px;color:#5d6d7e;line-height:1.6">{r.get('detail','')}</div>
              </td>
            </tr>"""
        for i, r in enumerate(recs[:6])
    )

    title_t   = (op.get("title") or {}).get("t", "—")
    meta_t    = (op.get("meta")  or {}).get("t", "—")

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Your SEO Audit Report — {domain}</title></head>
<body style="margin:0;padding:0;background:#eef0f4;font-family:'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef0f4;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#c0392b,#922b21);border-radius:16px 16px 0 0;padding:30px 34px;color:#fff">
    <div style="font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;opacity:.7;margin-bottom:8px">SEO Audit Report</div>
    <div style="font-size:22px;font-weight:700;margin-bottom:6px">Website Report for {domain}</div>
    <div style="font-size:13px;opacity:.8">Prepared for {name}</div>
  </td></tr>

  <!-- Overall grade -->
  <tr><td style="background:#fff;padding:28px 34px;border-bottom:1px solid #eee">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="vertical-align:middle">
          <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#95a5a6;margin-bottom:6px">Overall Grade</div>
          <div style="font-size:52px;font-weight:700;color:{grade_color};line-height:1">{grade}</div>
        </td>
        <td style="vertical-align:middle;padding-left:28px">
          <div style="font-size:13.5px;color:#1c2b3a;line-height:1.65">{summary}</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- Category grades -->
  <tr><td style="background:#fff;padding:0 34px 24px">
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#95a5a6;margin-bottom:12px">Category Scores</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8f9fb">
        <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:#95a5a6;font-weight:600">Category</th>
        <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:#95a5a6;font-weight:600">Grade</th>
      </tr></thead>
      <tbody>{cat_rows}</tbody>
    </table>
  </td></tr>

  <!-- Key findings -->
  <tr><td style="background:#fff;padding:0 34px 24px;border-bottom:1px solid #eee">
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#95a5a6;margin-bottom:12px">Key On-Page Findings</div>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="padding:8px 0;border-bottom:1px solid #f0f2f5">
          <div style="font-size:11px;color:#95a5a6;margin-bottom:3px">TITLE TAG</div>
          <div style="font-size:13px;color:#1c2b3a">{title_t[:80]}{"..." if len(title_t)>80 else ""}</div>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 0">
          <div style="font-size:11px;color:#95a5a6;margin-bottom:3px">META DESCRIPTION</div>
          <div style="font-size:13px;color:#1c2b3a">{meta_t[:120]}{"..." if len(meta_t)>120 else ""}</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- Recommendations -->
  <tr><td style="background:#fff;padding:24px 34px;border-bottom:1px solid #eee">
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#95a5a6;margin-bottom:14px">🎯 Priority Recommendations</div>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tbody>{rec_rows}</tbody>
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="background:#fff;padding:24px 34px;text-align:center;border-bottom:1px solid #eee">
    <div style="font-size:13px;color:#5d6d7e;margin-bottom:16px">Your full interactive report with all sections is available online.</div>
    <div style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#06b6d4);border-radius:10px;padding:13px 28px">
      <span style="color:#fff;font-size:14px;font-weight:700;text-decoration:none">View Full Report Online</span>
    </div>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f8f9fb;border-radius:0 0 16px 16px;padding:18px 34px;border-top:1px solid #eee">
    <div style="font-size:12px;color:#95a5a6">
      SEO Audit for <strong style="color:#c0392b">{domain}</strong> · Powered by Claude AI<br/>
      This report was sent to {report_email}
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def build_email_text(D, name):
    domain = D.get("domain", "your website")
    ov     = D.get("overall", {})
    grade  = ov.get("grade", "—")
    summary= ov.get("summary", "")
    cats   = D.get("cats", [])
    recs   = D.get("recommendations", [])

    cat_lines = "\n".join(f"  {c.get('lbl','')}: {c.get('grade','—')}" for c in cats)
    rec_lines = "\n".join(f"  {i+1}. {r.get('title','')}\n     {r.get('detail','')}" for i,r in enumerate(recs[:6]))

    return f"""SEO Audit Report for {domain}
Prepared for {name}

OVERALL GRADE: {grade}
{summary}

CATEGORY SCORES:
{cat_lines}

PRIORITY RECOMMENDATIONS:
{rec_lines}

---
Powered by Claude AI SEO Audit Tool
"""


# ── Send email ────────────────────────────────────────────────────────────────

def send_email(to_addr, subject, html_body, text_body):
    host    = os.environ.get("SMTP_HOST", "")
    port    = int(os.environ.get("SMTP_PORT", "587"))
    user    = os.environ.get("SMTP_USER", "")
    pwd     = os.environ.get("SMTP_PASS", "")
    from_hdr= os.environ.get("SMTP_FROM", user)

    if not host or not user or not pwd:
        raise ValueError("SMTP not configured — set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS in Vercel env vars")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_hdr
    msg["To"]      = to_addr
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

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
            length    = int(self.headers.get("Content-Length", 0))
            body      = json.loads(self.rfile.read(length))
            job_id    = body.get("job_id", "").strip()
            to_email  = body.get("email",  "").strip()

            # Validate email
            if not to_email or not valid_email(to_email):
                return self._json(400, {"error": "Please enter a valid email address."})

            # Fetch report from Redis
            record = store_get(job_id)
            if not record or record.get("status") != "done":
                return self._json(404, {"error": "Report not found. Please run the audit again."})

            D    = record.get("data", {})
            name = record.get("name", "there")
            domain = D.get("domain", "your website")

            subject   = f"Your SEO Audit Report for {domain}"
            html_body = build_email_html(D, name, to_email)
            text_body = build_email_text(D, name)

            send_email(to_email, subject, html_body, text_body)

            self._json(200, {"ok": True, "message": f"Report sent to {to_email}"})

        except ValueError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": f"Failed to send email: {str(e)}"})

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
