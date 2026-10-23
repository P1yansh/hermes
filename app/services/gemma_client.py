import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.models.extraction import EmailExtraction

logger = logging.getLogger(__name__)

GRAMMAR_PATH = Path(__file__).resolve().parent.parent / "grammars" / "deadline_extraction.gbnf"

class GemmaClient:
    def __init__(
        self,
        base_url: str = settings.LOCAL_LLM_URL,
        model: str = settings.LOCAL_LLM_MODEL,
        api_key: str = settings.LOCAL_LLM_API_KEY,
        timeout: float = 30.0
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._grammar: Optional[str] = None

    def _deadline_grammar(self) -> Optional[str]:
        if self._grammar is None and GRAMMAR_PATH.exists():
            self._grammar = GRAMMAR_PATH.read_text(encoding="utf-8")
        return self._grammar

    async def _call_chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        json_mode: bool = True,
        grammar: Optional[str] = None,
    ) -> Optional[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        if grammar:
            payload["grammar"] = grammar
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                logger.debug("Gemma returned HTTP %s", res.status_code)
        except Exception as exc:
            logger.debug("Gemma request failed: %s", exc)
        return None

    async def extract_email_task(
        self,
        sender: str,
        subject: str,
        body: str,
        email_received_at_ist: Optional[str] = None
    ) -> dict:
        """
        4-Class Few-Shot Discrimination Engine with Relative Date Anchoring.
        Classifies incoming emails into:
          - ACADEMIC_DEADLINE
          - OPPORTUNITY_DEADLINE
          - INFORMATIONAL_ALERT
          - SPAM_NOISE
        """
        anchor = email_received_at_ist or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        system_prompt = (
            "You are Hermes, an autonomous intelligence classifier for student and developer inboxes.\n"
            f"EMAIL RECEIVED TIMESTAMP CONTEXT: {anchor}\n"
            "CRITICAL TIME RULE: All relative temporal phrases ('tomorrow', 'tonight', 'in 2 days', 'due Friday') "
            f"MUST be calculated relative to {anchor}, NEVER relative to the current wall-clock date.\n\n"
            "Classify the email into exactly one of four categories:\n"
            "1. 'ACADEMIC_DEADLINE': University course homework, lab, problem set, quiz, exam, or project.\n"
            "2. 'OPPORTUNITY_DEADLINE': Hackathon, fellowship, research grant, or internship submission/registration.\n"
            "3. 'INFORMATIONAL_ALERT': Welcome messages, security/passkey alerts, login receipts, verification codes, "
            "purchase confirmations, or newsletters without course deadlines or competitions. (NO DEADLINE).\n"
            "4. 'SPAM_NOISE': Store discounts, merchandise, hoodies, promotional ads.\n\n"
            "Return valid JSON matching this schema:\n"
            "{\n"
            '  "category": "ACADEMIC_DEADLINE" | "OPPORTUNITY_DEADLINE" | "INFORMATIONAL_ALERT" | "SPAM_NOISE",\n'
            '  "has_explicit_deadline": bool,\n'
            '  "confidence": float,\n'
            '  "title": str,\n'
            '  "course_or_organizer": str,\n'
            '  "exact_deadline_iso": str or null,\n'
            '  "deadline_verbatim": str or null,\n'
            '  "needs_web_search": bool,\n'
            '  "search_query": str or null,\n'
            '  "action_required": str,\n'
            '  "estimated_hours": float\n'
            "}\n\n"
            "FEW-SHOT EXAMPLES:\n"
            "--- Example 1 ---\n"
            "Sender: SerpApi <contact@serpapi.com>\n"
            "Subject: Welcome to SerpApi!\n"
            "Body: Welcome to SerpApi! Hi student, To scrape search results with our API...\n"
            "Output: {\n"
            '  "category": "INFORMATIONAL_ALERT",\n'
            '  "has_explicit_deadline": false,\n'
            '  "confidence": 0.99,\n'
            '  "title": "Welcome to SerpApi!",\n'
            '  "course_or_organizer": "SerpApi",\n'
            '  "exact_deadline_iso": null,\n'
            '  "deadline_verbatim": null,\n'
            '  "needs_web_search": false,\n'
            '  "search_query": null,\n'
            '  "action_required": "None",\n'
            '  "estimated_hours": 0.0\n'
            "}\n\n"
            "--- Example 2 ---\n"
            "Sender: Google <no-reply@accounts.google.com>\n"
            "Subject: Security alert\n"
            "Body: New passkey added to your account. If you didn't do this, check your account settings.\n"
            "Output: {\n"
            '  "category": "INFORMATIONAL_ALERT",\n'
            '  "has_explicit_deadline": false,\n'
            '  "confidence": 0.99,\n'
            '  "title": "Security alert",\n'
            '  "course_or_organizer": "Google Accounts",\n'
            '  "exact_deadline_iso": null,\n'
            '  "deadline_verbatim": null,\n'
            '  "needs_web_search": false,\n'
            '  "search_query": null,\n'
            '  "action_required": "None",\n'
            '  "estimated_hours": 0.0\n'
            "}\n\n"
            "--- Example 3 ---\n"
            "Sender: No Reply <no-reply@devpost.com>\n"
            "Subject: Still planning on entering PayPal AI Hackathon?\n"
            "Body: Submissions are open. Build an innovative financial agent using open weights...\n"
            "Output: {\n"
            '  "category": "OPPORTUNITY_DEADLINE",\n'
            '  "has_explicit_deadline": false,\n'
            '  "confidence": 0.95,\n'
            '  "title": "PayPal AI Hackathon",\n'
            '  "course_or_organizer": "PayPal / Devpost",\n'
            '  "exact_deadline_iso": null,\n'
            '  "deadline_verbatim": null,\n'
            '  "needs_web_search": true,\n'
            '  "search_query": "PayPal AI Hackathon 2026 submission deadline",\n'
            '  "action_required": "Submit project on Devpost",\n'
            '  "estimated_hours": 8.0\n'
            "}\n\n"
            "--- Example 4 ---\n"
            "Sender: Prof. Menon <menon@example.edu>\n"
            "Subject: CS401: Distributed Systems - Lab 3 Submission Cutoff Tonight\n"
            "Body: Lab 3 consensus engine is due tonight by 11:59 PM on Classroom.\n"
            "Context Anchor: 2026-10-22 14:00:00 IST (Thursday)\n"
            "Output: {\n"
            '  "category": "ACADEMIC_DEADLINE",\n'
            '  "has_explicit_deadline": true,\n'
            '  "confidence": 0.98,\n'
            '  "title": "Lab 3: Raft Consensus Engine",\n'
            '  "course_or_organizer": "CS401: Distributed Systems",\n'
            '  "exact_deadline_iso": "2026-10-22T18:29:00Z",\n'
            '  "deadline_verbatim": "tonight by 11:59 PM",\n'
            '  "needs_web_search": false,\n'
            '  "search_query": null,\n'
            '  "action_required": "Submit Raft consensus engine on Classroom",\n'
            '  "estimated_hours": 3.0\n'
            "}"
        )

        user_prompt = f"Sender: {sender}\nSubject: {subject}\nReceived Context: {anchor}\nBody:\n{body[:1500]}"

        response = await self._call_chat(
            user_prompt,
            system=system_prompt,
            json_mode=True,
            grammar=self._deadline_grammar(),
        )
        if response:
            try:
                clean = re.sub(r"^```(?:json)?", "", response.strip(), flags=re.MULTILINE)
                clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE)
                data = EmailExtraction.model_validate(json.loads(clean.strip())).model_dump()
                # Backwards-compatible keys used by the triage agent.
                data["has_action"] = data["category"] in ("ACADEMIC_DEADLINE", "OPPORTUNITY_DEADLINE")
                data["is_spam"] = data["category"] in ("SPAM_NOISE", "INFORMATIONAL_ALERT")
                data["course"] = data["course_or_organizer"]
                data["deadline_text"] = data["deadline_verbatim"] or data["exact_deadline_iso"]
                return data
            except Exception as exc:
                logger.debug("Gemma extraction was not valid JSON/schema: %s", exc)

        # Robust deterministic fallback
        lower_text = f"{subject} {body}".lower()

        # Check informational / security alerts
        if any(w in lower_text for w in ["welcome to", "security alert", "passkey", "verification code", "receipt for", "subscription confirmed"]):
            return {
                "category": "INFORMATIONAL_ALERT",
                "has_action": False,
                "is_spam": True,
                "has_explicit_deadline": False,
                "confidence": 0.95,
                "title": subject,
                "course_or_organizer": sender.split("<")[0].strip(),
                "exact_deadline_iso": None,
                "deadline_verbatim": None,
                "deadline_text": None,
                "needs_web_search": False,
                "search_query": None,
                "action_required": "None",
                "estimated_hours": 0.0
            }

        # Check spam
        if any(w in lower_text for w in ["sale", "hoodies", "newsletter", "movie night", "lost & found", "discount", "merchandise"]):
            return {
                "category": "SPAM_NOISE",
                "has_action": False,
                "is_spam": True,
                "has_explicit_deadline": False,
                "confidence": 0.95,
                "title": subject,
                "course_or_organizer": sender,
                "exact_deadline_iso": None,
                "deadline_verbatim": None,
                "deadline_text": None,
                "needs_web_search": False,
                "search_query": None,
                "action_required": "None",
                "estimated_hours": 0.0
            }

        # Check opportunities
        is_opp = any(w in lower_text for w in ["hackathon", "internship", "fellowship", "code for good", "devpost", "unstop"])
        if is_opp:
            has_due = any(w in lower_text for w in ["due", "deadline", "closing", "cutoff", "submit before"])
            return {
                "category": "OPPORTUNITY_DEADLINE",
                "has_action": True,
                "is_spam": False,
                "has_explicit_deadline": has_due,
                "confidence": 0.90,
                "title": subject,
                "course_or_organizer": sender.split("<")[0].strip() or "Opportunity",
                "exact_deadline_iso": None,
                "deadline_verbatim": "See Event" if has_due else None,
                "deadline_text": "See Event" if has_due else None,
                "needs_web_search": not has_due,
                "search_query": f"{subject} 2026 deadline" if not has_due else None,
                "action_required": "Register/Submit project",
                "estimated_hours": 5.0
            }

        # Academic task check
        has_due = any(w in lower_text for w in ["due", "submission", "deadline", "cutoff", "extension", "assignment", "lab", "homework"])
        course_match = re.search(r"([A-Z]{2,4}\s?\d{3})", subject)
        course = course_match.group(1) if course_match else "General Coursework"

        return {
            "category": "ACADEMIC_DEADLINE" if has_due else "INFORMATIONAL_ALERT",
            "has_action": bool(has_due),
            "is_spam": not bool(has_due),
            "has_explicit_deadline": bool(has_due and any(k in lower_text for k in ["tonight", "tomorrow", "pm", "am", "by "])),
            "confidence": 0.85 if has_due else 0.70,
            "title": subject,
            "course_or_organizer": course,
            "exact_deadline_iso": None,
            "deadline_verbatim": "Tonight 11:59 PM" if "tonight" in lower_text else ("Tomorrow 6:00 PM" if "tomorrow" in lower_text else None),
            "deadline_text": "Tonight 11:59 PM" if "tonight" in lower_text else ("Tomorrow 6:00 PM" if "tomorrow" in lower_text else None),
            "needs_web_search": False,
            "search_query": None,
            "action_required": "Submit coursework before cutoff" if has_due else "None",
            "estimated_hours": 3.0 if "lab" in lower_text else 1.5
        }

    async def extract_deadline_from_search(
        self,
        query: str,
        snippets: list[str],
        anchor_ist: Optional[str] = None
    ) -> Optional[str]:
        """
        Parses search engine snippets to extract an exact future ISO-8601 deadline.
        """
        if not snippets:
            return None

        if anchor_ist:
            anchor = anchor_ist
        else:
            try:
                anchor = datetime.now(ZoneInfo(settings.USER_TIMEZONE)).strftime(
                    "%Y-%m-%d %H:%M:%S %Z"
                )
            except Exception:
                anchor = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        combined_text = "\n".join(f"- {s}" for s in snippets[:4])

        system_prompt = (
            "You are Hermes Deadline Extractor. Given search snippets about an event, extract the exact future submission/registration cutoff date.\n"
            f"REFERENCE ANCHOR: {anchor}\n"
            "Return JSON: {\"found\": bool, \"exact_deadline_iso\": str or null, \"reason\": str}\n"
            "Rules:\n"
            "- If multiple dates exist, choose the final project submission or registration deadline.\n"
            "- If the deadline is in the past relative to reference anchor, return found: false, exact_deadline_iso: null.\n"
            "- If no specific deadline is mentioned, return found: false, exact_deadline_iso: null."
        )
        user_prompt = f"Event: {query}\nSnippets:\n{combined_text}"

        response = await self._call_chat(user_prompt, system=system_prompt, json_mode=True)
        if response:
            try:
                clean = re.sub(r"^```(?:json)?", "", response.strip(), flags=re.MULTILINE)
                clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE)
                data = json.loads(clean.strip())
                if data.get("found") and data.get("exact_deadline_iso"):
                    return data["exact_deadline_iso"]
            except Exception:
                pass

        # Regex heuristic fallback: look for dates like "October 28, 2026" or "Nov 15, 2026"
        month_pattern = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(202[5-9])"
        match = re.search(month_pattern, combined_text, re.IGNORECASE)
        if match:
            month_str, day_str, year_str = match.groups()
            try:
                dt = datetime.strptime(f"{month_str[:3]} {day_str} {year_str}", "%b %d %Y").replace(
                    hour=23, minute=59, tzinfo=timezone.utc
                )
                return dt.isoformat()
            except Exception:
                pass

        return None

    async def score_opportunity(self, title: str, description: str, tags: list[str], user_skills: list[str]) -> dict:
        """
        Uses Gemma to score relevance of hackathons and internships.
        """
        system_prompt = (
            "You are Hermes Opportunity Scout. "
            "Evaluate relevance (1-10) of this opportunity for a student skilled in: "
            f"{', '.join(user_skills)}. "
            "Respond ONLY in JSON: {\"relevance_score\": int, \"reason\": str, \"highlight\": str}"
        )
        user_prompt = f"Title: {title}\nTags: {tags}\nDescription: {description}"

        response = await self._call_chat(user_prompt, system=system_prompt, json_mode=True)
        if response:
            try:
                clean = re.sub(r"^```(?:json)?", "", response.strip(), flags=re.MULTILINE)
                clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE)
                return json.loads(clean.strip())
            except Exception:
                pass

        # Robust skill-matching fallback
        text_corpus = (title + " " + description + " " + " ".join(tags)).lower()
        matched_skills = [s for s in user_skills if s.lower() in text_corpus]
        score = min(10, 4 + len(matched_skills) * 2) if user_skills else 5

        return {
            "relevance_score": score,
            "reason": f"Matches skills: {', '.join(matched_skills)}" if matched_skills else "General technical opportunity",
            "highlight": "High relevance to your background" if score >= 8 else "Standard match"
        }

    async def generate_briefing_script(self, panic_items: list[dict], imminent_items: list[dict], top_opp: Optional[dict]) -> str:
        system_prompt = (
            "You are Hermes, the Maha-Aalsi AI: a student deadline assistant who would rather "
            "nap than panic, but refuses to let a real cutoff slip. Speak in natural Hinglish, "
            "the way a tired senior would warn a junior in a hostel mess. Keep a calm, slightly "
            "lazy, direct tone. Generate a 60-second morning spoken briefing. Name what is due "
            "in the next 6 hours, what is coming in the next 24 hours, and one opportunity worth "
            "getting off the bed for. Use short sentences and at least three Hinglish phrases "
            "such as 'uth ja, alsi', 'jaldi kar', 'baki sab chill hai', or 'kaam abhi kar le'. "
            "Do not write formal corporate English. No markdown, asterisks, bullet points, or "
            "stage directions. Do not use gaali, profanity, or insults. Do not invent the current "
            "clock time or claim it is morning, noon, or night; use only the hours remaining. "
            "Return plain text only.\n\n"
            "Example tone: 'Uth ja, alsi. Aaj ek hi cheez panic mein hai: CS401 Lab 3, "
            "chaar ghante baki. Baaki sab chill hai. GSoC ka form bhi dekh le, but pehle lab.'"
        )
        user_prompt = (
            f"Panic items due in < 6 hours: {panic_items}\n"
            f"Imminent items due in 6-24 hours: {imminent_items}\n"
            f"Top Opportunity: {top_opp}\n"
        )
        response = await self._call_chat(user_prompt, system=system_prompt, json_mode=False)
        if response:
            # Strip stray markdown emphasis from small-model output.
            return response.replace("*", "").strip()

        # Deterministic Hinglish fallback so offline demos still match the persona.
        if panic_items:
            first = panic_items[0]
            return (
                f"Uth ja, alsi. {len(panic_items)} kaam panic band mein hain. "
                f"Sabse pehle {first.get('title', 'ek deadline')} — "
                f"{first.get('hours_left', 0)} ghante baki hain. "
                f"Uske baad {len(imminent_items)} cheezein 24 ghante ke andar hain. "
                "Baaki sab chill hai, lekin pehle wala abhi kar le."
            )
        if imminent_items:
            return (
                f"Abhi koi emergency nahi hai. {len(imminent_items)} deadline 24 ghante ke andar "
                "aa rahi hain. Aaj thoda kaam kar le, kal ki tension bachegi. "
                "Top opportunity bhi dashboard par wait kar rahi hai."
            )
        return (
            "Sab clear hai. Aaj koi panic deadline nahi hai. "
            "Laptop band kar, paani pi, aur agle hafte ke kaam ke liye thoda buffer bana le."
        )

gemma_client = GemmaClient()
