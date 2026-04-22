import os
import json
import threading
import re
from datetime import datetime
from typing import Callable

from config.api_manager import get_client
from core.audio_prep import prepare_audio
from shared.criteria import CLIENT_CRITERIA, LEAD_TEMPLATES, TEMP_LOGIC, WHISPER_VOCAB, WHISPER_HALLUCINATIONS


# ─── Whisper transcription ────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def transcribe(file_path: str) -> tuple[str, str]:
    """
    Returns (plain_transcript, stamped_transcript).
    Uses verbose_json for real segment timestamps — much more accurate than estimation.
    """
    client = get_client()
    wav_path = prepare_audio(file_path)
    try:
        with open(wav_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                prompt=WHISPER_VOCAB,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # Clean up known hallucinations
        raw_text = result.text if hasattr(result, "text") else str(result)
        for phrase in WHISPER_HALLUCINATIONS:
            raw_text = raw_text.replace(phrase, "")

        # Build plain transcript with phonetic reconstruction
        plain = reconstruct_spelled_out(raw_text.strip())

        # Build stamped version from actual segment timestamps
        segments = getattr(result, "segments", None) or []
        if segments:
            stamped = _build_stamped_from_segments(segments)
        else:
            stamped = _add_rough_timestamps(plain)

        return plain, stamped

    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def _build_stamped_from_segments(segments) -> str:
    """
    Build a timestamped transcript from Whisper verbose_json segments.
    Each segment has real start/end times.
    """
    lines = []
    for seg in segments:
        start = getattr(seg, "start", 0.0)
        text = getattr(seg, "text", "").strip()
        if not text:
            continue
        # Clean hallucinations from each segment too
        for phrase in WHISPER_HALLUCINATIONS:
            text = text.replace(phrase, "")
        text = reconstruct_spelled_out(text.strip())
        if text:
            lines.append(f"[{_fmt_time(start)}] {text}")
    return "\n".join(lines)


def _add_rough_timestamps(text: str) -> str:
    """
    Fallback: split transcript into sentence-like chunks with rough [MM:SS] markers.
    Assumes ~130 words per minute average speaking rate.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    lines = []
    elapsed = 0.0
    words_per_sec = 130 / 60

    for sent in sentences:
        if not sent.strip():
            continue
        mins, secs = divmod(int(elapsed), 60)
        lines.append(f"[{mins:02d}:{secs:02d}] {sent.strip()}")
        elapsed += len(sent.split()) / words_per_sec

    return "\n".join(lines) if lines else text


# ─── Phonetic / spelled-out email correction ──────────────────────────────────

def reconstruct_spelled_out(text: str) -> str:
    """Fix phonetic alphabet and ASR-mangled emails/addresses from transcript."""

    PHONETIC = {
        "alpha": "a", "bravo": "b", "charlie": "c", "delta": "d",
        "echo": "e", "foxtrot": "f", "golf": "g", "hotel": "h",
        "india": "i", "juliet": "j", "kilo": "k", "lima": "l",
        "mike": "m", "november": "n", "oscar": "o", "papa": "p",
        "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t",
        "uniform": "u", "victor": "v", "whiskey": "w", "x-ray": "x",
        "xray": "x", "yankee": "y", "zulu": "z",
    }

    # "N as in Nancy" or "B as in bravo" → single letter
    text = re.sub(
        r'\b([A-Za-z])\s+as\s+in\s+\w+',
        lambda m: m.group(1).lower(),
        text, flags=re.IGNORECASE
    )

    # Hyphen-spelled letters: "D-U-S-T-I-N" → "dustin"
    # Only matches sequences of single chars (not words like "Double-D-Outfitters")
    text = re.sub(
        r'\b([A-Za-z](?:-[A-Za-z]){2,})\b',
        lambda m: m.group(0).replace('-', '').lower(),
        text
    )

    # "dot <word>" spoken aloud → literal dot before the word
    # Handles: "john dot smith at gmail dot com" → "john.smith at gmail.com"
    # Must run before the phonetic loop so it doesn't interfere
    text = re.sub(
        r'\bdot\s+([A-Za-z0-9_]+)',
        lambda m: f".{m.group(1).lower()}",
        text, flags=re.IGNORECASE
    )

    # Replace phonetic words ONLY when 3+ consecutive phonetic words appear in a row.
    # (Requiring 3 avoids false positives with common two-word combos in normal speech.)
    # Letters are JOINED into a single token — "sierra alpha romeo alpha" → "sara"
    words = text.split()
    result = []
    i = 0
    while i < len(words):
        lower      = words[i].lower().rstrip(".,")
        next_lower = words[i + 1].lower().rstrip(".,") if i + 1 < len(words) else ""
        next2_lower = words[i + 2].lower().rstrip(".,") if i + 2 < len(words) else ""

        # Trigger only when current + next are both phonetic (2-word minimum)
        if lower in PHONETIC and next_lower in PHONETIC:
            # Consume all consecutive phonetic words and join into one word
            letters = []
            while i < len(words) and words[i].lower().rstrip(".,") in PHONETIC:
                letters.append(PHONETIC[words[i].lower().rstrip(".,")])
                i += 1
            result.append("".join(letters))
        else:
            result.append(words[i])
            i += 1
    text = " ".join(result)

    # Collapse runs of single lowercase letters separated by spaces into one word
    # (catches any leftover spacing: "s a r a" → "sara")
    text = re.sub(
        r'\b([a-z](?: [a-z]){2,})\b',
        lambda m: m.group(0).replace(" ", ""),
        text
    )

    # Join adjacent hyphen-spelled/phonetic tokens separated by a literal dot segment:
    # "dustin .brooks" → "dustin.brooks"   (Whisper may emit ".Brooks" as separate token)
    text = re.sub(
        r'\b([A-Za-z0-9_]+)\s+(\.[A-Za-z0-9_]+)',
        lambda m: m.group(1).lower() + m.group(2).lower(),
        text
    )

    # "localpart at domain dot tld" → "localpart@domain.tld"
    text = re.sub(
        r'\b([A-Za-z0-9._+\-]+)\s+(?:at|@)\s+([A-Za-z0-9._+\-]+)\s+\.([A-Za-z]{2,})\b',
        lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower(),
        text, flags=re.IGNORECASE
    )
    # same but "dot tld" already replaced by ".tld" above — catch "at domain.tld"
    text = re.sub(
        r'\b([A-Za-z0-9._+\-]+)\s+(?:at|@)\s+([A-Za-z0-9._+\-]+\.(?:[A-Za-z]{2,}))\b',
        lambda m: f"{m.group(1)}@{m.group(2)}".lower(),
        text, flags=re.IGNORECASE
    )

    # "word at domain.tld" (domain already contains a dot — company website style)
    text = re.sub(
        r'\b([A-Za-z0-9._+\-]+)\s+at\s+([A-Za-z0-9][A-Za-z0-9\-]*\.[A-Za-z]{2,})\b',
        lambda m: f"{m.group(1)}@{m.group(2)}".lower(),
        text, flags=re.IGNORECASE
    )

    # Remove stray spaces inside reconstructed email addresses
    text = re.sub(r'(\w)\s+@\s+(\w)', r'\1@\2', text)

    return text


# ─── Email post-validation ─────────────────────────────────────────────────────

def _extract_emails_from_text(text: str) -> list[str]:
    """Pull all email addresses from any text block."""
    return re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text)


# ─── GPT scoring ──────────────────────────────────────────────────────────────

def _build_prompt(transcript: str, client_key: str, caller_name: str, call_date: str) -> str:
    criteria = CLIENT_CRITERIA[client_key]
    template_key = criteria["template_type"]
    template = LEAD_TEMPLATES[template_key]

    checklist_text = "\n".join(f"- {item}" for item in criteria["checklist"])
    disqualifiers_text = "\n".join(f"- {d}" for d in criteria["hard_disqualifiers"])
    red_flags_text = "\n".join(f"- {r}" for r in criteria["red_flags"])

    is_re = criteria["type"] == "real_estate"
    mv_note = (
        "Market Value / MV / Zestimate field must NEVER be filled — leave it blank regardless of what it is called in the template. "
        "The user will look it up on Zillow, Realtor.com, and Redfin manually.\n"
        if is_re else ""
    )

    return f"""You are a call quality analyst for a real estate / business acquisitions outreach team.

Analyze the following call transcript and return a JSON object with these keys:

1. "checklist": array of objects — one per checklist item:
   {{ "item": "<item text>", "result": "yes" | "no" | "partial" | "n/a", "note": "<short explanation>" }}

2. "hard_disqualifiers_triggered": array of strings (empty if none triggered)

3. "red_flags": array of strings (empty if none found)

4. "score": integer 0–100 based on checklist performance

5. "lead_template": the filled lead template as a plain string. Rules:
   - caller_name = "{caller_name}"
   - date = "{call_date}"
   - {mv_note}Any information the prospect gave that has no matching field → put in Notes.
   - For real estate clients: include preliminary temperature and flag as "Preliminary — recalculate after MV is confirmed" if MV is unknown.

   EMAIL EXTRACTION — read very carefully and follow every rule:
   - Hyphened single letters spell a word: "D-U-S-T-I-N" = "dustin", "B-R-O-O-K-S" = "brooks"
   - A dot spoken before a name segment = literal dot: ".Brooks" = ".brooks"
   - "at [Company].com" or "at [Company] dot com" = "@company.com"
   - "dot" between two word parts = literal dot: "john dot smith" = "john.smith"
   - Reconstruct the full email from ALL spoken parts in sequence.
   - Example: "dustin, D-U-S-T-I-N, .Brooks, B-R-O-O-K-S, at DoubleDOutfitters.com"
     → dustin.brooks@doubledoutfitters.com
   - Example: "john at gmail dot com" → john@gmail.com
   - Example: "sierra alpha romeo alpha at yahoo dot com" → sara@yahoo.com
   - If letters are repeated/confirmed (prospect says name then spells it), use the spelled version, NOT the spoken name before spelling.
   - Always lowercase the final email.

   EMAIL CORRECTIONS — CRITICAL:
   - If someone gives an email and then IMMEDIATELY corrects it (says "not plural", "without the s", "just service not services", "correction:", "actually it's", "I mean", "sorry it's"), ALWAYS use the CORRECTED version. The correction overrides EVERYTHING said before.
   - Example: agent hears "proroofingservices1 at gmail dot com" then says "not plural on services, just service" → final email MUST be proroofingservice1@gmail.com
   - Example: "john@gmail.com — actually make that johnny@gmail.com" → johnny@gmail.com
   - Read the ENTIRE conversation after the email is first given to check for any correction.
   - When in doubt, use the LAST version the prospect confirmed.

6. "preliminary_temp": one of Hot / Warm / Cold / Nurture / Throwaway (real estate only, else null)
   Use this logic:
{TEMP_LOGIC}

7. "coaching_notes": 2–4 short bullet points of specific feedback for this agent on this call

8. "strengths": 1–3 things the agent did well

9. "call_data": a small object used for temperature recalculation when MV is added later:
   {{ "ap": <asking price as a number, or null>, "has_valid_motive": <true|false>, "timeline_months": <estimated months, or null>, "open_to_listing": <true|false> }}

---
CLIENT: {client_key}
FRAMEWORK: {criteria['framework']}

CHECKLIST:
{checklist_text}

HARD DISQUALIFIERS:
{disqualifiers_text}

RED FLAGS TO WATCH FOR:
{red_flags_text}

TEMPLATE TO FILL:
{template}

---
TRANSCRIPT:
{transcript}

Return ONLY valid JSON. No markdown fences, no commentary outside the JSON.
"""


def score(transcript: str, client_key: str, caller_name: str, call_date: str) -> dict:
    client = get_client()
    prompt = _build_prompt(transcript, client_key, caller_name, call_date)

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the largest {...} block
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {"error": "Failed to parse GPT response", "raw": raw}


# ─── Speaker diarization (agent vs prospect) ──────────────────────────────────

def diarize(stamped_transcript: str, caller_name: str, client_key: str) -> list[str]:
    """
    Ask GPT to label each transcript line as 'A' (Agent) or 'P' (Prospect).
    Returns one label per non-empty input line. Much cheaper than re-emitting
    the full transcript — GPT only outputs a single letter per line.
    """
    lines = [l for l in stamped_transcript.splitlines() if l.strip()]
    if not lines:
        return []

    # Give each line a numeric index so GPT can't drop or rearrange them
    numbered = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))

    prompt = f"""You are a speaker-diarization assistant. Below is a transcript of a cold outreach call.
The AGENT is "{caller_name}" — they placed the call on behalf of a real-estate / business acquisitions team.
The PROSPECT is the homeowner / business owner being called.

For EACH numbered line, output exactly one letter on its own line:
  A = Agent (the caller, "{caller_name}", works for the outreach team)
  P = Prospect (the person being called)

Rules:
- Agent usually introduces themselves, asks qualifying questions, explains they're calling about a property or business.
- Prospect usually answers questions, provides personal info, asks questions back about the offer.
- Output EXACTLY {len(lines)} letters, one per line, nothing else.
- No commentary, no line numbers, no punctuation — just A or P per line.

TRANSCRIPT:
{numbered}
"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        labels = [c.strip().upper()[0] for c in raw.splitlines() if c.strip()]
        # Pad / truncate to exactly match input line count
        while len(labels) < len(lines):
            labels.append(labels[-1] if labels else "A")
        return labels[:len(lines)]
    except Exception:
        # Fallback: simple alternation
        return ["A" if i % 2 == 0 else "P" for i in range(len(lines))]


def build_labeled_transcript(stamped_transcript: str, labels: list[str]) -> str:
    """Merge stamped transcript with A/P labels into a readable, speaker-tagged transcript."""
    lines = [l for l in stamped_transcript.splitlines() if l.strip()]
    merged = []
    for i, line in enumerate(lines):
        m = re.match(r'(\[\d{2}:\d{2}\])\s+(.*)', line)
        if not m:
            merged.append(line)
            continue
        stamp, text = m.group(1), m.group(2)
        label = labels[i] if i < len(labels) else "A"
        speaker = "Agent" if label == "A" else "Prospect"
        arrow   = "→" if label == "A" else "◆"
        merged.append(f"{stamp} {arrow} {speaker}: {text}")
    return "\n".join(merged)


# ─── Public pipeline entry point ─────────────────────────────────────────────

def run(
    file_path: str,
    client_key: str,
    caller_name: str,
    call_date: str,
    on_progress: Callable[[int, str], None],
    on_complete: Callable[[dict], None],
    on_error: Callable[[str], None],
) -> None:
    """Runs the full pipeline in a daemon thread."""

    def _work():
        try:
            on_progress(10, "Preparing audio…")

            on_progress(25, "Transcribing (Whisper)…")
            plain_transcript, stamped_transcript = transcribe(file_path)

            on_progress(55, "Identifying speakers…")
            labels = diarize(stamped_transcript, caller_name, client_key)
            labeled_transcript = build_labeled_transcript(stamped_transcript, labels)

            on_progress(70, "Scoring call (GPT-4.1-mini)…")
            result = score(plain_transcript, client_key, caller_name, call_date)

            on_progress(95, "Finalising…")
            result["transcript"] = plain_transcript
            result["stamped_transcript"] = stamped_transcript
            result["labeled_transcript"] = labeled_transcript
            result["file"] = os.path.basename(file_path)
            result["client"] = client_key
            result["caller_name"] = caller_name
            result["call_date"] = call_date
            result["analyzed_at"] = datetime.now().isoformat()

            on_progress(100, "Done")
            on_complete(result)

        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_work, daemon=True).start()
