#!/usr/bin/env python3
"""
build_from_sheet.py
Pulls the Google Sheet CSV, regenerates index.html / sitemap.xml / robots.txt.
Designed to run in GitHub Actions on a daily schedule.
"""
import os, csv, json, re, io, urllib.request, sys
from datetime import datetime

DOMAIN = "https://trueworthjobs.com"
SHEET_CSV_URL = os.environ.get("SHEET_CSV_URL", "")
if not SHEET_CSV_URL:
    print("ERROR: SHEET_CSV_URL env var not set", file=sys.stderr)
    sys.exit(1)

TODAY = datetime.utcnow().strftime("%Y-%m-%d")
VALID_THROUGH = (datetime.utcnow().replace(month=((datetime.utcnow().month % 12) + 1))).strftime("%Y-%m-%d")

# === 1. Pull CSV from Google Sheets ===
print(f"Fetching {SHEET_CSV_URL}")
req = urllib.request.Request(SHEET_CSV_URL, headers={"User-Agent": "TrueWorthJobs-build/1.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    csv_text = resp.read().decode("utf-8")
print(f"Got {len(csv_text)} bytes")

reader = csv.DictReader(io.StringIO(csv_text))
all_rows = list(reader)
# Filter only Live status
rows = [r for r in all_rows if r.get("Status", "").strip().lower() == "live"]
print(f"Total rows: {len(all_rows)}, Live: {len(rows)}")

if not rows:
    print("ERROR: No Live rows found, aborting build", file=sys.stderr)
    sys.exit(2)

# === Text sanitisers (auto-repair bad data from the Sheet) ===
def fix_mojibake(s):
    """Repair UTF-8 text that was mis-decoded as Windows-1252 (e.g. 'Â£' -> '£', 'â€\u201c' -> en/em dash)."""
    if not s:
        return s
    if "Â" in s or "â€" in s or "Ã" in s or "â‚¬" in s:
        try:
            return s.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s

def clean_location(location, county):
    """Strip the county (and any duplicates) out of the Location field so the site doesn't repeat it."""
    location = fix_mojibake(location)
    county = fix_mojibake(county)
    parts = [p.strip() for p in location.split(",") if p.strip()]
    seen = set()
    out = []
    for p in parts:
        if county and p.lower() == county.lower():
            continue
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append(p)
    return ", ".join(out) if out else (location or "")

# === 2. Build JS data array (for the in-page filter table) ===
def salary_num_avg(s):
    nums = [int(n.replace(",", "")) for n in re.findall(r"£([\d,]+)", s)]
    return sum(nums) // len(nums) if nums else 0

SOURCE_KEY = {
    "Career page": "v1",
    "Indeed": "indeed-v2",
    "LinkedIn": "linkedin-v3",
    "CWJobs": "cwjobs-v4",
    "Manual": "manual",
}

js_data = []
for r in rows:
    _county = fix_mojibake(r["County"].strip())
    _salary = fix_mojibake(r["Salary"].strip())
    js_data.append({
        "role": fix_mojibake(r["Role"].strip()),
        "company": fix_mojibake(r["Company"].strip()),
        "location": clean_location(r["Location"].strip(), _county),
        "county": _county,
        "industry": fix_mojibake(r["Industry"].strip()),
        "salary": _salary,
        "salaryNum": salary_num_avg(_salary),
        "worktype": r["Work Type"].strip(),
        "url": r["Apply URL"].strip(),
        "notes": fix_mojibake(r["Notes"].strip()),
        "source": SOURCE_KEY.get(r.get("Source", "Career page").strip(), "v1"),
        "dateAdded": (r.get("First Listed", "") or "").strip(),
    })
js_json = json.dumps(js_data, ensure_ascii=False)

# === 3. Build JobPosting JSON-LD ===
def emp_type(role_title):
    rt = role_title.lower()
    if "contract" in rt or "inside ir35" in rt: return "CONTRACTOR"
    if "intern" in rt: return "INTERN"
    if "apprentice" in rt: return "TEMPORARY"
    return "FULL_TIME"

job_postings = []
for r in rows:
    sal_min = int(r["Salary Min"]) if r.get("Salary Min", "").strip().isdigit() else 0
    sal_max = int(r["Salary Max"]) if r.get("Salary Max", "").strip().isdigit() else 0
    p = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": fix_mojibake(r["Role"]),
        "description": f"<p>{fix_mojibake(r['Notes'])}</p><p><strong>Industry:</strong> {fix_mojibake(r['Industry'])}<br><strong>Work type:</strong> {r['Work Type']}<br><strong>Salary:</strong> {fix_mojibake(r['Salary'])}</p>",
        "datePosted": r.get("First Listed", TODAY) or TODAY,
        "validThrough": VALID_THROUGH,
        "employmentType": emp_type(r["Role"]),
        "hiringOrganization": {"@type": "Organization", "name": fix_mojibake(r["Company"])},
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": clean_location(r["Location"], fix_mojibake(r["County"])),
                "addressRegion": r["County"],
                "addressCountry": "GB",
            },
        },
        "url": r["Apply URL"],
    }
    if r["Work Type"].strip() == "Remote":
        p["jobLocationType"] = "TELECOMMUTE"
        p["applicantLocationRequirements"] = {"@type": "Country", "name": "United Kingdom"}
    if sal_min and sal_max and sal_min > 1000:
        p["baseSalary"] = {
            "@type": "MonetaryAmount", "currency": "GBP",
            "value": {"@type": "QuantitativeValue", "minValue": sal_min, "maxValue": sal_max, "unitText": "YEAR"}
        }
    job_postings.append(p)
job_postings_json = json.dumps(job_postings, ensure_ascii=False)

# === 4. Stats ===
n_v1 = sum(1 for r in rows if r.get("Source") == "Career page")
n_v2 = sum(1 for r in rows if r.get("Source") == "Indeed")
n_v3 = sum(1 for r in rows if r.get("Source") == "LinkedIn")
n_v4 = sum(1 for r in rows if r.get("Source") == "CWJobs")
total = len(rows)

# === 5. Load template + replace data + stats + refresh date ===
with open("index_template.html", "r", encoding="utf-8") as f:
    html = f.read()

# Replace ROLES JS array
html = re.sub(r"const ROLES = \[.*?\];", "const ROLES = " + js_json + ";", html, count=1, flags=re.DOTALL)

# Replace JobPosting JSON-LD (the second LD+JSON block)
def replace_jobposting_block(html_text, new_json):
    # Find all ld+json blocks
    pattern = re.compile(r'(<script type="application/ld\+json">\s*)(\[[\s\S]*?\])(\s*</script>)')
    matches = list(pattern.finditer(html_text))
    if matches:
        # Replace the first array-typed one
        m = matches[0]
        return html_text[:m.start(2)] + new_json + html_text[m.end(2):]
    return html_text

html = replace_jobposting_block(html, job_postings_json)

# Replace stat counts in <stats> block
html = re.sub(r'<div class="num" id="stat-live">\d+</div>',
              f'<div class="num" id="stat-live">{total}</div>', html)
html = re.sub(r'<div class="stat"><div class="num">\d+</div><div class="lbl">Career page</div></div>',
              f'<div class="stat"><div class="num">{n_v1}</div><div class="lbl">Career page</div></div>', html)
html = re.sub(r'<div class="stat"><div class="num">\+?\d+</div><div class="lbl">Indeed</div></div>',
              f'<div class="stat"><div class="num">+{n_v2}</div><div class="lbl">Indeed</div></div>', html)
html = re.sub(r'<div class="stat"><div class="num">\+?\d+</div><div class="lbl">LinkedIn</div></div>',
              f'<div class="stat"><div class="num">+{n_v3}</div><div class="lbl">LinkedIn</div></div>', html)
html = re.sub(r'<div class="stat"><div class="num">\+?\d+</div><div class="lbl">CWJobs</div></div>',
              f'<div class="stat"><div class="num">+{n_v4}</div><div class="lbl">CWJobs</div></div>', html)
html = re.sub(r'Showing <strong id="count">\d+</strong> of <strong id="total">\d+</strong>',
              f'Showing <strong id="count">{total}</strong> of <strong id="total">{total}</strong>', html)

# Replace footer refresh date and total count
html = re.sub(r'Last refresh \d{4}-\d{2}-\d{2} &middot; \d+ roles',
              f'Last refresh {TODAY} &middot; {total} roles', html)
html = re.sub(r'Last refresh \d+ \w+ \d{4} &middot; \d+ roles',
              f'Last refresh {TODAY} &middot; {total} roles', html)

# === 6. Build sitemap and robots ===
sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{DOMAIN}/</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>
  <url><loc>{DOMAIN}/privacy.html</loc><lastmod>{TODAY}</lastmod><changefreq>yearly</changefreq><priority>0.3</priority></url>
</urlset>
"""
robots = f"""User-agent: *
Allow: /
Disallow: /private/

Sitemap: {DOMAIN}/sitemap.xml
"""

# Inject live role count into static copy placeholders
html = html.replace("{{COUNT}}", str(total))

# Inject favicon link tags after the <title> (idempotent — skip if already present)
if 'rel="icon"' not in html:
    html = html.replace(
        "</title>",
        '</title>\n<link rel="icon" type="image/x-icon" href="/favicon.ico?v=1">\n'
        '<link rel="shortcut icon" type="image/x-icon" href="/favicon.ico?v=1">\n'
        '<link rel="apple-touch-icon" href="/favicon.ico">',
        1,
    )

# === 7. Write outputs ===
out = "public"
os.makedirs(out, exist_ok=True)
with open(f"{out}/index.html", "w", encoding="utf-8") as f:
    f.write(html)
with open(f"{out}/sitemap.xml", "w", encoding="utf-8") as f:
    f.write(sitemap)
with open(f"{out}/robots.txt", "w", encoding="utf-8") as f:
    f.write(robots)

print(f"Build complete: {total} live roles ({n_v1} career page, {n_v2} Indeed, {n_v3} LinkedIn, {n_v4} CWJobs)")
print(f"Output: {out}/")
