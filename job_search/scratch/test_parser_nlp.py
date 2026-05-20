import logging
from resume_parser import parse_resume

# Setup logging
logging.basicConfig(level=logging.INFO)

# We can test parsing directly. Let's write a simple pdf mock or run rule-based parsing on a dummy file
# Let's inspect get_default_profile or _suggest_job_titles
from resume_parser import _suggest_job_titles, _extract_skills

text = "Candidate with expertise in Java, Spring Boot, REST APIs. Worked on backend developer roles."
skills = _extract_skills(text)
suggested = _suggest_job_titles(text, skills)

print("Pattern matching suggested:", suggested)

# Now test nlp prediction inside parser
try:
    from nlp_model import nlp_model
    nlp_pred = nlp_model.predict(text)
    print("NLP prediction:", nlp_pred)
except Exception as e:
    print("NLP load error:", e)
