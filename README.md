# True Worth Jobs

Live: https://trueworthjobs.com

## How this works

1. **Master data lives in Google Sheets** — [True Worth Jobs Master](https://docs.google.com/spreadsheets/d/1XUoXfrh6gZabxuIMGRK62qrxVCF7JaGipjT9j8xSU1c/edit)
2. **GitHub Actions runs daily at 6am UTC** — pulls the Sheet, regenerates `public/index.html` + sitemap, commits if anything changed
3. **Netlify auto-deploys** any push to `main` → site is updated within 30 seconds

## Adding / editing jobs

1. Open the Sheet
2. Add a row, mark `Status = Live`
3. Wait for next daily build (or click "Run workflow" in the [Actions tab](../../actions) for instant rebuild)

## Schema

| Column | Required | Notes |
|---|---|---|
| Role | Yes | Job title |
| Company | Yes | Hiring company name |
| Location | Yes | Town/city |
| County | Yes | One of: Greater Manchester, Cheshire, Lancashire, Merseyside |
| Industry | Yes | e.g. "Insurance / Financial Services" |
| Salary | Yes | Display string e.g. "£55,000 – £75,000 (est.)" |
| Salary Min | Optional | Numeric min for sort/filter |
| Salary Max | Optional | Numeric max |
| Work Type | Yes | Hybrid / Remote / Onsite |
| Apply URL | Yes | Direct link to the role |
| Notes | Yes | 1-2 sentence summary for the table |
| Status | Yes | Live / Needs review / Expired / Archived (only Live publishes) |
| Source | Optional | Career page / Indeed / LinkedIn / CWJobs / Manual |
| First Listed | Yes | YYYY-MM-DD when first added |
| Last Verified | Optional | YYYY-MM-DD of last URL check |

## Manual rebuild

In GitHub: **Actions** tab → **Rebuild from Sheet** → **Run workflow** → main → Run.

Takes ~30 seconds.

## Required GitHub secret

`SHEET_CSV_URL` — the published CSV URL of the Sheet, e.g.
`https://docs.google.com/spreadsheets/d/1XUoXfrh6gZabxuIMGRK62qrxVCF7JaGipjT9j8xSU1c/export?format=csv&gid=0`

Set in: Settings → Secrets and variables → Actions → New repository secret.
