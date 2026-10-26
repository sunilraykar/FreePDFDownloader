# FreePDFDownloader

A free local web app for discovering and bulk-downloading PDFs linked from a website.

## Planned capabilities
- Crawl same-host pages with depth and page limits.
- Discover PDFs through page links and common sitemap locations.
- Select individual PDFs or all results.
- Bulk download with retry, safe filenames, and status reporting.
- Export discovered links to CSV.
- Windows startup script; no paid hosting required.

## Requirements
Python 3.10+

## Windows setup
1. Install Python from https://www.python.org/downloads/ and enable Add Python to PATH.
2. Download or clone this repository.
3. Run `start.bat`.
4. Open `http://127.0.0.1:8000`.

Manual setup:

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

## Responsible use
The tool is intended for local use and publicly accessible files. It does not bypass authentication, paywalls, CAPTCHA, or access controls. Respect site terms, robots guidance, rate limits, copyright, and applicable law. Discovery can be incomplete on JavaScript-heavy sites or where PDFs are not linked from pages or sitemaps.
