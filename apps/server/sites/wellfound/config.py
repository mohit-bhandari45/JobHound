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


def _load_headers_and_cookies() -> tuple[dict, dict]:
    static_headers = json.loads((_config_dir / "headers.json").read_text())
    session = json.loads((_config_dir / "session.json").read_text())
    headers = {**static_headers, **session["headers"]}
    cookies = session["cookies"]
    return headers, cookies


def update_session_from_curl(curl: str) -> None:
    curl = curl.strip()
    if not curl.startswith("curl "):
        raise ValueError("invalid input: must be a curl command starting with 'curl '")

    session_path = _config_dir / "session.json"
    session = json.loads(session_path.read_text())

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
            "curl parsed but nothing matched session.json — "
            "no known headers or cookies found. is this the right request?"
        )

    session_path.write_text(json.dumps(session, indent=4))
    print(f"\nsession.json updated ({len(headers_updated)} headers, {len(cookies_updated)} cookies)")



WF_HEADERS, WF_COOKIES = _load_headers_and_cookies()



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

if sys.argv[1] == "update_session":
    print(_config_dir)
    curl_input = pyperclip.paste()
    update_session_from_curl(curl_input)
