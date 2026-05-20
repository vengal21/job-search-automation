# Job Search Automation Workflow

## Overview

A Python-based web application with a beautiful UI that:
- Searches multiple job boards for matching roles
- Filters by location (Chennai onsite / Remote India / Remote Global / Outside India onsite)
- Targets: Business Analyst, Data Analyst, BI, Data-related, Project Management, Stakeholder/Client roles
- Experience filter: ~1–3 years (targeting 1.5 YoE candidates)
- Only fetches jobs posted in the **last 24 hours**
- Exports results to **Excel (.xlsx)** with direct apply links
- Re-searches fresh every time you upload a resume or change a designation

---

## Architecture

```
[Web UI (Flask + HTML/JS)] 
    ↓ user input (resume PDF / designation text + location filter)
[Job Search Engine (Python)]
    ↓ concurrent API/scraping calls
[Multiple Job Boards]
    - LinkedIn Jobs (via linkedin_jobs_scraper or web scraping)
    - Indeed (via indeed-scraper / BeautifulSoup)
    - Naukri.com (via requests + BeautifulSoup)
    - Internshala (for fresher/1.5yr roles)
    - Glassdoor (via web scraping)
    - Shine.com
    - TimesJobs
    ↓
[Job Deduplication & Scoring Engine]
    - Score each job against profile keywords
    - Filter: posted in last 24 hours
    - Filter: location matches preference
    ↓
[Export Engine]
    - Excel (.xlsx) via openpyxl with apply links, color-coded scores
    - Option to open Google Sheets (via link)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web UI | Flask (Python) + Vanilla HTML/CSS/JS |
| Job Scraping | `requests`, `BeautifulSoup`, `selenium` (fallback) |
| LinkedIn | `linkedin-jobs-scraper` or `jobspy` library |
| Data Processing | `pandas` |
| Excel Export | `openpyxl` |
| Resume Parsing | `PyPDF2` + keyword extraction |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |
| Scheduling | On-demand (per search trigger) |

> **Key library**: `python-jobspy` — a unified scraper for LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs all in one call. This is the most reliable approach without needing API keys.

---

## Proposed File Structure

```
c:\Users\W2632\project\job_search\
├── app.py                  # Flask web server
├── job_searcher.py         # Core search + filter engine
├── resume_parser.py        # PDF resume → keywords
├── exporter.py             # Excel export logic
├── config.py               # Job titles, keywords, experience levels
├── requirements.txt
├── templates\
│   └── index.html          # Beautiful UI
├── static\
│   ├── style.css
│   └── app.js
└── exports\                # Generated Excel files saved here
```

---

## Proposed Changes

### [NEW] `requirements.txt`
Dependencies: `flask`, `python-jobspy`, `pandas`, `openpyxl`, `PyPDF2`, `requests`, `beautifulsoup4`

### [NEW] `config.py`
- Target job titles list
- Experience keywords
- Location mappings (Chennai / Remote-India / Remote-Global / Outside-India)
- Scoring keywords from profile

### [NEW] `resume_parser.py`
- Reads uploaded PDF resume
- Extracts text, pulls out skills, designations, experience years
- Returns structured keyword dict for search

### [NEW] `job_searcher.py`
- Uses `python-jobspy` to query LinkedIn, Indeed, Glassdoor, ZipRecruiter
- Also queries Naukri.com via direct HTTP scraping
- Filters by: `date_posted <= 24h`, location preference, keyword match
- Scores each job 0–100 based on keyword overlap
- Returns pandas DataFrame

### [NEW] `exporter.py`
- Takes DataFrame → writes styled Excel with:
  - Color-coded match score column
  - Clickable "Apply" hyperlinks
  - Auto-fit columns
  - Job title, company, location, salary, posted date, source board

### [NEW] `app.py`
- Flask server with routes:
  - `GET /` → serve UI
  - `POST /search` → trigger job search, return JSON results
  - `POST /upload-resume` → parse resume, extract keywords
  - `GET /export` → download Excel file

### [NEW] `templates/index.html` + `static/style.css`
- Dark mode, glassmorphism UI
- Resume upload dropzone
- OR manual designation input
- Location toggle: Chennai / Remote India / Remote World / Onsite Outside India
- Live results table with match score badges
- "Export to Excel" button

---

## Job Boards Targeted

| Board | Method | India Coverage |
|---|---|---|
| LinkedIn | `python-jobspy` | ✅ |
| Indeed | `python-jobspy` | ✅ |
| Glassdoor | `python-jobspy` | ✅ |
| ZipRecruiter | `python-jobspy` | Partial |
| Naukri.com | BeautifulSoup scraping | ✅ Best for India |
| Google Jobs | `python-jobspy` (google mode) | ✅ |

---

## Target Job Roles (pre-configured)

- Business Analyst
- Data Analyst
- Business Intelligence Analyst
- BI Developer
- Power BI Analyst
- Tableau Developer
- Data Reporting Analyst
- Project Analyst
- Junior Project Manager
- Client Relations Analyst
- Stakeholder Management Analyst
- MIS Analyst
- Operations Analyst
- Product Analyst

---

## Location Logic

| Mode | What it searches |
|---|---|
| Chennai Onsite | `location=Chennai` + onsite only |
| Remote India | `location=India` + remote only |
| Remote Global | `location=Worldwide` + remote only |
| Onsite Outside India | Configurable cities (Singapore, Dubai, etc.) + onsite |

---

## Open Questions

> [!IMPORTANT]
> **Naukri.com Scraping**: Naukri has bot protection. The scraper may need Selenium for reliable results. Do you want me to include Selenium support (requires Chrome + ChromeDriver installed)?

> [!IMPORTANT]
> **Google Sheets**: Exporting directly to Google Sheets requires a Google Service Account (OAuth). Since that's complex to set up, I'll produce a local Excel file by default + a button to upload manually. Alternatively, I can convert the Excel to a shareable Google Sheets link. Which do you prefer?

> [!NOTE]
> **Resume Upload**: The resume parser extracts keywords from your PDF. The more detailed your resume, the better the job matching. Alternatively, you can just type designations manually.

> [!NOTE]
> **Rate Limiting**: Job boards may throttle heavy scraping. The tool uses delays and User-Agent rotation to minimize this.

---

## Verification Plan

### Automated
- Run the Flask app: `python app.py`
- Upload a sample resume PDF
- Trigger a search with location = "Chennai + Remote India"
- Verify results appear in the UI table
- Download Excel and verify hyperlinks work

### Manual
- Check that jobs are dated within 24 hours
- Verify apply links open the correct job postings
- Confirm export file opens cleanly in Excel

