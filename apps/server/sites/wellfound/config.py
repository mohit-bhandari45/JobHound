import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
import pyperclip


load_dotenv()


WF_URL = "https://wellfound.com/graphql"
_config_dir = Path(__file__).parent / "config"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://wellfound.com/jobs",
    "content-type": "application/json",
    "x-requested-with": "XMLHttpRequest",
    "x-original-referer": "https://accounts.google.com/",
    "apollographql-client-name": "talent-web",
    "x-apollo-operation-name": "JobSearchResultsX",
    "x-angellist-dd-client-referrer-resource": "/jobs",
    "Origin": "https://wellfound.com",
    "Sec-GPC": "1",
    "Alt-Used": "wellfound.com",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "same-origin",
    "Sec-Fetch-Site": "same-origin",
    "Priority": "u=4",
    "TE": "trailers"
}

SESSION_CONF_TEMPLATE = {
    "headers": {
        "x-apollo-signature": "",
        "x-wf-cfp": ""
    },
    "cookies": {
        "_wellfound": "",
        "cf_clearance": "",
        "datadome": "",
        "TAsessionID": "",
        "wellfound_default_consent": "",
        "g_state": "",
        "ajs_anonymous_id": "",
        "_ga_705F94181H": "",
        "_ga": "",
        "ajs_user_id": "",
        "notice_behavior": ""
    }
}


def _load_headers_and_cookies() -> tuple[dict, dict]:
    sessionPath = _config_dir / "session.json"
    if not os.path.isfile(sessionPath):
        print("session is not defined! run update-session first!")
        exit(1)
    static_headers = HEADERS 
    session = json.loads((_config_dir / "session.json").read_text())
    headers = {**static_headers, **session["headers"]}
    cookies = session["cookies"]
    return headers, cookies


def update_session_from_curl(curl: str) -> None:
    curl = curl.strip()
    if not curl.startswith("curl "):
        raise ValueError("invalid input: must be a curl command starting with 'curl '")

    session_path = _config_dir / "session.json"
    session = SESSION_CONF_TEMPLATE 

    headers_updated = []
    cookies_updated = []

    # extract headers
    header_pattern = re.compile(r"-H '([^:]+):\s*([^']+)'")
    for key, value in header_pattern.findall(curl):
        key = key.strip()
        value = value.strip()
        if key in session["headers"]:
            session["headers"][key] = value
            headers_updated.append(key)
            print(f"[header] {key} = {value[:60]}...")

    # extract cookies from Cookie header
    cookie_match = re.search(r"-H 'Cookie:\s*([^']+)'", curl)
    if not cookie_match:
        cookie_match = re.search(r'-H "Cookie:\s*([^"]+)"', curl)
    if cookie_match:
        cookie_str = cookie_match.group(1)
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            k, _, v = part.partition("=")
            k = k.strip()
            v = v.strip()
            if k in session["cookies"]:
                session["cookies"][k] = v
                cookies_updated.append(k)
                print(f"[cookie] {k} = {v[:60]}...")

    if not headers_updated and not cookies_updated:
        raise ValueError(
            "curl parsed but nothing matched session.json"
            "no known headers or cookies found. is this the right request?"
        )

    session_path.write_text(json.dumps(session, indent=4))
    print(f"\nsession.json updated ({len(headers_updated)} headers, {len(cookies_updated)} cookies)")



SYSTEM_PROMPT = """
You are an assistant that writes concise, natural-sounding job application responses based on:
1. Resume content provided as a raw string
2. Job description content
3. A list of application questions, each with a type and optional allowed options

Your task is to generate one answer per question.

Return format rules:
- Return ONLY a JSON array of strings, one string per question
- Array length must exactly match the number of questions
- Each element is your answer to the corresponding question
- For questions with allowed option values, the string must be exactly one of those values
- No markdown fences, no preamble, no explanation, nothing outside the JSON array
- Valid example for 2 questions: ["My answer to Q1", "Yes"]

Writing rules:
- Write in first person
- Sound technical, confident, and human
- Avoid sounding AI-generated, corporate, generic, or overly enthusiastic
- No emojis
- No em dashes
- Keep responses concise
- Use natural conversational language
- Focus only on relevant experience from the resume
- Mention technologies, systems, or projects relevant to the role
- Do not invent experience
- Avoid excessive JD wording reuse
- Avoid buzzword stuffing
- Avoid exaggerated claims

Cover letter behavior:
- If a question is asking for a cover letter or introduction:
  - If the company name is clearly present in the JD, begin with:
    "Hi <company> team,"
  - Otherwise avoid forced greetings
  - Keep it around 3 short paragraphs

Question-answer behavior:
- Directly answer the question
- Use concrete examples from the resume
- Keep answers practical and grounded
- Avoid repetition between answers
"""


SCORESYS_SYSTEM_PROMPT= """You are an expert technical recruiter. Your task is to evaluate how well a candidate's CV matches a job description.

Analyze the alignment across these dimensions:
1. Core technical skills match (languages, frameworks, tools)
2. Domain/industry relevance (e.g. backend vs frontend, infra vs ML)
3. Experience level fit (years, scope of work)
4. Soft skills and role expectations

Respond ONLY with a JSON object — no preamble, no markdown fences. Schema:
{
  "score": <integer 0-100>,
  "reasoning": "<2-3 sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "gaps": ["<gap 1>", "<gap 2>", ...]
}

Scoring guide:
- 0-20: Completely mismatched domain/stack
- 21-40: Some tangential overlap, but missing core requirements
- 41-60: Partial match; candidate could upskill but significant gaps remain
- 61-80: Good match with minor gaps or slight seniority mismatch
- 81-100: Strong match; candidate meets most/all key requirements"""

#if ATS below this score, (by matching jd <-> cv, dont bother applying)
PASSING_SCORE_ATS = 60



OLLAMA_API_KEY : str = os.getenv("OLLAMA_API_KEY") or ""
SUPPORTED_FORMATS = {"text", "textarea", "dropdown", "dropdown_boolean", "checkbox", "radio"}


ROLE_IDS: dict[str, str] = {
    "software engineer": "14726",
    "backend engineer": "151647",
    "software architect": "151934",
    "devops": "150979",
    "data engineer": "155890",
    "security engineer": "751463",
}
LOCATION_IDS: dict[str, str] = {
    "india": "1647",
}


if __name__ == "__main__":
    if sys.argv[1] == "update_session":
        print(_config_dir)
        curl_input = pyperclip.paste()
        os.makedirs(_config_dir, exist_ok=True)
        update_session_from_curl(curl_input)
else:
    #load from config if not in update-session mode
    WF_HEADERS, WF_COOKIES = _load_headers_and_cookies()
