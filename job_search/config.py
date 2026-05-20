# =============================================================================
# config.py — Central configuration for the Job Search Automation Workflow
# =============================================================================

# ─── Target Job Titles ────────────────────────────────────────────────────────
# These are the search terms used across all job boards.
# Grouped by category for UI display and targeted searching.

JOB_TITLE_GROUPS = {
    "Business Analysis": [
        "Business Analyst",
        "Jr Business Analyst",
        "Junior Business Analyst",
        "Associate Business Analyst",
    ],
    "Data Analysis": [
        "Data Analyst",
        "Junior Data Analyst",
        "Data Reporting Analyst",
        "MIS Analyst",
        "Operations Analyst",
        "Reporting Analyst",
    ],
    "Business Intelligence": [
        "BI Analyst",
        "Business Intelligence Analyst",
        "Power BI Analyst",
        "Tableau Developer",
        "BI Developer",
        "Data Visualization Analyst",
    ],
    "Project Management": [
        "Project Analyst",
        "Junior Project Manager",
        "Associate Project Manager",
        "Project Coordinator",
        "Scrum Master",
    ],
    "Client & Stakeholder": [
        "Client Relations Analyst",
        "Stakeholder Management Analyst",
        "Client Engagement Analyst",
        "Delivery Analyst",
    ],
    "Product & Strategy": [
        "Product Analyst",
        "Strategy Analyst",
        "Business Operations Analyst",
        "Process Analyst",
    ],
}

# Flat list of all titles for search queries
ALL_JOB_TITLES = [t for group in JOB_TITLE_GROUPS.values() for t in group]

# Primary search terms (used for aggregated searches — shorter list for speed)
PRIMARY_SEARCH_TERMS = [
    "Business Analyst",
    "Data Analyst",
    "Business Intelligence Analyst",
    "MIS Analyst",
    "Project Analyst",
    "BI Analyst",
    "Reporting Analyst",
    "Product Analyst",
]

# ─── Profile Matching Keywords ────────────────────────────────────────────────
# Used to score job descriptions against this profile.
# Add/remove based on your actual skills.

PROFILE_KEYWORDS = {
    "high": [       # High-weight keywords (more important to match)
        "business analyst",
        "data analyst",
        "business intelligence",
        "SQL",
        "Power BI",
        "Tableau",
        "stakeholder",
        "requirements gathering",
        "data analysis",
        "reporting",
    ],
    "medium": [     # Medium-weight keywords
        "Excel",
        "Python",
        "dashboard",
        "KPI",
        "metrics",
        "JIRA",
        "Agile",
        "Scrum",
        "project management",
        "client handling",
        "ETL",
        "data visualization",
        "MIS",
        "pivot table",
        "process improvement",
    ],
    "low": [        # Good-to-have keywords
        "Power Query",
        "Azure",
        "AWS",
        "Snowflake",
        "Looker",
        "Power Automate",
        "SharePoint",
        "data modeling",
        "gap analysis",
        "user stories",
    ],
}

# ─── Experience Levels ────────────────────────────────────────────────────────
EXPERIENCE_YEARS = 1.5
EXPERIENCE_RANGE = (0, 3)       # Min and max years (to catch 0-3 yr range jobs)

# Keywords in job description that indicate experience compatibility
EXPERIENCE_MATCH_PHRASES = [
    "0-2 years", "1-2 years", "1-3 years", "2-3 years",
    "0 to 2", "1 to 2", "1 to 3", "2 to 3",
    "fresher", "entry level", "junior", "associate",
    "0+ years", "1+ years", "2+ years",
]

EXPERIENCE_REJECT_PHRASES = [
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "5 years experience", "senior level", "10 years",
]

# ─── Location Modes ───────────────────────────────────────────────────────────
LOCATION_MODES = {
    "chennai": {
        "label": "Chennai Onsite",
        "icon": "🏢",
        "locations": ["Chennai, Tamil Nadu, India", "Chennai"],
        "glassdoor_locations": ["Chennai"],
        "is_remote": False,
        "country_indeed": "India",
        "description": "Onsite jobs in Chennai, TN",
    },
    "remote_india": {
        "label": "Remote — India",
        "icon": "🇮🇳",
        "locations": ["India"],
        "glassdoor_locations": ["India"],
        "is_remote": True,
        "country_indeed": "India",
        "description": "Work-from-home jobs across India",
    },
    "remote_global": {
        "label": "Remote — Global",
        "icon": "🌍",
        "locations": ["Worldwide", "Remote"],
        "is_remote": True,
        "country_indeed": None,
        "description": "Fully remote jobs anywhere in the world",
    },
    "outside_india": {
        "label": "Onsite — Outside India",
        "icon": "✈️",
        "locations": [],        # populated at runtime from user input
        "is_remote": False,
        "country_indeed": None,
        "description": "Onsite roles in cities outside India (e.g. Singapore, Dubai)",
    },
}

# Suggested cities for "Outside India" mode
SUGGESTED_OUTSIDE_INDIA_CITIES = [
    "Singapore", "Dubai, UAE", "Abu Dhabi, UAE",
    "London, UK", "Toronto, Canada", "Sydney, Australia",
    "Kuala Lumpur, Malaysia", "Doha, Qatar", "Riyadh, Saudi Arabia",
    "New York, USA", "San Francisco, USA", "Amsterdam, Netherlands",
]

# ─── Job Boards ───────────────────────────────────────────────────────────────
# Glassdoor is scraped separately (regional headers + location format)
JOB_BOARDS_JOBSPY = ["linkedin", "indeed", "google"]
NAUKRI_BASE_URL = "https://www.naukri.com"

# ─── Search Settings ─────────────────────────────────────────────────────────
HOURS_OLD = 24                  # Only jobs posted in last 24 hours
MAX_RESULTS_PER_QUERY = 30      # Per job title per board
REQUEST_DELAY_SECONDS = 2       # Delay between board requests
GLASSDOOR_DELAY_SECONDS = 5     # Extra delay — Glassdoor rate-limits aggressively
GLASSDOOR_MAX_RETRIES = 3

# ─── Scoring Weights ─────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "title_exact_match": 30,
    "title_partial_match": 15,
    "high_keyword_match": 3,    # per keyword found
    "medium_keyword_match": 2,  # per keyword found
    "low_keyword_match": 1,     # per keyword found
    "experience_match": 15,
    "recency_bonus": 10,        # posted in last 6 hours
}
MAX_SCORE = 100

# ─── Google Sheets Integration ────────────────────────────────────────────────
# Controls whether job results are automatically synced to Google Sheets
# after each search. Set to False to export to Excel only.
EXPORT_TO_SHEETS = True

# Name of the Google Spreadsheet to create / update.
# If a sheet with this name already exists in your Drive, it will be reused.
GOOGLE_SHEET_NAME = "Job Search Results — Automated"

# Path to your OAuth 2.0 client credentials file (relative to this script).
# Download from Google Cloud Console → APIs & Services → Credentials.
GOOGLE_CREDENTIALS_FILE = "credentials.json"

# Path where the OAuth token is cached after the first successful login.
GOOGLE_TOKEN_FILE = "token.json"

# ─── MySQL Database Configuration (MVC Model) ─────────────────────────────────
# Set this to your actual MySQL database credentials and host.
# Note: Special characters in the password (like '@') have been URL-encoded ('%40').
MYSQL_URI = "mysql+pymysql://root:Root%40123@localhost:3306/jobsearch"

# ─── Auto-Apply Configuration ────────────────────────────────────────────────
# Credentials for Naukri.com auto-apply bot.
# If these are left blank, the bot will skip auto-applying.
NAUKRI_EMAIL = ""
NAUKRI_PASSWORD = ""

LINKEDIN_EMAIL = ""
LINKEDIN_PASSWORD = ""

INDEED_EMAIL = ""
INDEED_PASSWORD = ""

GLASSDOOR_EMAIL = ""
GLASSDOOR_PASSWORD = ""

# ─── LLM Configuration ────────────────────────────────────────────────────────
# E.g., "gemini" or "openai"
LLM_PROVIDER = "gemini" 
LLM_API_KEY = ""

# Default path for resume upload in auto-apply
DEFAULT_RESUME_PATH = ""

