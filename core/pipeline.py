import os
import json
import threading
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from config.api_manager import get_client
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
# ~3.5 min is a sweet spot: big enough that the API overhead is amortized,
# small enough that 3-5 chunks fit in a long call and parallelize well.
_CHUNK_MS = 3 * 60 * 1000 + 30 * 1000  # 3:30
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
    """Transcribe a single audio file and return (text, offset-shifted segments)."""
    client = get_client()
    with open(path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            prompt=WHISPER_VOCAB,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            timeout=120,
        )

    raw_text = result.text if hasattr(result, "text") else str(result)
    for phrase in WHISPER_HALLUCINATIONS:
        raw_text = raw_text.replace(phrase, "")

    segments = getattr(result, "segments", None) or []
    shifted = []
    for seg in segments:
        start = getattr(seg, "start", 0.0) + offset_sec
        text  = getattr(seg, "text", "").strip()
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
                  phone_number: str | None = None, facts: dict | None = None) -> str:
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
        f"use this EXACT value in any phone / number field).\n"
        if phone_number else
        "   - Phone number: leave blank if not provided in the extracted facts.\n"
    )

    facts_block = (
        f"\nEXTRACTED FACTS (use these verbatim — do NOT re-derive from transcript):\n"
        f"{json.dumps(facts, indent=2)}\n"
        if facts is not None else ""
    )

    return f"""You are a call quality analyst for a real estate / business acquisitions outreach team.

You will receive (1) a set of already-extracted facts the prospect literally stated, and
(2) the raw transcript. Use the FACTS to fill the lead template. Use the TRANSCRIPT only
to judge call quality (checklist, score, coaching). Do not invent facts that aren't in the
extracted-facts block.

Return a JSON object matching the required schema.

Key behaviour:

- "checklist": one entry per checklist item below. result ∈ yes / no / partial / n/a.
- "hard_disqualifiers_triggered": list anything from the disqualifier list the prospect triggered.
- "red_flags": list anything from the red-flag list that appeared.
- "score": integer 0–100 based on checklist performance.
- "lead_template": the filled lead template as a plain string.
   - caller_name = "{caller_name}"
   - date = "{call_date}"
{phone_note}   - {mv_note}Any field not present in the extracted facts → leave blank or "N/A".
   - Use the EXTRACTED FACTS verbatim for every field they cover.
   - Any extra prospect-stated detail in other_notes → put in Notes.
   - For real estate clients: include preliminary temperature and flag as "Preliminary — recalculate after MV is confirmed" if MV is unknown.
- "preliminary_temp": one of Hot / Warm / Cold / Nurture / Throwaway (real estate only, else null).
   Use this logic:
{TEMP_LOGIC}
- "coaching_notes": 2–4 short bullet points of specific feedback for this agent on this call.
- "strengths": 1–3 things the agent did well.
- "call_data": {{ ap, has_valid_motive, timeline_months, open_to_listing }} — prefer values from extracted facts.

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
{facts_block}
---
TRANSCRIPT:
{transcript}
"""


def score(transcript: str, client_key: str, caller_name: str, call_date: str,
          phone_number: str | None = None, facts: dict | None = None) -> dict:
    """
    Pass 2 — grade the call and fill the lead template.
    Uses json_object response format (guaranteed valid JSON, no schema compile
    overhead) with a defensive parser fallback.
    """
    client = get_client()
    prompt = _build_prompt(transcript, client_key, caller_name, call_date, phone_number, facts)

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

            on_progress(60, "Analyzing (parallel: speakers + scoring)…")
            t0 = time.perf_counter()

            # Time diarize and score individually — ThreadPoolExecutor hides
            # that info by default. We wrap each call to record its own duration.
            diarize_t: dict[str, float] = {}
            score_t:   dict[str, float] = {}

            def _timed_diarize():
                s = time.perf_counter()
                r = diarize(stamped_transcript, caller_name, client_key)
                diarize_t["s"] = round(time.perf_counter() - s, 2)
                return r

            def _timed_score():
                s = time.perf_counter()
                r = score(plain_transcript, client_key, caller_name, call_date,
                          phone_number, None)
                score_t["s"] = round(time.perf_counter() - s, 2)
                return r

            with ThreadPoolExecutor(max_workers=2) as ex:
                f_labels = ex.submit(_timed_diarize)
                f_result = ex.submit(_timed_score)
                labels = f_labels.result()
                result = f_result.result()

            timings["diarize_s"]  = diarize_t.get("s", 0)
            timings["score_s"]    = score_t.get("s", 0)
            timings["analyze_wall_s"] = round(time.perf_counter() - t0, 2)

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
            on_progress(
                100,
                f"Done in {timings['total_s']}s "
                f"(transcribe {timings['transcribe_s']}s · "
                f"score {timings['score_s']}s · "
                f"diarize {timings['diarize_s']}s)"
            )
            on_complete(result)

        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_work, daemon=True).start()
