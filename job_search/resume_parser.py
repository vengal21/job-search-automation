# =============================================================================
# resume_parser.py — Extract keywords from a PDF resume
# =============================================================================

import re
import logging
from pathlib import Path

try:
    import pdfplumber
    PDF_BACKEND = "pdfplumber"
except ImportError:
    pdfplumber = None
    PDF_BACKEND = None



logger = logging.getLogger(__name__)


# ─── Known Skills to Detect in Resume ────────────────────────────────────────
SKILL_PATTERNS = [
    # Data & BI Tools
    r'\bSQL\b', r'\bMySQL\b', r'\bPostgreSQL\b', r'\bOracle\b', r'\bMongoDB\b',
    r'\bPower\s?BI\b', r'\bTableau\b', r'\bLooker\b', r'\bQlikView\b', r'\bQlikSense\b',
    r'\bExcel\b', r'\bPivot\s?Table[s]?\b', r'\bVLOOKUP\b', r'\bVBA\b',
    r'\bPower\s?Query\b', r'\bPower\s?Pivot\b', r'\bPower\s?Automate\b',
    r'\bPython\b', r'\bPandas\b', r'\bNumPy\b', r'\bScikit[- ]?learn\b',
    r'\bETL\b', r'\bData\s?Warehouse\b', r'\bSnowflake\b', r'\bAzure\b',
    r'\bAWS\b', r'\bGoogle\s?Cloud\b', r'\bGCP\b', r'\bDatabricks\b',
    r'\bSAP\b', r'\bSalesforce\b', r'\bServiceNow\b',
    r'\bR\b', r'\bSPSS\b', r'\bSAS\b',
    # PM / BA Tools
    r'\bJIRA\b', r'\bConfluence\b', r'\bTrello\b', r'\bAsana\b',
    r'\bAgile\b', r'\bScrum\b', r'\bKanban\b',
    r'\bSharePoint\b', r'\bMS\s?Project\b', r'\bMonday\.com\b',
    # Finance / Domain
    r'\bFinance\b', r'\bAccounting\b', r'\bInvoice\b', r'\bBudget\b',
    r'\bForecasting\b', r'\bFP&A\b', r'\bP&L\b', r'\bBalance\s?Sheet\b',
    r'\bCRM\b', r'\bERP\b', r'\bHR\b', r'\bSupply\s?Chain\b',
    # Skills
    r'\bRequirements\s?Gathering\b', r'\bStakeholder\b', r'\bBRD\b',
    r'\bFRD\b', r'\bUser\s?Stories\b', r'\bUse\s?Cases\b',
    r'\bData\s?Analysis\b', r'\bBusiness\s?Analysis\b',
    r'\bData\s?Visualization\b', r'\bDashboard[s]?\b',
    r'\bKPI\b', r'\bMetrics\b', r'\bReporting\b',
    r'\bClient\b', r'\bStakeholder\s?Management\b',
    r'\bProject\s?Management\b', r'\bProcess\s?Improvement\b',
    r'\bGap\s?Analysis\b', r'\bRoot\s?Cause\b', r'\bRisk\s?Management\b',
    r'\bMachine\s?Learning\b', r'\bArtificial\s?Intelligence\b', r'\bNLP\b',
    r'\bAPI\b', r'\bREST\b', r'\bMicroservices\b', r'\bDevOps\b',
    r'\bGit\b', r'\bJenkins\b', r'\bCI/CD\b',
    r'\bMIS\b', r'\bData\s?Modell?ing\b', r'\bData\s?Governance\b',
    # Networking & Security
    r'\bSonicWall\b', r'\bPalo\s?Alto\b', r'\bFirewall[s]?\b', r'\bVPN[s]?\b',
    r'\bVLAN[s]?\b', r'\bRouting\b', r'\bSwitching\b', r'\bWazuh\b',
    r'\bZabbix\b', r'\bSIEM\b', r'\bWireshark\b', r'\btcpdump\b',
    r'\bNmap\b', r'\bAnsible\b', r'\bRADIUS\b', r'\bFreeRADIUS\b',
    r'\bTOTP\b', r'\bMFA\b', r'\b2FA\b', r'\bDHCP\b', r'\bDNS\b',
    r'\bOSPF\b', r'\bBGP\b', r'\bTCP/IP\b', r'\bLAN/WAN\b',
    r'\bNACL[s]?\b', r'\bLoad\s?Balancer\b', r'\bNetwork\s?Security\b',
]

# Patterns to extract experience years from resume text
EXPERIENCE_YEAR_PATTERNS = [
    r'(\d+\.?\d*)\s*\+?\s*years?\s*of\s*experience',
    r'experience\s*of\s*(\d+\.?\d*)\s*\+?\s*years?',
    r'(\d+\.?\d*)\s*\+?\s*yrs?\s*of\s*experience',
    r'total\s*experience[:\s]+(\d+\.?\d*)',
]

# ─── LLM-Powered Parser (primary) ──────────────────────────────────────────────────────

def parse_resume_with_llm(file_path: str) -> dict:
    """
    Primary resume parser. Tries LLM analysis first for rich extraction.
    Falls back to the rule-based parse_resume() if:
      - No LLM API key is configured
      - LLM request fails
      - LLM returns empty / invalid JSON

    Returns a profile dict with these extra keys vs the rule-based parser:
      - past_roles     : list of job titles the person has held
      - projects       : list of project descriptions
      - needs_role_input: True if LLM couldn't determine target role
      - llm_analysed   : True/False so callers know which path was taken
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume not found: {file_path}")

    text = _extract_text(path)
    if not text:
        raise ValueError("Could not extract text from the PDF. Is it a scanned image PDF?")

    # ── Try LLM first ────────────────────────────────────────────────────────
    try:
        from llm_helper import analyse_resume
        llm_result = analyse_resume(text)
    except Exception as e:
        logger.warning(f"LLM import/call failed: {e} — using rule-based parser.")
        llm_result = {}

    if llm_result and llm_result.get("skills"):  # LLM succeeded
        skills = llm_result.get("skills", [])
        past_roles = llm_result.get("past_roles", [])
        projects = llm_result.get("projects", [])
        suggested_titles = llm_result.get("suggested_titles", [])
        needs_role_input = llm_result.get("needs_role_input", False)
        summary = llm_result.get("summary", "")

        # Also run rule-based extractor for experience years (LLM often misses exact numbers)
        experience_years = _extract_experience_years(text)

        logger.info(
            f"[LLM] Resume analysed: {len(skills)} skills, "
            f"roles={past_roles}, needs_input={needs_role_input}"
        )
        return {
            "raw_text":       text,
            "skills":         skills,
            "past_roles":     past_roles,
            "projects":       projects,
            "experience_years": experience_years,
            "suggested_titles": suggested_titles,
            "search_keywords":  skills,
            "needs_role_input": needs_role_input or not suggested_titles,
            "summary":          summary,
            "llm_analysed":     True,
        }

    # ── Fallback: rule-based ────────────────────────────────────────────────────
    logger.info("[Fallback] Using rule-based resume parser.")
    base = parse_resume(file_path)
    base["past_roles"] = []
    base["projects"] = []
    base["needs_role_input"] = False
    base["summary"] = ""
    base["llm_analysed"] = False
    return base


# ─── Rule-Based Parser (fallback) ────────────────────────────────────────────────────

def parse_resume(file_path: str) -> dict:
    """
    Parse a PDF resume and extract:
    - Raw text
    - Detected skills / keywords
    - Estimated years of experience
    - Suggested job titles to search

    Returns a dict ready for use in job_searcher.py
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume not found: {file_path}")

    text = _extract_text(path)
    if not text:
        raise ValueError("Could not extract text from the PDF. Is it a scanned image PDF?")

    skills = _extract_skills(text)
    experience_years = _extract_experience_years(text)
    suggested_titles = _suggest_job_titles(text, skills)
    free_keywords = _extract_free_keywords(text)

    # Merge pattern-matched skills with free-text keywords, deduping
    all_keywords = list(dict.fromkeys(skills + free_keywords))

    logger.info(
        f"Resume parsed: {len(skills)} pattern skills + {len(free_keywords)} free keywords, "
        f"~{experience_years} yrs experience, titles: {suggested_titles}"
    )

    return {
        "raw_text": text,
        "skills": all_keywords,
        "experience_years": experience_years,
        "suggested_titles": suggested_titles,
        "search_keywords": all_keywords,
    }


def _extract_text(path: Path) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    if PDF_BACKEND == "pdfplumber" and pdfplumber:
        try:
            with pdfplumber.open(str(path)) as pdf:
                pages_text = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages_text)
        except Exception as e:
            logger.error(f"pdfplumber failed: {e}")
            return ""
    else:
        raise ImportError("pdfplumber is not installed. Run: pip install pdfplumber")


def _extract_skills(text: str) -> list[str]:
    """Find all known skills mentioned in the resume text."""
    found = set()

    for pattern in SKILL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # Extract the clean match text
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                found.add(match.group(0).strip())

    return sorted(found)


def _extract_experience_years(text: str) -> float:
    """Try to detect total years of experience from resume text."""
    for pattern in EXPERIENCE_YEAR_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return 1.5  # Default to 1.5 years if not detected


ROLE_CATEGORIES = {
    "network_security": [
        "Network Security Engineer",
        "Network Engineer",
        "Network Administrator",
        "Security Engineer",
        "System Administrator"
    ],
    "data_analytics": [
        "Data Analyst",
        "Data Scientist",
        "BI Analyst",
        "Business Analyst",
        "MIS Analyst",
        "Reporting Analyst",
        "Product Analyst"
    ],
    "project_management": [
        "Project Analyst",
        "Project Coordinator",
        "Scrum Master",
        "Project Manager"
    ]
}

def _suggest_job_titles(text: str, skills: list[str]) -> list[str]:
    """
    Based on skills and raw text found in resume, suggest the most relevant job titles.
    Prioritises titles directly mentioned or strongly implied in the resume.
    """
    suggestions_priority = []   # ordered: first match = highest priority
    text_lower = text.lower()
    skills_lower = [s.lower() for s in skills]

    # Check for strong role indicators in the resume (order = priority)
    role_indicators = [
        # Network & Security
        ("Network Security Engineer", ["network security", "firewall", "vpn", "sonicwall", "palo alto", "security engineer", "utm", "ips/ids", "threat detection"]),
        ("Network Engineer",          ["network engineer", "routing", "switching", "vlan", "lan/wan", "ccna", "ccnp", "ospf", "bgp", "tcp/ip"]),
        ("Network Administrator",     ["network administrator", "junior network administrator", "network admin", "active directory", "dhcp", "dns"]),
        ("Security Engineer",         ["security engineer", "siem", "wazuh", "zabbix", "vulnerability", "incident handling", "threat hunt"]),
        ("System Administrator",      ["system administrator", "sysadmin", "linux administrator", "windows server", "ansible", "rhel"]),
        
        # Existing data/analyst roles...
        ("Data Scientist",          ["data science", "machine learning", "deep learning", "nlp", "scikit", "tensorflow", "pytorch"]),
        ("Machine Learning Engineer",["machine learning", "ml engineer", "deep learning", "neural network"]),
        ("Financial Analyst",       ["financial analyst", "finance", "fp&a", "p&l", "balance sheet", "forecasting", "budgeting"]),
        ("Business Analyst",        ["business analyst", "brd", "frd", "requirements gathering", "business analysis", "business requirements"]),
        ("Data Analyst",            ["data analyst", "data analysis", "sql", "python", "etl", "data pipeline"]),
        ("BI Analyst",              ["power bi", "tableau", "looker", "qlikview", "data visualization", "dashboard", "bi developer"]),
        ("MIS Analyst",             ["mis", "mis report", "mis analyst", "management information"]),
        ("Project Analyst",         ["project management", "jira", "agile", "scrum", "project coordinator", "project analyst"]),
        ("Reporting Analyst",       ["reporting", "kpi", "metrics", "excel", "reports"]),
        ("Product Analyst",         ["product analyst", "product management", "product metrics", "roadmap"]),
        ("HR Analyst",              ["human resource", "hr analyst", "hris", "payroll", "recruitment", "talent"]),
        ("Supply Chain Analyst",    ["supply chain", "logistics", "procurement", "inventory", "warehouse"]),
        ("Operations Analyst",      ["operations", "process improvement", "workflow", "sop"]),
        ("Salesforce Analyst",      ["salesforce", "crm", "salesforce admin"]),
        ("SAP Analyst",             ["sap", "sap hana", "sap fico", "sap mm", "sap sd"]),
    ]

    seen = set()
    matched_categories = set()
    for title, keywords in role_indicators:
        if any(kw in text_lower for kw in keywords):
            if title not in seen:
                suggestions_priority.append(title)
                seen.add(title)
                # Identify which category was matched
                for category, titles in ROLE_CATEGORIES.items():
                    if title in titles:
                        matched_categories.add(category)

    # If nothing matched, return empty — caller must ask user for target role
    if not suggestions_priority:
        logger.info("No resume role indicators matched — returning empty suggestions (will prompt user)")
        return []

    # Instead of appending unrelated PRIMARY_SEARCH_TERMS, suggest other titles from the matched categories!
    expanded_suggestions = list(suggestions_priority)
    for cat in matched_categories:
        for title in ROLE_CATEGORIES[cat]:
            if title not in seen:
                expanded_suggestions.append(title)
                seen.add(title)

    logger.info(f"Suggested job titles from resume: {expanded_suggestions[:10]}")
    return expanded_suggestions[:10]


def _extract_free_keywords(text: str) -> list[str]:
    """
    Extract likely tech/skill keywords from resume text that weren't
    captured by the hardcoded SKILL_PATTERNS. Looks for:
    - CamelCase words (e.g. PowerBI, SalesForce)
    - All-caps acronyms 2-8 chars (e.g. ERP, CRM, HRIS)
    - Common tech patterns not in pattern list
    """
    found = set()

    # All-caps acronyms (2-8 letters)
    acronyms = re.findall(r'\b[A-Z]{2,8}\b', text)
    # Filter out common English stop-words in caps
    stop_caps = {"THE", "AND", "FOR", "WITH", "FROM", "THAT", "THIS",
                 "HAVE", "WILL", "YOUR", "WHICH", "ARE", "NOT", "BUT",
                 "ALL", "WHO", "HAS", "WAS", "CAN", "HER", "HIM", "ITS"}
    for ac in acronyms:
        if ac not in stop_caps and len(ac) >= 2:
            found.add(ac)

    return sorted(found)[:30]  # Cap at 30 extra keywords


def get_default_profile() -> dict:
    """
    Return a minimal empty profile dict. Skills and titles must be provided by user input.
    This is used as a base structure only — no defaults are injected.
    """
    return {
        "raw_text": "",
        "skills": [],
        "experience_years": "",
        "suggested_titles": [],
        "search_keywords": [],
    }
