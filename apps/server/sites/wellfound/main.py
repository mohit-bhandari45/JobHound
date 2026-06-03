from models import *
from config import *
from pathlib import Path

import re
import requests
import json
import colorlog
import pdfplumber

import asyncio
import argparse
import logging
from datetime import datetime
from curl_cffi import requests, AsyncSession
from pydantic import ValidationError
from dotenv import load_dotenv


_session: AsyncSession | None = None
def get_session() -> AsyncSession:
    global _session
    if _session is None:
        _session = AsyncSession()
    return _session


def setup_logging() -> logging.Logger:
    timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M")
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{timestamp}.log"

    logger = logging.getLogger("wellfound")
    logger.setLevel(logging.DEBUG)

    plain_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    color_fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        },
    )

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(plain_fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(color_fmt)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"logging to {log_path}")
    return logger



async def getJobs(roleId: str, roleName: str = "", locationId: Optional[str] = None, locationName: str | None = "", maxPages: int = 10) -> list[JobListing]:
    jobs: list[JobListing] = []
    sess = get_session()
    for page in range(1, maxPages + 1):
        if locationName is not None:
            log.info(f"searching for role({roleName}), location({locationName}), page: {page}")
        else:
            log.info(f"searching for role({roleName}), location(worldwide), page: {page}")
        filter_input: dict = {
            "page": page,
            "roleTagIds": [roleId],
            "equity": {"min": None, "max": None},
            "includeJobsWithoutExperience": True,
            "jobTypes": ["full_time", "contract"],
            "remotePreference": "REMOTE_OPEN",
            "salary": {"min": None, "max": None},
            "yearsExperience": {"min": None, "max": None},
        }
        if locationId is not None:
            filter_input["locationTagIds"] = [locationId]

        payload = {
            "operationName": "JobSearchResultsX",
            "variables": {"filterConfigurationInput": filter_input},
            "extensions": {
                "operationId": "tfe/5f366cd305b4f13cf6098df75f7ff2bb92fa42b9a74cb3a3aec7bdc69c6b051e"
            },
        }
        resp = await sess.post(
            WF_URL,
            headers=WF_HEADERS,
            cookies=WF_COOKIES,
            json=payload,
            impersonate="firefox",
            timeout=300,
        )
        if resp.status_code == 403:
            raise SessionExpiredError(f"403 on getJobs page {page} — session expired, update cookies")
        if resp.status_code == 429:
            raise SessionExpiredError(f"429 on getJobs page {page} — rate limited")
        resp.raise_for_status()
        raw: dict = {}
        try:
            raw = resp.json()
            data = WellfoundResponse.model_validate(raw)
            for edge in data.data.talent.jobSearchResults.startups.edges:
                for company in edge.resolve_startups():
                    for job in company.highlightedJobListings:
                        job.companyId = company.id
                        job.companyName = company.name
                        jobs.append(job)
        except ValidationError as e:
            log.error(f"validation error at page {page}:\n{e}")
            log.debug(f"raw response snippet:\n{json.dumps(raw, indent=2)[:3000]}")
            return jobs
    return jobs



async def getJobInfo(jobId: str) -> JobListingDetail:
    payload = {
        "operationName": "JobApplicationModal",
        "variables": {"jobListingId": jobId},
        "extensions": {
            "operationId": "tfe/f4c70cbe1f045b5c06c22d1dea14819813abd702dd0b213999b3ea8c0538483c"
        },
    }
    sess = get_session()
    resp = await sess.post(
        url=WF_URL,
        headers=WF_HEADERS,
        cookies=WF_COOKIES,
        json=payload,
        impersonate="firefox",
        timeout=300,
    )
    if resp.status_code == 403:
        raise SessionExpiredError(f"403 on getJobInfo — session expired, update cookies")
    if resp.status_code == 429:
        raise SessionExpiredError(f"429 on getJobInfo — rate limited")
    resp.raise_for_status()
    try:
        data = JobApplicationModalResponse.model_validate(resp.json())
        if data.data.jobListing is None:
            raise ValueError(f"jobListing is null for job id {jobId} — job may be deleted or unlisted")
        return data.data.jobListing
    except ValidationError as e:
        raise ValueError(f"unexpected response shape for job id {jobId}: {e}") from e



async def applyJob(startupId: str, jobListingId: str, questionAnswers: list[JobQuestionAnswer]) -> int:
    payload = {
        "operationName": "CreateJobApplication",
        "variables": {
            "input": {
                "sourceId": None,
                "jobListingId": jobListingId,
                "product": "job search",
                "questionResponseSets": None,
                "customQuestionAnswers": [
                    {
                        "jobListingQuestionId": qa["jobListingQuestionId"],
                        "answer": qa["answer"],
                        "jobListingQuestionOptionId": qa["jobListingQuestionOptionId"],
                    }
                    for qa in questionAnswers
                ],
                "startupId": startupId,
                "userNote": "",
            }
        },
        "extensions": {
            "operationId": "tfe/b8b8f259334b9998f1034458d18eeda958decc17a57da9280a9fd121aa522015"
        },
    }
    headers = WF_HEADERS.copy()
    headers["x-apollo-operation-name"] = "CreateJobApplication"

    sess = get_session()
    resp = await sess.post(
        url=WF_URL,
        headers=headers,
        cookies=WF_COOKIES,
        json=payload,
        impersonate="firefox",
        timeout=300,
    )
    return resp.status_code



def extract_pdf_text(filepath: str) -> str:
    path = Path(filepath).expanduser().resolve()
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True, x_tolerance=2, y_tolerance=3)
            if text:
                pages.append(text)
    raw = "\n".join(pages).strip()

    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb00": "ff",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\u00a0": " ",
        "shubhamtw--/": "shubhamtw----/",
    }
    for bad, good in replacements.items():
        raw = raw.replace(bad, good)
    return raw


def ollama_cloud_chat(user_prompt: str, system_prompt: str, api_key: str, model: str = "gpt-oss:120b-cloud") -> str:
    try:
        r = requests.post(
            "https://ollama.com/api/chat",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            timeout=300,
        )
        if r.status_code == 429:
            raise LLMError(f"quota limit exceeded (429): {r.text}")
        if r.status_code == 401:
            raise LLMError(f"invalid or expired API key (401): {r.text}")
        if r.status_code == 503:
            raise LLMError(f"LLM service unavailable (503): {r.text}")
        if not (200 <= r.status_code < 300):
            raise LLMError(f"unexpected LLM error ({r.status_code}): {r.text}")

        return r.json()["message"]["content"]

    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"LLM request failed: {e}") from e


def getJobResponses(questions: list[JobApplicationQuestion], resumeContents: str, jobDesc: str) -> list[dict]:
    questions_text_parts = []
    for i, q in enumerate(questions, start=1):
        line = f"{i}. [{q.format}] {q.value}"
        if q.options:
            opts = ", ".join(f'"{o.value}" ({o.label})' for o in q.options)
            line += f"\n   Allowed option values: {opts}"
        questions_text_parts.append(line)

    questions_text = "\n".join(questions_text_parts)
    user_prompt: str = f"""
Questions:
{questions_text}

Job Description:
{jobDesc}

Resume:
{resumeContents}
""".strip()

    response = ollama_cloud_chat(
        user_prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        api_key=OLLAMA_API_KEY,
    )

    match = re.search(r"\[.*\]", response, re.DOTALL)
    if not match:
        log.error(f"LLM returned no JSON array:\n{response}")
        raise LLMError("LLM returned no JSON array")

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError as e:
        log.error(f"LLM returned invalid JSON: {e}\nraw response:\n{response}")
        raise LLMError(f"LLM returned invalid JSON: {e}") from e

    if not isinstance(parsed, list):
        log.error(f"LLM returned non-list:\n{response}")
        raise LLMError("LLM returned non-list")

    if len(parsed) != len(questions):
        log.warning(f"LLM returned {len(parsed)} answers, expected {len(questions)} — truncating to shorter")
        count = min(len(parsed), len(questions))
        parsed = parsed[:count]
        questions = questions[:count]

    results = []
    for item in parsed:
        if isinstance(item, str):
            results.append({"answer": item})
        elif isinstance(item, dict) and "answer" in item:
            results.append({"answer": str(item["answer"])})
        else:
            log.error(f"unexpected answer shape: {item}")
            raise LLMError(f"unexpected answer shape: {item}")

    return results



def jobQuestionsAnswered(
    question_sets: list[JobApplicationQuestionSet],
    legacy_questions: list[JobListingQuestion],
    jobDesc: str,
) -> list[JobQuestionAnswer]:
    supported: list[JobApplicationQuestion] = []

    # legacy questions field — normalize to JobApplicationQuestion
    for q in legacy_questions:
        supported.append(q.to_application_question())

    # applicationQuestionSets
    for qs in question_sets:
        for q in qs.questions:
            if q.format in SUPPORTED_FORMATS:
                supported.append(q)
            else:
                log.warning(f"[SKIP] unsupported format '{q.format}' for question id={q.id} ('{q.value}')")

    if not supported:
        return []

    raw_answers = getJobResponses(
        questions=supported,
        resumeContents=resumeContents,
        jobDesc=jobDesc,
    )

    results: list[JobQuestionAnswer] = []
    for q, raw in zip(supported, raw_answers):
        answer_str: str = raw["answer"]
        option_id: Optional[str] = None

        if q.options:
            valid_values = {o.value for o in q.options}
            if answer_str not in valid_values:
                log.warning(f"[WARN] LLM invalid option '{answer_str}' for '{q.value}'. Valid: {valid_values}. Skipping.")
                continue
            option_id = answer_str

        results.append(
            JobQuestionAnswer(
                jobListingQuestionId=q.id,
                answer=answer_str,
                jobListingQuestionOptionId=option_id,
            )
        )
    return results


#appends emails found in jd to the emails/timestamp.log 
def extractJobEmails(jobs: list[JobListing]) -> None:
    email_pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    matches: list[str] = []
    for job in jobs:
        emails = email_pattern.findall(job.description or "")
        for email in set(emails):
            title_slug = re.sub(r"[^a-z0-9]+", "-", job.title.lower()).strip("-")
            job_url = f"https://wellfound.com/jobs?job_listing_slug={job.id}-{title_slug}"
            line = f"{job.companyName} | {job.title} | {job.id} | {job_url} | {email}"
            matches.append(line)
            log.info(f"[EMAIL FOUND] {line}")
    if not matches:
        log.info("no emails found in job descriptions")
        return
    email_dir = Path(__file__).parent / "emails"
    email_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M")
    email_path = email_dir / f"{timestamp}.log"
    with open(email_path, "a") as f:
        f.write("\n".join(matches) + "\n")
    log.info(f"wrote {len(matches)} email(s) to {email_path}")


async def runBot(role: str, location: str | None = None, maxPages : int = 5):
    #input parsing
    role_id = ROLE_IDS.get(role.lower())
    if role_id is None:
        log.error(f"[ERROR] unknown role '{role}'")
        log.info(f"available roles: {', '.join(ROLE_IDS.keys())}")
        return

    location_id: Optional[str] = None
    if location is not None:
        location_id = LOCATION_IDS.get(location.lower())
        if location_id is None:
            log.error(f"[ERROR] unknown location '{location}'")
            log.info(f"available locations: {', '.join(LOCATION_IDS.keys())} (or pass None for worldwide)")
            return
    
    locationName = location if (location != None) else "Worldwide"
    print(f"Gonna run Bot for role: {role}, with location: {locationName} for: MAX {maxPages} pages")

    jobs = await getJobs(roleId= role_id, locationId= location_id, maxPages=maxPages, roleName=role, locationName=location)
    extractJobEmails(jobs)
    log.info(f"found {len(jobs)} jobs for role='{role}', location='{location or 'worldwide'}'...")

    for idx, job in enumerate(jobs, start=1):
        log.info("\n" + "=" * 80)
        log.info(f"[{idx}/{len(jobs)}] {job.title} at {job.companyName} (id - {job.id})")
        log.info("=" * 80)

        if job.currentUserApplied:
            log.info("status: already applied (search result), skipping...")
            continue

        try:
            jobInfo = await getJobInfo(job.id)
        except SessionExpiredError:
            raise
        except Exception as e:
            log.error(f"failed to fetch job info, skipping: {e}")
            continue

        if jobInfo.currentUserApplied:
            log.info("status: already applied (job detail), skipping...")
            continue

        log.info("generating responses...")
        try:
            responses: list[JobQuestionAnswer] = jobQuestionsAnswered(
                question_sets=jobInfo.applicationQuestionSets,
                legacy_questions=jobInfo.questions,
                jobDesc=job.description,
            )
        except LLMError:
            raise
        except Exception as e:
            log.error(f"failed to generate responses, skipping: {e}")
            continue

        all_questions: list[JobApplicationQuestion] = (
            [q.to_application_question() for q in jobInfo.questions]
            + [q for qs in jobInfo.applicationQuestionSets for q in qs.questions]
        )
        if not responses:
            log.info("no application questions answered")
        else:
            for q_idx, response in enumerate(responses, start=1):
                question_obj = next(
                    (q for q in all_questions if q.id == response["jobListingQuestionId"]),
                    None,
                )
                question_text = question_obj.value if question_obj else response["jobListingQuestionId"]
                log.info(f"Q{q_idx}: {question_text}")
                log.info(f"A{q_idx}: {response['answer']}")
                log.info("-" * 80)

        startupId = job.companyId or ""
        jobId = job.id

        log.info("submitting application...")
        try:
            apply_status = await applyJob(
                startupId=startupId,
                jobListingId=jobId,
                questionAnswers=responses,
            )
            if 200 <= apply_status < 300:
                log.info(f"status: applied successfully ({apply_status})")
            else:
                log.error(f"status: application failed ({apply_status})")
        except Exception as e:
            log.error(f"failed to submit application, skipping: {e}")
            continue

        log.info("=" * 80)



async def main():
    parser = argparse.ArgumentParser(description="Wellfound job application bot")
    parser.add_argument("--role", required=True, help=f"role to apply for. options: {', '.join(ROLE_IDS.keys())}")
    parser.add_argument("--location", default=None, help=f"location filter. options: {', '.join(LOCATION_IDS.keys())} (default: worldwide)")
    parser.add_argument("--maxpages", type=int, default=10, help="max pages to fetch (default: 10)")
    parser.add_argument("--emails-mode", action="store_true", help="only extract emails from job descriptions, skip applying")
    args = parser.parse_args()

    try:
        if args.emails_mode:
            role_id = ROLE_IDS.get(args.role.lower())
            if role_id is None:
                log.error(f"unknown role '{args.role}'. available: {', '.join(ROLE_IDS.keys())}")
                raise SystemExit(1)
            location_id: Optional[str] = None
            if args.location is not None:
                location_id = LOCATION_IDS.get(args.location.lower())
                if location_id is None:
                    log.error(f"unknown location '{args.location}'. available: {', '.join(LOCATION_IDS.keys())}")
                    raise SystemExit(1)
            jobs = await getJobs(roleId=role_id, locationId=location_id, maxPages=args.maxpages, roleName=args.role, locationName=args.location)
            log.info(f"found {len(jobs)} jobs, extracting emails only...")
            extractJobEmails(jobs)
        else:
            await runBot(role=args.role, location=args.location, maxPages=args.maxpages)
    except (LLMError, SessionExpiredError) as e:
        log.error(f"fatal error, stopping: {e}")
        raise SystemExit(1)

    except Exception as e:
        log.error(f"unexpected fatal error: {e}", exc_info=True)
        raise SystemExit(1)
    

if __name__ == '__main__':
    load_dotenv()
    log = setup_logging()
    resumePath = os.getenv("RESUME_PATH") or ""
    resumeContents = extract_pdf_text(resumePath)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\nstopped by user with KeyboardInterrupt")
        raise SystemExit(0)
