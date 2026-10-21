"""Extract best-effort company and location details from public search results."""
from __future__ import annotations

import html
import re
from urllib.parse import unquote, urlsplit


UNKNOWN_COMPANY = "Company not identified by search result"
UNKNOWN_LOCATION = "Not verified; see posting"

_CITY_TERMS = (
    "Poonamallee", "Chennai", "Bengaluru", "Bangalore", "Hyderabad", "Mumbai",
    "Pune", "Delhi", "Gurugram", "Gurgaon", "Noida", "Kolkata", "Ahmedabad",
    "Remote", "India", "United States", "United Kingdom", "Canada", "Australia",
)


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def extract_company(title: str, snippet: str = "", link: str = "", explicit: str = "") -> tuple[str, str]:
    candidate = _plain(explicit)
    if candidate and candidate.casefold() not in {"unknown", "unknown company", UNKNOWN_COMPANY.casefold()}:
        return candidate, "Search provider"

    title_text = _plain(title)
    match = re.match(r"(.+?)\s+hiring\s+", title_text, re.IGNORECASE)
    if match:
        return match.group(1).strip(" -|"), "Title"
    match = re.search(r"\bjob application for\s+.+?\s+at\s+(.+?)(?:\s*\|.*)?$", title_text, re.IGNORECASE)
    if match:
        return match.group(1).strip(" -|"), "Title"

    snippet_text = _plain(snippet)
    match = re.search(
        r"\bcompany\s*:\s*(.+?)\s+(?=(?:location|experience|salary|job\s*type|work\s*type)\s*:|$)",
        snippet_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" .;,-"), "Snippet"

    path = unquote(urlsplit(link).path)
    match = re.search(r"(?:^|[-])at-(.+?)-\d{6,}(?:[-/]|$)", path, re.IGNORECASE)
    if match:
        slug = match.group(1).replace("-", " ").strip()
        return slug.title(), "Posting URL"
    return UNKNOWN_COMPANY, ""


def extract_location(title: str, snippet: str = "") -> tuple[str, str]:
    title_text = _plain(title)
    # Keep the location segment containing a recognizable place, not the search-query region.
    terms = sorted(_CITY_TERMS, key=len, reverse=True)
    place_match = None
    for term in terms:
        match = re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", title_text, re.IGNORECASE)
        if match:
            place_match = match
            break
    if place_match:
        start = place_match.start()
        in_marker = title_text.rfind(" in ", 0, start)
        dash_marker = title_text.rfind(" - ", 0, start)
        if in_marker >= 0 and in_marker + 4 > dash_marker + 3:
            start = in_marker + 4
        elif dash_marker >= 0:
            start = dash_marker + 3
        end = len(title_text)
        for marker in (" | ", " - indeed", " - glassdoor"):
            index = title_text.casefold().find(marker, place_match.end())
            if index >= 0:
                end = min(end, index)
        value = title_text[start:end].strip(" -|,()")
        value = re.sub(r"\s+", " ", value)
        if value:
            return value, "Title"

    snippet_text = _plain(snippet)
    match = re.search(
        r"\b(?:job\s+)?location\s*(?:(?:is|:|-)\s*)?(?:based\s+in\s+|located\s+in\s+)?([^.;|\n]+)",
        snippet_text,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(r"\b(?:based|located)\s+in\s+([^.;|\n]+)", snippet_text, re.IGNORECASE)
    if match:
        return match.group(1).strip(" -,"), "Snippet"
    return UNKNOWN_LOCATION, ""
