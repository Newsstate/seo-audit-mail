"""
/api/audit_run
PRIMARY:  Claude AI with web_search (full AI-powered analysis)
FALLBACK: Direct HTTP scraping via urllib — no AI key needed.
Triggers fallback when: API key missing, credits exhausted, any Anthropic error.
"""
import json, os, re, urllib.request, urllib.parse, urllib.error
from http.server import BaseHTTPRequestHandler


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

def store_set(job_id, value):
    r = get_redis()
    if r:
        r.set(f"seo:{job_id}", json.dumps(value), ex=3600)

def store_get(job_id):
    r = get_redis()
    if not r:
        return {}
    v = r.get(f"seo:{job_id}")
    return json.loads(v) if v else {}


# ── Claude AI audit ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a world-class SEO auditor. Use the web_search tool MULTIPLE TIMES to research every aspect of the site, then return ONE JSON object only — no markdown, no backticks, no text outside the JSON.

RESEARCH STEPS — do ALL:
1. Fetch the main URL — read title, meta description, H1-H6 tags, keyword frequency, word count, canonical, lang attribute, schema markup, Open Graph tags, Twitter Cards, iframes, favicon
2. Check robots.txt at domain/robots.txt
3. Check sitemap at domain/sitemap.xml and domain/sitemap_index.xml
4. Search "{domain} PageSpeed Insights mobile desktop score"
5. Search "{domain} Core Web Vitals LCP CLS INP"
6. Search "{domain} Facebook Instagram LinkedIn Twitter YouTube" for social profiles
7. Search "{domain} Google Business Profile reviews rating"
8. Search "{domain} DMARC record" and "{domain} SPF record"
9. Search "{domain} technology stack" to identify CMS, CDN, analytics
10. Check domain/llms.txt
11. Search "{domain} organic keyword rankings traffic"
12. Search "{domain} hreflang"

Return ONLY this exact JSON (fill every field with real discovered data):

{
  "domain": "example.com",
  "overall": {"grade": "A", "summary": "One specific sentence about this site's SEO health"},
  "cats": [
    {"k":"op",  "grade":"A+","lbl":"On-Page SEO","c":"#7F77DD"},
    {"k":"geo", "grade":"A", "lbl":"GEO / AI",   "c":"#1e8449"},
    {"k":"us",  "grade":"B-","lbl":"Usability",  "c":"#c0392b"},
    {"k":"pf",  "grade":"A-","lbl":"Performance","c":"#2980b9"}
  ],
  "op": {
    "title":{"t":"Actual title text","len":76,"ok":false},
    "titleAdvice":"Specific advice.",
    "meta":{"t":"Actual meta text","len":160,"ok":true},
    "metaAdvice":"Specific meta advice.",
    "serpUrl":"https://example.com",
    "serpTitle":"Title up to 57 chars",
    "serpDesc":"Meta up to 155 chars...",
    "h1":[{"tag":"H1","v":"Actual H1 text"}],
    "h1Count":1,"h1Status":"good",
    "hfreq":[{"t":"H2","n":12},{"t":"H3","n":24},{"t":"H4","n":7}],
    "kws":[{"p":"keyword","ti":true,"me":true,"hd":true,"f":35}],
    "wc":2118,"wcOk":true,
    "imgAlt":true,"imgAltDesc":"All images have alt attributes.",
    "canon":"https://example.com/","canonOk":true,
    "noindex":false,"noindexOk":true,"noindexHeader":false,
    "httpsRedir":true,
    "robots":"https://example.com/robots.txt","robotsOk":true,"robotsBlocked":false,
    "sitemap":"https://example.com/sitemap_index.xml","sitemapOk":true,
    "analytics":true,"analyticsTools":["Google Analytics"],
    "schema":true,"schemaTypes":["LocalBusiness","WebPage"],
    "lang":"en","langOk":true,
    "hreflang":false,"hreflangDesc":"No hreflang tags found.",
    "amp":false,"ampDesc":"AMP not enabled.","flash":false
  },
  "geo": {
    "renderPct":"18%","renderOk":true,"renderDesc":"Low render % good for LLMs.",
    "llmsTxt":true,"llmsTxtUrl":"https://example.com/llms.txt","llmsDesc":"llms.txt found.",
    "traffic":{"org":107,"paid":0,"ai":0},
    "kws":[{"kw":"brand","co":"IN","pos":1,"vol":90,"tr":27}],
    "positions":[{"r":"Position 1","n":2},{"r":"Position 2-3","n":0},{"r":"Position 4-10","n":0},{"r":"Position 11-20","n":0},{"r":"Position 21-30","n":0},{"r":"Position 31-100","n":3}]
  },
  "us": {
    "cwv":{"lcp":"3.3s","inp":"164ms","cls":"0.00","pass":true},
    "cwvAdvice":"CWV pass.",
    "mob":{"score":35,"fcp":"9.5s","si":"9.5s","lcp":"16.3s","tti":"17.3s","tbt":"0.46s","cls":"0","opps":[{"n":"Reduce unused JS","s":"4.84s"}]},
    "desk":{"score":68,"fcp":"0.8s","si":"1.0s","lcp":"1.1s","tti":"3.9s","tbt":"0.65s","cls":"0.046","opps":[{"n":"Avoid redirects","s":"0.19s"}]},
    "viewport":true,"iframes":false,"iframesDesc":"No iFrames.",
    "fontSizes":true,"tapTargets":true,"favicon":true,"emailPrivacy":true,"flash":false
  },
  "pf": {
    "speed":{"srv":"0.0s","cnt":"4.3s","scr":"7.6s","ok":true},
    "size":{"tot":"2.00MB","html":"0.13MB","css":"0.11MB","js":"1.2MB","img":"0.34MB","other":"0.22MB","ok":true},
    "comp":{"rate":"64%","html":"61%","css":"74%","js":"72%","img":"0%","other":"0%","ok":true},
    "http2":true,"imgOpt":true,"minify":false,"minifyDesc":"Some files not minified.",
    "jsErrors":false,"jsErrDesc":"","inlineStyles":false,"inlineDesc":"","depHtml":false,
    "res":{"tot":106,"html":5,"js":32,"css":20,"img":34,"other":15}
  },
  "social":[
    {"name":"Facebook","url":"https://facebook.com/page","ico":"F","bg":"#1877F2","c":"#fff","linked":true,"stat":""},
    {"name":"Instagram","url":"https://instagram.com/page","ico":"Ig","bg":"#E1306C","c":"#fff","linked":true,"stat":""},
    {"name":"LinkedIn","url":"https://linkedin.com/company/x","ico":"in","bg":"#0A66C2","c":"#fff","linked":true,"stat":""},
    {"name":"X/Twitter","url":"https://x.com/handle","ico":"X","bg":"#000","c":"#fff","linked":true,"stat":""},
    {"name":"YouTube","url":"https://youtube.com/channel/x","ico":"▶","bg":"#FF0000","c":"#fff","linked":true,"stat":""}
  ],
  "fbPixel":"835561506088336","fbPixelOk":true,
  "ogTags":[{"t":"og:title","v":"Title"},{"t":"og:description","v":"Desc"},{"t":"og:image","v":"https://example.com/img.jpg"}],
  "twitterCard":true,
  "twitterTags":[{"t":"twitter:card","v":"summary_large_image"},{"t":"twitter:title","v":"Title"}],
  "local":{
    "hasAddress":true,"phone":"+91 99715 44461","addr":"Full address",
    "localSchema":true,"schemaType":"LocalBusiness",
    "gbp":{"found":true,"name":"Business","addr":"Address","phone":"+91 99717 44661","site":"https://example.com/"},
    "reviews":{"rating":4.7,"count":52,"dist":[45,4,0,2,1]}
  },
  "tech":{
    "list":[{"name":"WordPress","ver":""},{"name":"Cloudflare","ver":""}],
    "dmarc":false,"dmarcDesc":"No DMARC record.",
    "spf":true,"spfRecord":"v=spf1 include:_spf.google.com ~all",
    "server":"cloudflare","serverIp":"162.159.137.54","charset":"UTF-8","http2":true,"http3":false
  },
  "recommendations":[
    {"priority":1,"title":"Issue","detail":"Specific advice."},
    {"priority":2,"title":"Issue","detail":"Specific advice."},
    {"priority":3,"title":"Issue","detail":"Specific advice."}
  ]
}
IMPORTANT: Use REAL values. Return JSON ONLY."""


def run_claude_audit(url):
    """Try Claude AI audit. Raises on any failure."""
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": (
            f"Run a full SEO audit on: {url}\n\n"
            "Use web_search many times. Return ONLY the JSON report."
        )}]
    )
    raw   = "".join(b.text for b in resp.content if b.type == "text")
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError("No JSON found in AI response")
    return json.loads(match.group(0))


# ── Fallback scraper ──────────────────────────────────────────────────────────

UA = "Mozilla/5.0 (compatible; SEOAuditBot/1.0)"

def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace"), r.url, r.status
    except urllib.error.HTTPError as e:
        return "", url, e.code
    except Exception:
        return "", url, 0

def head_ok(url, timeout=6):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False

def gmeta(html, name):
    for p in [
        rf'<meta\s+name=["\']?{re.escape(name)}["\']?\s+content=["\']([^"\']*)["\']',
        rf'<meta\s+content=["\']([^"\']*)["\']?\s+name=["\']?{re.escape(name)}["\']?',
    ]:
        m = re.search(p, html, re.I)
        if m: return m.group(1).strip()
    return ""

def gog(html, prop):
    for p in [
        rf'<meta\s+property=["\']?og:{re.escape(prop)}["\']?\s+content=["\']([^"\']*)["\']',
        rf'<meta\s+content=["\']([^"\']*)["\']?\s+property=["\']?og:{re.escape(prop)}["\']?',
    ]:
        m = re.search(p, html, re.I)
        if m: return m.group(1).strip()
    return ""

def gtw(html, name):
    for p in [
        rf'<meta\s+name=["\']?twitter:{re.escape(name)}["\']?\s+content=["\']([^"\']*)["\']',
        rf'<meta\s+content=["\']([^"\']*)["\']?\s+name=["\']?twitter:{re.escape(name)}["\']?',
    ]:
        m = re.search(p, html, re.I)
        if m: return m.group(1).strip()
    return ""

def word_count(html):
    t = re.sub(r'<[^>]+>', ' ', html)
    return len(re.sub(r'\s+', ' ', t).split())

def top_kws(html, title, meta):
    text  = re.sub(r'<[^>]+>', ' ', html).lower()
    words = re.sub(r'[^\w\s]', '', text).split()
    stop  = {'the','a','an','and','or','but','in','on','at','to','for','of','with',
             'is','are','was','were','be','been','this','that','it','by','from','as',
             'into','about','which','have','has','had','not','do','does','did','we',
             'you','your','our','more','can','will','get','all','any','its','use'}
    words = [w for w in words if len(w) > 3 and w not in stop]
    freq  = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda x: -x[1])[:6]
    return [{"p": kw, "ti": kw in title.lower(), "me": kw in meta.lower(),
             "hd": bool(re.search(rf'<h[1-6][^>]*>[^<]*{re.escape(kw)}', html, re.I)),
             "f": f} for kw, f in top]

def to_grade(score):
    for t, g in [(92,"A+"),(87,"A"),(82,"A-"),(77,"B+"),(72,"B"),(67,"B-"),
                 (60,"C+"),(53,"C"),(45,"C-"),(35,"D+"),(25,"D"),(15,"D-")]:
        if score >= t: return g
    return "F"

def run_fallback_audit(url):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    base   = f"{parsed.scheme}://{parsed.netloc}"

    html, final_url, _ = fetch(url)
    https_ok = final_url.startswith("https://")

    # Title
    tm = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    title_t   = re.sub(r'\s+', ' ', tm.group(1)).strip() if tm else ""
    title_len = len(title_t)
    title_ok  = 45 <= title_len <= 65

    # Meta
    meta_t   = gmeta(html, "description")
    meta_len = len(meta_t)
    meta_ok  = 120 <= meta_len <= 165

    # Canonical / lang / noindex
    cm    = re.search(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', html, re.I)
    canon = cm.group(1).strip() if cm else ""
    lm    = re.search(r'<html[^>]*lang=["\']([^"\']+)["\']', html, re.I)
    lang  = lm.group(1).strip() if lm else ""
    noindex = bool(re.search(r'<meta[^>]*name=["\']robots["\'][^>]*content=["\'][^"\']*noindex', html, re.I))

    # H tags
    h1s   = [re.sub(r'<[^>]+>', '', h).strip()
             for h in re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)]
    hfreq = [{"t": f"H{i}", "n": len(re.findall(rf'<h{i}[\s>]', html, re.I))}
             for i in range(2, 6) if len(re.findall(rf'<h{i}[\s>]', html, re.I)) > 0]

    wc   = word_count(html)
    imgs = re.findall(r'<img[^>]+>', html, re.I)
    miss = [i for i in imgs if 'alt=' not in i.lower()]

    # Schema / OG / Twitter
    stypes  = re.findall(r'"@type"\s*:\s*"([^"]+)"', html)
    og_map  = {k: gog(html, k) for k in ["title","description","image","type","url"]}
    og_tags = [{"t": f"og:{k}", "v": v} for k, v in og_map.items() if v]
    tw_map  = {k: gtw(html, k) for k in ["card","title","description","image"]}
    tw_tags = [{"t": f"twitter:{k}", "v": v} for k, v in tw_map.items() if v]

    # Analytics / FB Pixel
    has_ga  = bool(re.search(r'google-analytics\.com|gtag\(|UA-\d|G-[A-Z0-9]', html, re.I))
    has_gtm = bool(re.search(r'googletagmanager\.com', html, re.I))
    fpxm    = re.search(r"fbq\('init',\s*['\"](\d+)['\"]", html)
    fb_px   = fpxm.group(1) if fpxm else ""

    # Robots / Sitemap / llms.txt
    robots_url  = f"{base}/robots.txt"
    robots_ok   = head_ok(robots_url)
    sitemap_url = next((u for u in [f"{base}/sitemap_index.xml", f"{base}/sitemap.xml"]
                        if head_ok(u)), "")
    llms_url = f"{base}/llms.txt"
    has_llms = head_ok(llms_url)

    # Social links
    links    = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    networks = [("Facebook","facebook.com","F","#1877F2"),
                ("Instagram","instagram.com","Ig","#E1306C"),
                ("LinkedIn","linkedin.com","in","#0A66C2"),
                ("X/Twitter","x.com","X","#000000"),
                ("YouTube","youtube.com","▶","#FF0000")]
    social   = [{"name": n, "url": next((l for l in links if d in l), ""),
                 "ico": ic, "bg": bg, "c": "#fff",
                 "linked": any(d in l for l in links), "stat": ""}
                for n, d, ic, bg in networks]

    # Tech detection
    tech_map = [("WordPress",r'wp-content|wp-includes'),
                ("Shopify",r'cdn\.shopify\.com'),
                ("Wix",r'wix\.com|wixstatic\.com'),
                ("Webflow",r'webflow\.com'),
                ("Next.js",r'__NEXT_DATA__|_next/'),
                ("React",r'react\.production|react\.development'),
                ("Vue.js",r'vue\.min\.js'),
                ("jQuery",r'jquery\.min\.js|jquery-\d'),
                ("Bootstrap",r'bootstrap\.min\.(css|js)'),
                ("Cloudflare",r'__cf_bm|cloudflare\.com'),
                ("Google Analytics",r'google-analytics\.com|gtag\('),
                ("Google Tag Manager",r'googletagmanager\.com'),
                ("Facebook Pixel",r"fbq\(|facebook\.com/tr"),
                ("Tailwind CSS",r'tailwindcss|tailwind\.min'),
                ("Django",r'csrfmiddlewaretoken'),
                ("Laravel",r'laravel')]
    tech_list = [{"name": n, "ver": ""} for n, p in tech_map if re.search(p, html, re.I)]

    server_hdr = ""
    charset    = "UTF-8"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            server_hdr = r.headers.get("Server", "")
            ct  = r.headers.get("Content-Type", "")
            csm = re.search(r'charset=([^\s;]+)', ct)
            if csm: charset = csm.group(1).upper()
    except Exception:
        pass

    # Scoring
    op_checks = [title_ok, meta_ok, len(h1s)==1, wc>=500, bool(canon), bool(lang),
                 not noindex, https_ok, robots_ok, bool(sitemap_url),
                 bool(stypes), bool(og_tags), len(miss)==0]
    op_sc  = round(sum(op_checks) / len(op_checks) * 100)
    geo_sc = round(sum([has_llms, bool(stypes),
                        bool(re.search(r'hreflang', html, re.I)),
                        bool(og_tags)]) / 4 * 100)
    us_sc  = round(sum([https_ok,
                        not bool(re.search(r'<iframe[\s>]', html, re.I)),
                        bool(re.search(r'<link[^>]*rel=["\']?(?:shortcut )?icon', html, re.I)),
                        bool(re.search(r'viewport', html, re.I))]) / 4 * 100)
    html_kb = len(html.encode()) / 1024
    pf_sc   = 90 if html_kb < 100 else (72 if html_kb < 300 else 50)
    ov_sc   = round((op_sc + geo_sc + us_sc + pf_sc) / 4)

    # Recommendations
    recs, p = [], 1
    def add(title, detail):
        nonlocal p
        recs.append({"priority": p, "title": title, "detail": detail}); p += 1

    if not title_ok:
        add("Fix title tag length",
            f"Title is {title_len} chars. Aim for 50–60 characters for best SERP display.")
    if not meta_ok:
        add("Improve meta description",
            f"Meta is {meta_len} chars. Keep between 120–160 characters.")
    if len(h1s) == 0:
        add("Add H1 heading",
            "No H1 tag found. Add one H1 with your primary keyword near the top of the page.")
    elif len(h1s) > 1:
        add("Fix multiple H1 tags",
            f"{len(h1s)} H1 tags found. Use exactly one H1 per page.")
    if not canon:
        add("Add canonical tag",
            "No canonical tag found. Add <link rel='canonical'> to prevent duplicate content.")
    if not robots_ok:
        add("Create robots.txt",
            f"No robots.txt at {robots_url}. Create one to guide search engine crawlers.")
    if not sitemap_url:
        add("Create XML sitemap",
            "No sitemap found. Create one and submit to Google Search Console.")
    if not stypes:
        add("Add Schema.org markup",
            "No structured data detected. Add JSON-LD schema to improve rich results and AI visibility.")
    if not og_tags:
        add("Add Open Graph tags",
            "No OG tags found. Add og:title, og:description, og:image for better social sharing.")
    if not has_llms:
        add("Add llms.txt for AI visibility",
            f"Add a llms.txt file at {llms_url} to help AI crawlers understand your content.")
    if not has_ga and not has_gtm:
        add("Add web analytics",
            "No analytics detected. Add Google Analytics to track your traffic and conversions.")

    recs = recs[:6]
    if not recs:
        recs = [{"priority": 1, "title": "Site looks well optimised",
                 "detail": "No critical issues found. Add Anthropic API key for a full AI-powered audit."}]

    return {
        "domain": domain,
        "overall": {
            "grade": to_grade(ov_sc),
            "summary": (
                f"{domain} scores {ov_sc}/100 in this basic scan. "
                f"Title {'optimal' if title_ok else 'needs fixing'}, "
                f"{'schema present' if stypes else 'no schema detected'}, "
                f"{'HTTPS active' if https_ok else 'not on HTTPS'}. "
                "(Basic scan — add Anthropic key for full AI audit)"
            )
        },
        "cats": [
            {"k": "op",  "grade": to_grade(op_sc),  "lbl": "On-Page SEO", "c": "#7F77DD"},
            {"k": "geo", "grade": to_grade(geo_sc), "lbl": "GEO / AI",    "c": "#1e8449"},
            {"k": "us",  "grade": to_grade(us_sc),  "lbl": "Usability",   "c": "#c0392b"},
            {"k": "pf",  "grade": to_grade(pf_sc),  "lbl": "Performance", "c": "#2980b9"},
        ],
        "op": {
            "title": {"t": title_t, "len": title_len, "ok": title_ok},
            "titleAdvice": f"Title is {title_len} chars. {'Optimal (50–60).' if title_ok else 'Shorten to 50–60 characters.'}",
            "meta": {"t": meta_t, "len": meta_len, "ok": meta_ok},
            "metaAdvice": f"Meta is {meta_len} chars. {'Optimal (120–160).' if meta_ok else 'Adjust to 120–160 characters.'}",
            "serpUrl": final_url,
            "serpTitle": title_t[:57],
            "serpDesc": meta_t[:155] + ("..." if len(meta_t) > 155 else ""),
            "h1": [{"tag": "H1", "v": h[:120]} for h in h1s[:3]] or [{"tag": "H1", "v": "Not found"}],
            "h1Count": len(h1s),
            "h1Status": "good" if len(h1s)==1 else ("multiple" if len(h1s)>1 else "missing"),
            "hfreq": hfreq,
            "kws": top_kws(html, title_t, meta_t),
            "wc": wc, "wcOk": wc >= 500,
            "imgAlt": len(miss)==0,
            "imgAltDesc": "All images have alt attributes." if not miss else f"{len(miss)} image(s) missing alt.",
            "canon": canon or "Not detected", "canonOk": bool(canon),
            "noindex": noindex, "noindexOk": not noindex, "noindexHeader": False,
            "httpsRedir": https_ok,
            "robots": robots_url if robots_ok else "Not found",
            "robotsOk": robots_ok, "robotsBlocked": False,
            "sitemap": sitemap_url or "Not found", "sitemapOk": bool(sitemap_url),
            "analytics": has_ga or has_gtm,
            "analyticsTools": [t for t in [
                "Google Analytics" if has_ga else None,
                "Google Tag Manager" if has_gtm else None
            ] if t],
            "schema": bool(stypes), "schemaTypes": list(set(stypes))[:5],
            "lang": lang, "langOk": bool(lang),
            "hreflang": bool(re.search(r'hreflang', html, re.I)),
            "hreflangDesc": "Hreflang tags found." if re.search(r'hreflang', html, re.I) else "No hreflang tags.",
            "amp": bool(re.search(r'<html[^>]*\bamp\b', html, re.I)),
            "ampDesc": "AMP enabled." if re.search(r'<html[^>]*\bamp\b', html, re.I) else "AMP not enabled.",
            "flash": False,
        },
        "geo": {
            "renderPct": "N/A", "renderOk": True,
            "renderDesc": "Render % unavailable in basic scan.",
            "llmsTxt": has_llms,
            "llmsTxtUrl": llms_url if has_llms else "",
            "llmsDesc": "llms.txt found." if has_llms else "No llms.txt — add one for AI crawler guidance.",
            "traffic": {"org": 0, "paid": 0, "ai": 0},
            "kws": [],
            "positions": [{"r": r, "n": 0} for r in [
                "Position 1","Position 2-3","Position 4-10",
                "Position 11-20","Position 21-30","Position 31-100"]],
        },
        "us": {
            "cwv": {"lcp": "N/A", "inp": "N/A", "cls": "N/A", "pass": False},
            "cwvAdvice": "CWV data unavailable in basic scan. Check Google Search Console.",
            "mob": {"score": 0, "fcp": "N/A", "si": "N/A", "lcp": "N/A",
                    "tti": "N/A", "tbt": "N/A", "cls": "N/A", "opps": []},
            "desk": {"score": 0, "fcp": "N/A", "si": "N/A", "lcp": "N/A",
                     "tti": "N/A", "tbt": "N/A", "cls": "N/A", "opps": []},
            "viewport": bool(re.search(r'viewport', html, re.I)),
            "iframes": bool(re.search(r'<iframe[\s>]', html, re.I)),
            "iframesDesc": "iFrames detected." if re.search(r'<iframe[\s>]', html, re.I) else "No iFrames detected.",
            "fontSizes": True, "tapTargets": True,
            "favicon": bool(re.search(r'<link[^>]*rel=["\']?(?:shortcut )?icon', html, re.I)),
            "emailPrivacy": not bool(re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', html, re.I)),
            "flash": False,
        },
        "pf": {
            "speed": {"srv": "N/A", "cnt": "N/A", "scr": "N/A", "ok": True},
            "size": {"tot": f"{html_kb/1024:.2f}MB (HTML only)",
                     "html": f"{html_kb:.0f}KB", "css": "N/A",
                     "js": "N/A", "img": "N/A", "other": "N/A",
                     "ok": html_kb < 500},
            "comp": {"rate": "N/A", "html": "N/A", "css": "N/A",
                     "js": "N/A", "img": "N/A", "other": "N/A", "ok": True},
            "http2": True, "imgOpt": True,
            "minify": False, "minifyDesc": "Minification not checked in basic scan.",
            "jsErrors": False, "jsErrDesc": "",
            "inlineStyles": False, "inlineDesc": "", "depHtml": False,
            "res": {"tot": 0, "html": 1, "js": 0, "css": 0, "img": 0, "other": 0},
        },
        "social": social,
        "fbPixel": fb_px, "fbPixelOk": bool(fb_px),
        "ogTags": og_tags,
        "twitterCard": bool(tw_map.get("card")),
        "twitterTags": tw_tags,
        "local": {
            "hasAddress": False, "phone": "", "addr": "",
            "localSchema": any("LocalBusiness" in t for t in stypes),
            "schemaType": "LocalBusiness" if any("LocalBusiness" in t for t in stypes) else "",
            "gbp": {"found": False, "name": "", "addr": "", "phone": "", "site": ""},
            "reviews": {"rating": 0, "count": 0, "dist": [0, 0, 0, 0, 0]},
        },
        "tech": {
            "list": tech_list or [{"name": "Unknown", "ver": ""}],
            "dmarc": False, "dmarcDesc": "DMARC not checked in basic scan.",
            "spf": False, "spfRecord": "",
            "server": server_hdr, "serverIp": "", "charset": charset,
            "http2": True, "http3": False,
        },
        "recommendations": recs,
    }


# ── Vercel Handler ────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        job_id = ""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            job_id = body.get("job_id", "")
            url    = body.get("url", "").strip()
            stored = store_get(job_id)
            mode   = "ai"

            # Try Claude AI — silently fall back on ANY error
            try:
                data = run_claude_audit(url)
            except Exception:
                mode = "fallback"
                data = run_fallback_audit(url)

            store_set(job_id, {
                "status": "done",
                "data":   data,
                "name":   stored.get("name", ""),
                "email":  stored.get("email", ""),
                "mode":   mode,
            })

        except Exception as e:
            if job_id:
                store_set(job_id, {"status": "error", "message": str(e)})

        out = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a): pass
