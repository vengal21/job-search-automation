import logging
import json
import requests
from config import LLM_PROVIDER, LLM_API_KEY

logger = logging.getLogger(__name__)

# ─── Resume Analysis ──────────────────────────────────────────────────────────

def analyse_resume(resume_text: str) -> dict:
    """
    Use the configured LLM to intelligently analyse a resume and extract:
      - skills         : list of technical + soft skills
      - past_roles     : list of job titles the person has held
      - projects       : list of project descriptions / domains worked on
      - suggested_titles: list of job titles to search for (most relevant first)
      - needs_role_input: True if LLM couldn't determine target role
      - summary        : 1-2 sentence plain-English summary of the candidate

    Falls back to an empty dict (triggering rule-based parser) if:
      - LLM_API_KEY is not set
      - LLM request fails
      - Response is not valid JSON
    """
    if not LLM_API_KEY:
        logger.info("LLM_API_KEY not set — skipping AI resume analysis, using rule-based parser.")
        return {}

    prompt = _build_resume_prompt(resume_text)

    try:
        if LLM_PROVIDER.lower() == "gemini":
            raw = _call_gemini(prompt)
        elif LLM_PROVIDER.lower() == "openai":
            raw = _call_openai(prompt)
        else:
            logger.warning(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")
            return {}

        # Strip markdown fences if LLM wraps JSON in ```json ... ```
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw.strip())
        logger.info(
            f"LLM resume analysis: {len(result.get('skills', []))} skills, "
            f"roles={result.get('past_roles', [])}, "
            f"suggested={result.get('suggested_titles', [])}, "
            f"needs_input={result.get('needs_role_input', False)}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON for resume analysis: {e}")
        return {}
    except Exception as e:
        logger.error(f"LLM resume analysis failed: {e}")
        return {}


def _build_resume_prompt(resume_text: str) -> str:
    # Truncate very long resumes to avoid token limits
    truncated = resume_text[:6000] if len(resume_text) > 6000 else resume_text
    return f"""You are an expert HR analyst and career counsellor. Analyse the following resume text and return ONLY a valid JSON object with no additional explanation.

The JSON must have exactly these keys:
{{
  "skills": ["list of technical and domain skills found"],
  "past_roles": ["list of job titles the person has actually held, in reverse chronological order"],
  "projects": ["short description of each distinct project or domain worked on"],
  "suggested_titles": ["list of 5-8 specific job titles to search for, ordered from most to least relevant based on skills and experience"],
  "needs_role_input": false,
  "summary": "1-2 sentence plain-English summary of the candidate"
}}

Rules:
- If the resume clearly shows what kind of role the person wants, set needs_role_input to false and fill suggested_titles.
- If there is not enough information to determine the best-fit role (e.g., very sparse resume, student with no work experience), set needs_role_input to true and leave suggested_titles as an empty list.
- suggested_titles must be specific job board search terms like "Data Analyst", "Business Analyst", "Financial Analyst", "HR Analyst", "Supply Chain Analyst" etc. — not generic phrases.
- Do NOT include markdown, code fences, or any text outside the JSON object.

Resume Text:
\"\"\"
{truncated}
\"\"\"
"""


# ─── Q&A Answer (existing) ────────────────────────────────────────────────────

def get_answer_from_llm(question_text: str, profile: dict) -> str:
    """
    Given an application question and a user profile context,
    use an LLM to generate the best single-line answer.
    """
    if not LLM_API_KEY:
        logger.warning("No LLM_API_KEY configured. Skipping LLM logic.")
        return ""

    context = _build_profile_context(profile)
    prompt = f"""You are an expert job applicant assistant. You need to answer a specific job application form question based on the user's profile.
Answer concisely, often in a single line or short paragraph. Do not add conversational filler.
If the profile lacks the information to answer, state "UNKNOWN" so the system can fallback to asking the human.

User Profile:
{context}

Question:
{question_text}
    """

    try:
        if LLM_PROVIDER.lower() == "gemini":
            return _call_gemini(prompt)
        elif LLM_PROVIDER.lower() == "openai":
            return _call_openai(prompt)
        else:
            logger.warning(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")
            return ""
    except Exception as e:
        logger.error(f"Error querying LLM: {e}")
        return ""


def _build_profile_context(profile: dict) -> str:
    """Convert a profile dictionary into a readable context string."""
    if not profile:
        return "No profile available."
    parts = []
    if profile.get('name'):
        parts.append(f"Name: {profile['name']}")
    if profile.get('skills'):
        parts.append(f"Skills: {', '.join(profile['skills'])}")
    if profile.get('past_roles'):
        parts.append(f"Past Roles: {', '.join(profile['past_roles'])}")
    if profile.get('projects'):
        parts.append(f"Projects: {'; '.join(profile['projects'])}")
    if profile.get('suggested_titles'):
        parts.append(f"Target Roles: {', '.join(profile['suggested_titles'])}")
    return "\n".join(parts)


# ─── LLM Backends ─────────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={LLM_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    try:
        answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "UNKNOWN" in answer.upper() and len(answer) < 20:
            return ""
        return answer
    except (KeyError, IndexError):
        return ""


def _call_openai(prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a concise HR analyst. Return only valid JSON when asked."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    try:
        answer = data["choices"][0]["message"]["content"].strip()
        if "UNKNOWN" in answer.upper() and len(answer) < 20:
            return ""
        return answer
    except (KeyError, IndexError):
        return ""
