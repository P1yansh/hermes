import json
import re
from typing import Optional
import httpx
from app.config import settings

class GemmaClient:
    def __init__(
        self,
        base_url: str = settings.LOCAL_LLM_URL,
        model: str = settings.LOCAL_LLM_MODEL,
        api_key: str = settings.LOCAL_LLM_API_KEY,
        timeout: float = 15.0
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    async def _call_chat(self, prompt: str, system: Optional[str] = None) -> Optional[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
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
        except Exception:
            return None
        return None

    async def extract_email_task(self, sender: str, subject: str, body: str) -> dict:
        """
        Uses Gemma 2 to extract actionable deadlines from emails.
        Falls back to rule-based parser if local LLM is unreachable.
        """
        system_prompt = (
            "You are Hermes, an autonomous academic assistant. "
            "Analyze the following student email. Determine if it contains an academic action item or deadline. "
            "Respond ONLY in valid JSON matching this schema: "
            "{\"has_action\": bool, \"is_spam\": bool, \"course\": str, \"title\": str, "
            "\"deadline_text\": str, \"action_required\": str, \"estimated_hours\": float}"
        )
        user_prompt = f"Sender: {sender}\nSubject: {subject}\nBody:\n{body}"

        response = await self._call_chat(user_prompt, system=system_prompt)
        if response:
            try:
                # Extract json substring if wrapped in markdown code blocks
                clean = re.sub(r"^```(?:json)?", "", response.strip(), flags=re.MULTILINE)
                clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE)
                return json.loads(clean.strip())
            except Exception:
                pass

        # Robust heuristic fallback for offline/test environments
        lower_text = f"{subject} {body}".lower()
        is_spam = any(w in lower_text for w in ["sale", "hoodies", "newsletter", "movie night", "lost & found", "discount"])
        has_due = any(w in lower_text for w in ["due", "submission", "deadline", "cutoff", "extension", "assignment", "lab"])
        
        course_match = re.search(r"([A-Z]{2,4}\s?\d{3})", subject)
        course = course_match.group(1) if course_match else "General"

        return {
            "has_action": bool(has_due and not is_spam),
            "is_spam": is_spam,
            "course": course,
            "title": subject,
            "deadline_text": "Tonight 11:59 PM" if "tonight" in lower_text else ("Tomorrow" if "tomorrow" in lower_text else "Next Week"),
            "action_required": "Submit coursework before cutoff" if has_due else "None",
            "estimated_hours": 3.0 if "lab" in lower_text else 1.5
        }

    async def score_opportunity(self, title: str, description: str, tags: list[str], user_skills: list[str]) -> dict:
        """
        Uses Gemma 2 to score relevance of hackathons and internships.
        """
        system_prompt = (
            "You are Hermes Opportunity Scout. "
            "Evaluate relevance (1-10) of this opportunity for a student skilled in: "
            f"{', '.join(user_skills)}. "
            "Respond ONLY in JSON: {\"relevance_score\": int, \"reason\": str, \"highlight\": str}"
        )
        user_prompt = f"Title: {title}\nTags: {tags}\nDescription: {description}"

        response = await self._call_chat(user_prompt, system=system_prompt)
        if response:
            try:
                clean = re.sub(r"^```(?:json)?", "", response.strip(), flags=re.MULTILINE)
                clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE)
                return json.loads(clean.strip())
            except Exception:
                pass

        # Fallback scoring
        matches = [s for s in user_skills if s.lower() in (title + description + " ".join(tags)).lower()]
        score = min(10, 5 + len(matches) * 2)
        return {
            "relevance_score": score,
            "reason": f"Matches your background in {', '.join(matches[:2])}" if matches else "General tech opportunity",
            "highlight": "High prize pool and aligns with open-source systems" if score >= 8 else "Standard opportunity"
        }

    async def generate_briefing_script(self, panic_items: list[dict], imminent_items: list[dict], top_opp: Optional[dict]) -> str:
        """
        Synthesizes a 60-second natural morning speech script for ElevenLabs.
        """
        system_prompt = (
            "You are Hermes, an Olympian academic butler with a calm, reassuring, and mildly witty tone. "
            "Generate a concise 60-second morning spoken briefing for the student. "
            "Highlight what is urgently due today, what is coming up tomorrow, and one exciting opportunity. "
            "Do NOT include markdown, bullet points, or stage directions. Return plain conversational text only."
        )
        user_prompt = (
            f"Panic items due in < 24 hours: {panic_items}\n"
            f"Imminent items due in 1-3 days: {imminent_items}\n"
            f"Top Opportunity: {top_opp}\n"
        )

        response = await self._call_chat(user_prompt, system=system_prompt)
        if response and len(response.strip()) > 30:
            return response.strip()

        # Fallback script
        panic_text = f"You have {len(panic_items)} urgent item requiring your attention today" if panic_items else "No critical deadlines due in the next 24 hours"
        if panic_items:
            first = panic_items[0]
            panic_text += f", notably {first.get('title', 'an assignment')} in {first.get('source', 'your courses')}."
        else:
            panic_text += ", so you can move at your own pace."

        opp_text = f" Also, don't miss {top_opp.get('title', 'an upcoming hackathon')} with registration closing soon." if top_opp else ""
        return (
            f"Good morning. Here is your Hermes intelligence briefing. {panic_text}"
            f"{opp_text} Focus on high-leverage work, and let the rest wait. Have a productive day."
        )

gemma_client = GemmaClient()
