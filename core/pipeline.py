import os
import json
import threading
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from config.api_manager import get_client, get_groq_client
from core.audio_prep import prepare_audio
from shared.criteria import CLIENT_CRITERIA, LEAD_TEMPLATES, TEMP_LOGIC, WHISPER_VOCAB, WHISPER_HALLUCINATIONS


# ─── Phone number extraction from filename ───────────────────────────────────

def extract_phone_from_filename(file_path: str) -> str | None:
    """
    Pull the prospect's phone number from the end of the audio filename.
    Looks for the LAST run of 10 or 11 consecutive digits.

    Examples:
      '...-19728013866.wav'           → '+1 (972) 801-3866'
      '20260422_1725_4405727500.mp3'  → '(440) 572-7500'
      '...-connect-69882-a-24362-19728013866.wav' → '+1 (972) 801-3866'
    """
    name = os.path.splitext(os.path.basename(file_path))[0]

    # Find ALL runs of 10 or 11 digits, take the last one
    # Use a boundary regex so we don't match partial chunks of longer numbers
    matches = re.findall(r'(?<!\d)(\d{10,11})(?!\d)', name)
    if not matches:
        return None

    raw = matches[-1]

    # Format: 10 digits = (AAA) BBB-CCCC ; 11 digits starting with 1 = +1 (AAA) BBB-CCCC
    if len(raw) == 11 and raw.startswith("1"):
        return f"+1 ({raw[1:4]}) {raw[4:7]}-{raw[7:]}"
    if len(raw) == 10:
        return f"({raw[0:3]}) {raw[3:6]}-{raw[6:]}"
    # 11 digits not starting with 1 — return as-is with light formatting
    return raw


# ─── Whisper transcription ────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# Chunk size for parallel Whisper transcription.
# With Groq (10x faster than OpenAI), a single 10-minute call finishes in a
# few seconds — so we only chunk when calls exceed this. The pydub
# slice+reencode overhead is ~1s per chunk, so keeping the chunk count low
# on typical calls is a net win.
_CHUNK_MS = 10 * 60 * 1000  # 10 min
_MAX_PARALLEL_CHUNKS = 5
# How far we'll nudge a chunk boundary to find a silent gap (either side).
# Splitting on silence avoids cutting mid-word, which confuses Whisper at seams.
_SILENCE_SEARCH_MS = 10 * 1000
_MIN_SILENCE_MS = 350


def _pick_chunk_boundaries(audio, chunk_ms: int, duration_ms: int) -> list[tuple[int, int]]:
    """
    Return a list of (start_ms, end_ms) chunk ranges that prefer silent gaps
    as split points. Falls back to a hard split if no silence is found nearby.
    """
    from pydub.silence import detect_silence

    # Threshold relative to overall loudness — robust across different recordings
    try:
        thresh = audio.dBFS - 16
    except Exception:
        thresh = -40

    boundaries: list[int] = [0]
    cursor = 0
    while cursor + chunk_ms < duration_ms:
        target = cursor + chunk_ms
        search_start = max(target - _SILENCE_SEARCH_MS, cursor + chunk_ms // 2)
        search_end   = min(target + _SILENCE_SEARCH_MS, duration_ms)
        region = audio[search_start:search_end]

        split_point = target  # fallback
        try:
            silences = detect_silence(
                region,
                min_silence_len=_MIN_SILENCE_MS,
                silence_thresh=thresh,
            )
            if silences:
                # Pick silence whose midpoint is closest to the target split
                def _mid_offset(s):
                    mid = search_start + (s[0] + s[1]) // 2
                    return abs(mid - target)
                best = min(silences, key=_mid_offset)
                split_point = search_start + (best[0] + best[1]) // 2
        except Exception:
            pass  # pydub/ffmpeg hiccup — just use the hard boundary

        boundaries.append(split_point)
        cursor = split_point

    boundaries.append(duration_ms)
    return list(zip(boundaries[:-1], boundaries[1:]))


def _transcribe_file(path: str, offset_sec: float):
    """
    Transcribe a single audio file via Groq's whisper-large-v3.
    Groq's LPU hardware runs Whisper ~10x faster than OpenAI, and large-v3 is
    a newer/more accurate model than OpenAI's whisper-1.
    Returns (text, offset-shifted segments).
    """
    client = get_groq_client()
    with open(path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            prompt=WHISPER_VOCAB,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            temperature=0.0,
            timeout=120,
        )

    raw_text = result.text if hasattr(result, "text") else str(result)
    for phrase in WHISPER_HALLUCINATIONS:
        raw_text = raw_text.replace(phrase, "")

    segments = getattr(result, "segments", None) or []
    shifted = []
    for seg in segments:
        # Groq returns segments as dicts; OpenAI as objects. Handle both.
        if isinstance(seg, dict):
            start = seg.get("start", 0.0)
            text = seg.get("text", "")
        else:
            start = getattr(seg, "start", 0.0)
            text = getattr(seg, "text", "")
        start = (start or 0.0) + offset_sec
        text = (text or "").strip()
        if text:
            shifted.append((start, text))
    return raw_text.strip(), shifted


def transcribe(file_path: str) -> tuple[str, str]:
    """
    Returns (plain_transcript, stamped_transcript).
    For calls longer than one chunk, splits audio into parallel chunks and
    transcribes them concurrently — network-bound work, so threading is a huge win.
    """
    from pydub import AudioSegment
    import tempfile

    # Preprocess once (16kHz mono) — tiny file, fast re-encoding of sub-slices
    prepped_path = prepare_audio(file_path)
    try:
        audio = AudioSegment.from_file(prepped_path)
        duration_ms = len(audio)

        # Single-chunk fast path (short call) — no threading overhead
        if duration_ms <= _CHUNK_MS:
            raw_text, shifted_segments = _transcribe_file(prepped_path, 0.0)
        else:
            # Slice into silence-aligned chunks and transcribe in parallel
            ranges = _pick_chunk_boundaries(audio, _CHUNK_MS, duration_ms)
            chunk_paths: list[tuple[str, float]] = []
            for start_ms, end_ms in ranges:
                slice_ = audio[start_ms:end_ms]
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.close()
                slice_.export(tmp.name, format="mp3", bitrate="64k")
                chunk_paths.append((tmp.name, start_ms / 1000.0))

            try:
                workers = min(_MAX_PARALLEL_CHUNKS, len(chunk_paths))
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = [
                        ex.submit(_transcribe_file, p, off) for p, off in chunk_paths
                    ]
                    chunk_results = [f.result() for f in futures]
            finally:
                for p, _ in chunk_paths:
                    if os.path.exists(p):
                        try:
                            os.unlink(p)
                        except Exception:
                            pass

            # Stitch in chronological order (ThreadPoolExecutor preserves submit order)
            raw_text = " ".join(r[0] for r in chunk_results).strip()
            shifted_segments = []
            for _, segs in chunk_results:
                shifted_segments.extend(segs)
            shifted_segments.sort(key=lambda s: s[0])

        plain = reconstruct_spelled_out(raw_text)

        if shifted_segments:
            lines = []
            for start, text in shifted_segments:
                for phrase in WHISPER_HALLUCINATIONS:
                    text = text.replace(phrase, "")
                text = reconstruct_spelled_out(text.strip())
                if text:
                    lines.append(f"[{_fmt_time(start)}] {text}")
            # Collapse Whisper hallucination loops: if the SAME line appears 3+
            # times in a row (e.g. "All right." x 20), keep just the first.
            lines = _dedupe_consecutive_lines(lines)
            stamped = "\n".join(lines)
        else:
            stamped = _add_rough_timestamps(plain)

        return plain, stamped
    finally:
        if os.path.exists(prepped_path):
            try:
                os.unlink(prepped_path)
            except Exception:
                pass


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


def _dedupe_consecutive_lines(lines: list[str]) -> list[str]:
    """
    Collapse Whisper's hallucination loops where the same phrase repeats on many
    consecutive segments (e.g. during silence). Keeps the FIRST occurrence and
    drops any immediate duplicates; once a different line appears, the loop resets.

    Normalization: strip timestamp prefix, lowercase, strip punctuation+whitespace.
    A "duplicate" means identical normalized text AND very short (≤ 6 words) — so
    we don't accidentally drop two genuine long sentences that happen to match.
    """
    def _norm(line: str) -> str:
        # Strip the leading "[MM:SS]" before comparing
        m = re.match(r'\[\d{2}:\d{2}\]\s*(.*)', line)
        body = m.group(1) if m else line
        body = re.sub(r'[^\w\s]', '', body).strip().lower()
        return body

    out: list[str] = []
    last_norm: str | None = None
    for line in lines:
        n = _norm(line)
        if not n:
            continue
        # Only dedupe short repeated phrases (typical hallucination loops)
        is_short = len(n.split()) <= 6
        if is_short and n == last_norm:
            continue
        out.append(line)
        last_norm = n
    return out


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


# ─── Pass 1: Fact extraction ──────────────────────────────────────────────────
#
# This runs BEFORE scoring. It pulls only facts the prospect literally said —
# no inference, no fabrication. The second pass then fills the template from
# these extracted facts instead of re-reading the transcript, which massively
# cuts hallucination (e.g. inventing an asking price that was never mentioned).

_FACTS_SCHEMA = {
    "name": "call_facts",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prospect_name":     {"type": ["string", "null"]},
            "prospect_email":    {"type": ["string", "null"]},
            "prospect_phone":    {"type": ["string", "null"]},
            "property_address":  {"type": ["string", "null"]},
            "property_type":     {"type": ["string", "null"]},
            "business_type":     {"type": ["string", "null"]},
            "asking_price":      {"type": ["number", "null"]},
            "motivation":        {"type": ["string", "null"]},
            "timeline_months":   {"type": ["number", "null"]},
            "open_to_listing":   {"type": ["boolean", "null"]},
            "other_notes":       {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "prospect_name", "prospect_email", "prospect_phone",
            "property_address", "property_type", "business_type",
            "asking_price", "motivation", "timeline_months",
            "open_to_listing", "other_notes",
        ],
    },
}


def extract_facts(transcript: str, client_key: str) -> dict:
    """
    Pass 1 — extract only explicitly-stated facts from the transcript.
    Values are null when the prospect did not literally state them.
    """
    client = get_client()

    criteria = CLIENT_CRITERIA[client_key]
    is_re = criteria["type"] == "real_estate"
    domain_hint = (
        "This is a REAL ESTATE outreach call. 'property_address' and 'property_type' "
        "are the target property. 'business_type' should be null."
        if is_re else
        "This is a BUSINESS-ACQUISITIONS outreach call. 'business_type' is the target "
        "business. 'property_address' and 'property_type' are usually null unless the "
        "business includes real estate."
    )

    prompt = f"""Extract ONLY facts the prospect literally stated in this cold-call transcript.
Return a JSON object with EXACTLY these keys (use null when unstated):
  "prospect_name", "prospect_email", "prospect_phone", "property_address",
  "property_type", "business_type", "asking_price" (number), "motivation",
  "timeline_months" (number), "open_to_listing" (boolean),
  "other_notes" (array of strings — any other prospect-stated details).

Rules — read carefully:
- DO NOT infer, guess, or fill in plausible values. If unstated, return null.
- Do not invent asking prices or timelines.
- For emails: reconstruct from phonetic spelling / dot-spelling / "at [company]" conventions.
  * "sierra alpha romeo alpha at gmail dot com" → "sara@gmail.com"
  * "D-U-S-T-I-N at DoubleDOutfitters.com" → "dustin@doubledoutfitters.com"
  * If the prospect corrected themselves ("not plural", "actually..."), use the CORRECTED version.
- If asked a yes/no question and the prospect gave no clear answer, return null (not false).

{domain_hint}

TRANSCRIPT:
{transcript}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=90,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        # Fact extraction is best-effort — scoring still works without it
        return {k: None for k in _FACTS_SCHEMA["schema"]["required"]}


# ─── Pass 2: GPT scoring ──────────────────────────────────────────────────────

_SCORING_SCHEMA = {
    "name": "call_scoring",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "checklist": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "item":   {"type": "string"},
                        "result": {"type": "string", "enum": ["yes", "no", "partial", "n/a"]},
                        "note":   {"type": "string"},
                    },
                    "required": ["item", "result", "note"],
                },
            },
            "hard_disqualifiers_triggered": {"type": "array", "items": {"type": "string"}},
            "red_flags":                    {"type": "array", "items": {"type": "string"}},
            "score":                        {"type": "integer", "minimum": 0, "maximum": 100},
            "lead_template":                {"type": "string"},
            "preliminary_temp":             {"type": ["string", "null"]},
            "coaching_notes":               {"type": "array", "items": {"type": "string"}},
            "strengths":                    {"type": "array", "items": {"type": "string"}},
            "call_data": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ap":                {"type": ["number", "null"]},
                    "has_valid_motive":  {"type": "boolean"},
                    "timeline_months":   {"type": ["number", "null"]},
                    "open_to_listing":   {"type": "boolean"},
                },
                "required": ["ap", "has_valid_motive", "timeline_months", "open_to_listing"],
            },
        },
        "required": [
            "checklist", "hard_disqualifiers_triggered", "red_flags", "score",
            "lead_template", "preliminary_temp", "coaching_notes", "strengths",
            "call_data",
        ],
    },
}


def _build_prompt(transcript: str, client_key: str, caller_name: str, call_date: str,
                  phone_number: str | None = None, facts: dict | None = None,
                  stamped_transcript: str | None = None) -> str:
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

    phone_note = (
        f"   - PROSPECT PHONE NUMBER = \"{phone_number}\" (extracted from the call recording filename — "
        f"use this EXACT value in any phone / number field, do NOT infer from the transcript).\n"
        if phone_number else
        "   - Phone number: leave blank if not explicitly mentioned in transcript.\n"
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
{phone_note}   - {mv_note}Any information the prospect gave that has no matching field → put in Notes.
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

10. "speaker_labels": array of strings, one entry per numbered line in STAMPED TRANSCRIPT below.
    Each entry MUST be exactly "A" (Agent = "{caller_name}", the caller who works for the outreach team)
    or "P" (Prospect, the homeowner/business owner being called).
    - The AGENT usually: introduces themselves ("This is {caller_name} with…"), asks qualifying questions,
      explains they're calling about a property/business, asks for email, proposes next steps.
    - The PROSPECT usually: answers questions, gives personal details (address, price, years owned), may push back.
    - Output EXACTLY one letter per line in the stamped transcript, in the same order.
    - Do NOT merge or skip lines.

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

---
STAMPED TRANSCRIPT (numbered lines — use for "speaker_labels" field):
{_numbered_stamped(stamped_transcript) if stamped_transcript else '(none)'}

Return ONLY valid JSON. No markdown fences, no commentary outside the JSON.
"""


def _numbered_stamped(stamped: str) -> str:
    lines = [l for l in stamped.splitlines() if l.strip()]
    return "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines))


def score(transcript: str, client_key: str, caller_name: str, call_date: str,
          phone_number: str | None = None, facts: dict | None = None,
          stamped_transcript: str | None = None) -> dict:
    """
    Pass 2 — grade the call, fill the lead template, AND return speaker labels
    for the stamped transcript. Combining labeling into the scoring call kills
    the old ~180s diarize call and adds only ~5s of output tokens.
    """
    client = get_client()
    prompt = _build_prompt(transcript, client_key, caller_name, call_date,
                           phone_number, facts, stamped_transcript)

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
        timeout=90,
    )
    raw = (response.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {"error": "Failed to parse GPT response", "raw": raw}


# ─── Dedicated email extraction pass ──────────────────────────────────────────

def _looks_like_spelled_email(transcript: str) -> bool:
    """
    Cheap detector — only run the dedicated email pass if the transcript
    actually contains spelled-out letters or an 'at <domain>' pattern.
    """
    t = transcript.lower()
    # "at gmail", "at yahoo", "at outlook", "at hotmail", "dot com"
    if re.search(r'\b(?:at\s+(?:gmail|yahoo|outlook|hotmail|aol|icloud|me|proton)|dot\s+(?:com|net|org|co|io))\b', t):
        return True
    # Hyphenated single-letter sequence ("D-U-S-T-I-N")
    if re.search(r'\b[a-z](?:-[a-z]){2,}\b', t):
        return True
    # 3+ phonetic words in a row
    phonetic = r'(?:alpha|bravo|charlie|delta|echo|foxtrot|golf|hotel|india|juliet|kilo|lima|mike|november|oscar|papa|quebec|romeo|sierra|tango|uniform|victor|whiskey|x-ray|yankee|zulu)'
    if re.search(rf'\b{phonetic}\s+{phonetic}\s+{phonetic}\b', t):
        return True
    # Already-present email shape (from Whisper's own detection)
    if re.search(r'\b[\w.+\-]+@[\w.\-]+\.[a-z]{2,}\b', t):
        return True
    return False


def extract_email(transcript: str) -> str | None:
    """
    Focused GPT pass dedicated to resolving the prospect's email address.
    Runs in parallel with scoring, only when the transcript shows signs of
    spelled letters / phonetic dictation / 'at <domain>' patterns.
    Returns a single email string, or None if no email was given.
    """
    client = get_client()

    prompt = f"""You resolve a SINGLE email address from a phone call transcript.

Rules — follow exactly:
1. If the prospect was asked for an email but did NOT give one, return null.
2. If letters were spelled phonetically ("sierra alpha romeo alpha" or "S as in Sam, A as in apple"), JOIN the letters into one word.
3. If letters were spelled hyphen-style ("D-U-S-T-I-N"), join into one word.
4. "at <Company>" or "at <Company> dot com" = "@company.com".
5. "dot" between name parts = literal dot (e.g. "john dot smith" = "john.smith").
6. If the prospect CORRECTED themselves ("not plural", "without the s", "actually it's...", "I mean..."), use the CORRECTED version, never the original.
7. The prospect's spelling overrides the agent's readback — if the agent reads it back and the prospect says "yes" or confirms, that's the final version.
8. Always lowercase the final email.
9. If multiple emails appear, return the PROSPECT's (not the agent's / company's).

Return JSON with exactly this shape:
  {{ "email": "<resolved email, lowercased>" or null, "confidence": "high" | "medium" | "low" }}

TRANSCRIPT:
{transcript}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=45,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        email = data.get("email")
        if email and isinstance(email, str):
            email = email.strip().lower()
            # Sanity check — must look like an email
            if re.fullmatch(r'[\w.+\-]+@[\w.\-]+\.[a-z]{2,}', email):
                return email
        return None
    except Exception:
        return None


def _inject_email(template_text: str, email: str) -> str:
    """
    Overwrite any Email / Email Address / E-mail field in the lead template
    with the resolved email from the dedicated extraction pass.
    """
    patterns = [
        r'^(\s*Email Address\s*:)\s*.*$',
        r'^(\s*E-?mail\s*:)\s*.*$',
    ]
    for pat in patterns:
        template_text = re.sub(
            pat,
            lambda m: f"{m.group(1)} {email}",
            template_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    return template_text


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
            timeout=60,
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


def _apply_facts(template_text: str, facts: dict) -> str:
    """
    Override specific lead-template fields with values from the fact-extraction
    pass. Facts are more reliable than the scoring pass's template fill because
    they come from a strict-schema, temperature-0, literal-only extraction.

    Only overrides fields where:
      1. The fact has a non-null value, AND
      2. The template line for that field exists, AND
      3. The current template value differs from the fact (avoids unnecessary edits).
    """
    if not facts:
        return template_text

    # Map fact keys → likely template label variants (case-insensitive)
    field_map = {
        "prospect_name":    ["Name", "Prospect Name", "Owner Name", "Contact Name", "Full Name"],
        "prospect_email":   ["Email", "Email Address", "E-mail"],
        "property_address": ["Address", "Property Address", "Location"],
        "asking_price":     ["Asking Price", "AP", "Price"],
        "motivation":       ["Motivation", "Motive", "Reason for Selling"],
    }

    def _fmt_value(key: str, val) -> str:
        if key == "asking_price" and isinstance(val, (int, float)):
            return f"${int(val):,}"
        return str(val).strip()

    for fact_key, labels in field_map.items():
        val = facts.get(fact_key)
        if val in (None, "", []):
            continue
        formatted = _fmt_value(fact_key, val)
        for label in labels:
            # Match "<Label>: <anything-or-empty>" up to end of line
            pattern = rf'^(\s*{re.escape(label)}\s*:)\s*(.*)$'
            def _sub(m, new=formatted):
                current = m.group(2).strip()
                # Skip if the template already has the correct value
                if current and current.lower() == new.lower():
                    return m.group(0)
                return f"{m.group(1)} {new}"
            new_text, n = re.subn(pattern, _sub, template_text,
                                   flags=re.IGNORECASE | re.MULTILINE)
            if n:
                template_text = new_text
                break  # Only hit the first matching label variant

    return template_text


def _inject_phone(template_text: str, phone: str) -> str:
    """
    Safety net that forces the phone number into the filled lead template.
    Handles every variant used across all 6 templates (Phone:, Phone Number:, Number:).
    Only fills fields that are blank or contain an obvious placeholder.
    """
    # Pattern matches any line with a phone-like label followed by empty / placeholder text
    patterns = [
        r'^(\s*Phone Number\s*:)\s*(?:\{phone\}|\[.*?\]|N/?A|none|unknown|)\s*$',
        r'^(\s*Phone\s*:)\s*(?:\{phone\}|\[.*?\]|N/?A|none|unknown|)\s*$',
        r'^(\s*Number\s*:)\s*(?:\{phone\}|\[.*?\]|N/?A|none|unknown|)\s*$',
    ]
    for pat in patterns:
        template_text = re.sub(
            pat,
            lambda m: f"{m.group(1)} {phone}",
            template_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    # Also replace any remaining literal {phone} placeholders
    template_text = template_text.replace("{phone}", phone)
    return template_text


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
            # ── TIMING INSTRUMENTATION ─────────────────────────────────────
            timings: dict[str, float] = {}
            t_total = time.perf_counter()

            on_progress(10, "Preparing audio…")
            t0 = time.perf_counter()
            phone_number = extract_phone_from_filename(file_path)
            timings["phone_extract_s"] = round(time.perf_counter() - t0, 2)

            on_progress(25, "Transcribing (Whisper)…")
            t0 = time.perf_counter()
            plain_transcript, stamped_transcript = transcribe(file_path)
            timings["transcribe_s"] = round(time.perf_counter() - t0, 2)

            on_progress(60, "Analyzing call (scoring + speakers + email)…")
            t0 = time.perf_counter()

            # Scoring (with combined speaker labels). If the transcript looks
            # like an email was dictated, run a dedicated email-extraction
            # pass in parallel — free wall time since score takes longer.
            needs_email = _looks_like_spelled_email(plain_transcript)
            score_t: dict[str, float] = {}
            email_t: dict[str, float] = {}

            def _timed_score():
                s = time.perf_counter()
                r = score(plain_transcript, client_key, caller_name, call_date,
                          phone_number, None, stamped_transcript)
                score_t["s"] = round(time.perf_counter() - s, 2)
                return r

            def _timed_email():
                s = time.perf_counter()
                r = extract_email(plain_transcript)
                email_t["s"] = round(time.perf_counter() - s, 2)
                return r

            verified_email = None
            if needs_email:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    f_result = ex.submit(_timed_score)
                    f_email = ex.submit(_timed_email)
                    result = f_result.result()
                    verified_email = f_email.result()
            else:
                result = _timed_score()

            timings["score_s"] = score_t.get("s", 0)
            timings["email_s"] = email_t.get("s", 0) if needs_email else 0
            timings["analyze_wall_s"] = round(time.perf_counter() - t0, 2)

            # Override the scoring pass's email with the verified one
            if verified_email and result.get("lead_template"):
                result["lead_template"] = _inject_email(
                    result["lead_template"], verified_email
                )
                result["verified_email"] = verified_email

            # Extract speaker labels from the combined response; fall back to
            # alternation if GPT didn't include them or returned the wrong count.
            stamped_line_count = len([
                l for l in stamped_transcript.splitlines() if l.strip()
            ])
            raw_labels = result.get("speaker_labels") or []
            labels = [
                ("A" if str(x).strip().upper().startswith("A") else "P")
                for x in raw_labels
            ]
            while len(labels) < stamped_line_count:
                labels.append("A" if len(labels) % 2 == 0 else "P")
            labels = labels[:stamped_line_count]

            labeled_transcript = build_labeled_transcript(stamped_transcript, labels)

            on_progress(95, "Finalising…")

            # Safety-net: force the phone into the filled template even if GPT missed it
            if phone_number and result.get("lead_template"):
                result["lead_template"] = _inject_phone(result["lead_template"], phone_number)

            timings["total_s"] = round(time.perf_counter() - t_total, 2)

            # Write a per-run timing entry that the user can share with me.
            try:
                log_dir = os.path.join(
                    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                    "MyVA", "logs",
                )
                os.makedirs(log_dir, exist_ok=True)
                log_path = os.path.join(log_dir, "timing.log")
                entry = {
                    "when": datetime.now().isoformat(timespec="seconds"),
                    "file": os.path.basename(file_path),
                    "client": client_key,
                    **timings,
                }
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass  # logging must never break analysis

            result["transcript"] = plain_transcript
            result["stamped_transcript"] = stamped_transcript
            result["labeled_transcript"] = labeled_transcript
            result["phone_number"] = phone_number
            result["file"] = os.path.basename(file_path)
            result["client"] = client_key
            result["caller_name"] = caller_name
            result["call_date"] = call_date
            result["analyzed_at"] = datetime.now().isoformat()
            result["_timings"] = timings

            # Surface the breakdown right in the "Done" message so it's visible
            email_suffix = (
                f" · email {timings['email_s']}s" if timings.get("email_s") else ""
            )
            on_progress(
                100,
                f"Done in {timings['total_s']}s "
                f"(transcribe {timings['transcribe_s']}s · "
                f"score {timings['score_s']}s{email_suffix})"
            )
            on_complete(result)

        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_work, daemon=True).start()
