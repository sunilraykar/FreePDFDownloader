# FreePDFDownloader

A free local web app for discovering and bulk-downloading PDF files linked from a website.

## Implemented features

- Crawl same-host HTML pages with configurable depth and page limits.
- Discover PDFs linked from pages and common sitemap locations, including sitemap indexes.
- Browser UI with scan status, page count, discovered PDF count, selection controls, and file status.
- Select individual results or all results for bulk download.
- Retry transient download failures, use safe duplicate-aware filenames, and verify PDF file signatures.
- Limit individual downloads to 250 MB and show failed download details.
- Export the discovery list and download statuses to CSV.
- Windows startup script; runs locally without paid hosting or a subscription.
- Basic unit tests and GitHub Actions checks.

## Requirements

- Python 3.10 or newer
- Internet access to the target website

## Windows quick start

1. Install Python from https://www.python.org/downloads/ and enable **Add Python to PATH**.
2. Download or clone this repository.
3. Run `start.bat`.
4. Open `http://127.0.0.1:8000` in your browser.

The first launch creates a virtual environment and installs dependencies.

## Manual setup

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8000`.

## Run tests

```powershell
python -m pip install -r requirements.txt
python -m compileall -q app.py tests
python -m unittest discover -s tests -v
```

## Responsible use and limitations

- This is a local personal-use tool and should remain bound to `127.0.0.1`; do not expose it to the public internet.
- It downloads files accessible from the machine running it. It does not bypass logins, paywalls, CAPTCHAs, or other access controls.
- The crawler applies page/depth limits and checks `robots.txt` when available. Respect website terms, crawl policies, rate limits, copyright, and applicable law.
- Discovery may be incomplete on JavaScript-driven websites, search-form-only pages, or for PDFs that are not linked from reachable pages or sitemaps.
- Files are saved under the project's `downloads/` directory. Downloaded files are excluded from Git.
