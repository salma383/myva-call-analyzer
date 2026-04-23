"""
MyVA Client Criteria — Call Analyzer Desktop App
"""

CLIENT_CRITERIA = {

    "Dealonomy (M&A)": {
        "type": "business",
        "framework": "RAT (Revenue · Authority · Timeline)",
        "checklist": [
            "Did agent confirm revenue is $1.5M+?",
            "Did agent confirm prospect is the owner / decision-maker?",
            "Did agent confirm prospect is open to exploring a sale?",
            "If prospect mentioned their business is SaaS — did agent disqualify / not proceed?",
            "If prospect mentioned they are California-based — did agent disqualify / not proceed?",
            "If agent reached the owner — did agent book an appointment with Devon?",
            "If agent reached the owner — did agent get email and ask prospect to accept the calendar invite?",
            "Did agent avoid pushing after a firm no — offered 6-month follow-up instead?",
        ],
        "hard_disqualifiers": [
            "Revenue confirmed under $1.5M",
            "Prospect confirmed business is SaaS (only if prospect mentioned it)",
            "Prospect confirmed California-based (only if prospect mentioned it)",
        ],
        "red_flags": [
            "Agent didn't confirm revenue threshold",
            "Agent didn't confirm owner / decision-maker status",
            "Agent pushed hard after firm no without pivoting to 6-month follow-up",
            "Agent booked appointment without speaking to the owner",
        ],
        "coaching_focus": [
            "RAT framework — Revenue, Authority, Timeline must all be confirmed",
            "Only attempt appointment booking and email capture when speaking to the actual owner",
            "When prospect says 'not interested' → pivot to 6-month follow-up, not goodbye",
            "Lock in specific appointment time — don't accept 'call me later'",
        ],
        "script_notes": "Opener should be disarming. Hook = 'have you ever thought about what your company might be worth?'",
        "template_type": "business",
    },

    "Stuart Moss / CIC Partners": {
        "type": "business",
        "framework": "5-Step Script Flow",
        "checklist": [
            "If agent reached the owner — did agent ask about long-term plans (sell, partner, step back)?",
            "If agent reached the owner — did agent get business nature and number of employees?",
            "If agent reached the owner — did agent get estimated annual revenues?",
            "Did agent get email? (always — owner or gatekeeper)",
            "If agent reached the owner — did agent schedule a callback with the acquisitions team?",
            "If prospect was skeptical — did agent use the CIC backstory?",
        ],
        "hard_disqualifiers": [
            "Business less than 5 years old",
            "Owner not open to any discussion",
        ],
        "red_flags": [
            "Agent asked key qualification questions to a gatekeeper instead of the owner",
            "Agent pushed hard sale instead of exploratory framing",
            "Agent skipped email capture",
        ],
        "coaching_focus": [
            "Frame as exploratory — NOT a sales call",
            "Key questions (plans, revenue, employees) are only for the owner — don't waste them on gatekeepers",
            "If skeptical: use full CIC backstory (20 years, 50+ deals, $250M capital)",
            "Always close with a specific date/time for the intro call",
        ],
        "script_notes": "Must sound like a private introduction, not a pitch.",
        "template_type": "business",
    },

    "Smithton / Boone (RE Cash Buyer)": {
        "type": "real_estate",
        "framework": "6-Part: Price · Condition · Timeline · Motivation · Close",
        "checklist": [
            "Did agent confirm seller's name and property address?",
            "Did agent ask asking price?",
            "Did agent ask about property condition (beds/baths/sqft/repairs)?",
            "Did agent ask about occupancy (owner-occupied / rental / vacant)?",
            "Did agent ask about mortgage balance?",
            "Did agent ask about timeline?",
            "Did agent ask about motivation?",
            "Did agent schedule callback with Property Specialist?",
            "Did agent get email?",
        ],
        "hard_disqualifiers": [
            "Prospect said they are not looking to sell",
            "No motivation and no equity indication",
        ],
        "red_flags": [
            "Agent skipped asking price question",
            "Agent skipped mortgage / equity question",
            "Agent didn't identify motivation",
            "Agent submitted a throwaway lead (no motivation)",
        ],
        "coaching_focus": [
            "Price anchor starts at 40% of Zillow — work up slowly",
            "Mortgage balance is key — no equity = deal won't work",
            "Throwaway = no motivation — don't submit",
            "Always schedule a specific callback with the Property Specialist",
        ],
        "script_notes": "Cash offer framing: no repairs, no commissions, fast close, cover closing costs.",
        "template_type": "smithton",
    },

    "Jordyn / Barracuda (RE Multifamily)": {
        "type": "real_estate",
        "framework": "Multifamily Qualification",
        "checklist": [
            "Did agent ask number of units?",
            "Did agent ask unit mix (1-bed, 2-bed, etc.)?",
            "Did agent ask how many units are occupied?",
            "Did agent ask monthly rent per unit?",
            "Did agent ask how long they've owned it?",
            "Did agent ask about CapEx / repairs done or needed?",
            "Did agent ask about asking price?",
            "Did agent ask about timeline?",
            "Did agent ask about motivation?",
            "Did agent confirm phone + email before ending call?",
        ],
        "hard_disqualifiers": [
            "Single-family home (not multifamily)",
            "Owner not open to any offer",
        ],
        "red_flags": [
            "Agent skipped occupancy / rent questions",
            "Agent did not clarify this is multifamily only",
            "Agent skipped email or phone confirmation",
        ],
        "coaching_focus": [
            "Multifamily ONLY — single-family does not qualify",
            "Get all financial details: units, occupancy, rent, CapEx",
            "On price: 'I don't run numbers — I'll check with Jordyn after this'",
            "Always confirm phone AND email before hanging up",
        ],
        "script_notes": "Focus areas: St. Louis, Columbia, Jefferson City. They close on deals themselves — not a wholesaler.",
        "template_type": "jordyn",
    },

    "Scott Fuller / Haven Senior": {
        "type": "referral",
        "framework": "Referral Capture",
        "checklist": [
            "If agent reached the owner — did agent make clear this is NOT asking if their facility is for sale?",
            "If agent reached the owner — did agent ask if they know someone who might be selling a senior facility?",
            "Did agent get the owner's email? (always)",
            "Did agent speak confidentially and avoid operational questions? (always)",
            "Did agent use the correct voicemail rotation (VM1/VM2/VM3)?",
            "If owner was unavailable — did agent pivot to email capture?",
        ],
        "hard_disqualifiers": [
            "Wrong type of facility (not senior housing)",
        ],
        "red_flags": [
            "Agent asked if THEIR facility is for sale (wrong framing)",
            "Agent gave operational details or discussed specifics",
            "Agent didn't attempt email capture when owner was unavailable",
        ],
        "coaching_focus": [
            "CRITICAL: Never ask if their community is for sale — ask if they KNOW someone",
            "Primary goal every call = owner email",
            "When gatekeeper blocks: clarify it's not a sales call, pivot to email",
            "Use VM rotation exactly: VM1 Day 1, VM2 Day 5, VM3 Day 10",
        ],
        "script_notes": "Say: 'Scott recently sold a community in Missouri' — confidently, no elaboration unless asked.",
        "template_type": "scott",
    },

    "Sir Charles / Premier Site": {
        "type": "real_estate",
        "framework": "Dual Path: Seller OR Construction",
        "checklist": [
            "Did agent confirm owner + property address?",
            "Did agent attempt seller qualification first (Path A)?",
            "If not selling — did agent pivot to construction path (Path B)?",
            "Did agent ask about property condition (beds/baths/sqft/repairs)?",
            "Did agent ask about mortgage / liens / taxes owed?",
            "Did agent ask about timeline and motivation?",
            "Did agent get price anchor ('what number would you need to move forward')?",
            "Did agent get email?",
            "Did agent ask if prospect is open to listing the property?",
        ],
        "hard_disqualifiers": [
            "No to selling AND no renovation project AND not open to listing",
        ],
        "red_flags": [
            "Agent gave up after 'not selling' without pivoting to construction path",
            "Agent took on small handyman requests (below minimum threshold)",
            "Agent didn't ask about listing option",
        ],
        "coaching_focus": [
            "Always try BOTH paths — don't leave after seller says no",
            "Construction minimum: paint, roofing, gutters, floors, kitchens, baths, sheetrock",
            "Too small: minor patches, single fixture replacements — politely decline",
            "If wants market value → pivot to listing path",
        ],
        "script_notes": "Two pipelines: Acquisition (seller) and Construction. Always try both.",
        "template_type": "listing",
    },

    "Shiraz (RE Listing)": {
        "type": "real_estate",
        "framework": "Listing Agent Script",
        "checklist": [
            "Did agent ask if prospect is considering selling within 2 years?",
            "Did agent ask if they're open to working with a realtor?",
            "Did agent get timeline?",
            "Did agent get motivation?",
            "Did agent ask about property condition?",
            "Did agent ask if there are any updates to the property?",
            "Did agent ask if prospect is open to listing the property?",
            "Did agent get email?",
            "Did agent schedule callback?",
        ],
        "hard_disqualifiers": [
            "Not selling within 2 years and no email",
        ],
        "red_flags": [
            "Agent skipped email capture",
            "Agent didn't ask about property condition or updates",
            "Agent didn't ask about listing option",
        ],
        "coaching_focus": [
            "Ask: 'Do you have a realtor you like working with?' (soft opener)",
            "Always capture email even for cold / no-timeline leads",
            "Ask about condition and updates — it helps with valuation",
        ],
        "script_notes": "Listing script — same flow as Kyle/Biancardi.",
        "template_type": "listing",
    },

    "Kyle / Biancardi (RE Listing)": {
        "type": "real_estate",
        "framework": "Listing + Appointment",
        "checklist": [
            "Did agent ask if prospect is considering selling?",
            "Did agent ask about timeline and motivation?",
            "Did agent ask about property condition?",
            "Did agent ask if there are any updates to the property?",
            "Did agent ask if prospect is open to listing the property?",
            "Did agent get email?",
            "Did agent get callback confirmation?",
        ],
        "hard_disqualifiers": [
            "Not selling and no email",
        ],
        "red_flags": [
            "Agent skipped email",
            "Agent didn't ask about property condition or updates",
            "Agent didn't ask about listing option",
        ],
        "coaching_focus": [
            "Goal is appointment booking — always push for a specific callback time",
            "Always get email even if they won't book now",
            "Condition and updates matter — ask every time",
        ],
        "script_notes": "Primary close = booking a specific callback or appointment.",
        "template_type": "listing",
    },

    "Giancarlo / Real Broker NJ": {
        "type": "real_estate",
        "framework": "Seller + Referral",
        "checklist": [
            "Did agent ask if prospect is considering selling?",
            "Did agent get timeline?",
            "Did agent get motivation?",
            "Did agent get email?",
            "Did agent schedule a callback at the prospect's best time?",
        ],
        "hard_disqualifiers": [
            "Not selling and no email",
        ],
        "red_flags": [
            "Agent skipped email capture",
            "Agent didn't ask for callback at prospect's best time",
        ],
        "coaching_focus": [
            "Always ask for the prospect's best time for a callback — don't assume",
            "Even cold leads need an email captured",
        ],
        "script_notes": "5 active campaigns — confirm which campaign before analyzing.",
        "template_type": "giancarlo",
    },
}


# ─── Lead Templates ───────────────────────────────────────────────────────────

LEAD_TEMPLATES = {

    "business": """{caller_name} - {date}
Temp: {temp}

Contact Info:
  Contact Name: {contact_name}
  Business Name: {business_name}
  Number: {phone}
  Email: {email}

Business Details:
  Business Address: {address}
  Nature of Business: {nature_of_business}
  Number of Employees: {employees}
  Est. Annual Revenue: {revenue}
  Best Time Window for Intro Call: {callback}
  Notes: {notes}

Call Recording: """,

    "smithton": """{caller_name} - {date}
Temp: {temp}
Lead Type: {lead_type}

Seller Name: {seller_name}
Address: {address}
Phone Number: {phone}
Email: {email}

Motive/Pain: {motivation}
Actively Selling? {actively_selling}
List with Realtor? {list_with_realtor}
What if we didn't give them the price: {price_reaction}

Occupancy: {occupancy}
Beds/Baths: {beds_baths}
Sqft: {sqft}
Condition/Repairs: {condition}
Mortgage: {mortgage}

Market Value:
Asking Price: {asking_price}
Timeline: {timeline}

Callback: {callback}
Notes: {notes}
Call Recording: """,

    "jordyn": """{caller_name} - {date}
Lead Temp: {temp}
Lead Type: {lead_type}

Address: {address}
Seller Name: {seller_name}
Phone Number: {phone}
Email: {email}

# Units: {units}
Occupancy: {occupancy}
Condition: {condition}

Timeline: {timeline}
Reason: {motivation}
AP: {asking_price}
MV:

Other Notes: {notes}""",

    "listing": """{caller_name} - {date}
Temp: {temp}

Contact Info:
  Name: {seller_name}
  Number: {phone}
  Email: {email}
  Address: {address}
  Call Back On: {callback}

Condition: {condition}

Motivation/Pain and Others:
  Notes: {notes}
  Residency: {occupancy}
  Timeline: {timeline}
  Reason: {motivation}
  AP: {asking_price}
  Zestimate:
  Listing: {listing_open}

Call Recording: """,

    "giancarlo": """{caller_name} - {date}
Temp: {temp}

Contact Info:
  Name: {seller_name}
  Number: {phone}
  Email: {email}
  Address: {address}

Notes: {notes}

Timeline: {timeline}
Listing: {listing_open}
Reason: {motivation}

Call Recording: """,

    "scott": """{caller_name} - {date}
Temperature: {temp}
Name: {contact_name}
Email: {email}
Phone: {phone}
Facility Name: {facility_name}
Title: {title}
Address: {address}

Notes: {notes}

Call Recording: """,
}


# ─── Temperature Logic (for GPT scoring prompt) ───────────────────────────────

TEMP_LOGIC = """
Determine lead temperature using these rules IN ORDER:

1. If prospect has NO valid motive or reason to sell → COLD (regardless of anything else)
2. If timeline is more than 1 year → NURTURE
3. If timeline is around 1 year → COLD
4. If timeline is ASAP to 3 months (soon):
   a. If AP < MV (or MV unknown) AND valid motive → HOT
   b. If AP > MV AND valid motive AND open to listing → WARM
   c. If AP > MV AND valid motive AND NOT open to listing → COLD

When MV is unknown (not yet looked up), base preliminary temperature on motive and timeline only,
and flag it as "Preliminary — recalculate after MV is confirmed."

Always add any information the prospect provided that does not fit an existing field into the Notes section.
"""


# ─── Universal Rules (applied to all clients) ─────────────────────────────────

UNIVERSAL_RULES = [
    "Did agent always ask for email on every call?",
    "Did agent confirm prospect's name at least once?",
    "Did agent lock in a specific callback time (not 'call anytime')?",
    "Did agent handle DNC immediately if mentioned (hang up, mark DNC)?",
    "Did agent sound natural and not robotic?",
    "Did agent reconfirm phone number before ending a lead call?",
    "Did agent avoid saying 'My manager will call you with an offer'?",
    "Did agent avoid mentioning offers proactively?",
]


# ─── Whisper vocabulary hint ──────────────────────────────────────────────────

WHISPER_VOCAB = (
    # Keep this balanced and short (~80 tokens). Heavy email-shape primers
    # were biasing Whisper to pattern-match and drop non-email speech.
    # Domain terms — helps with rare words Whisper has seen less often
    "Zillow, MLS, realtor, duplex, triplex, multifamily, Zestimate, "
    "ARV, HOA, escrow, wholesale, "
    # Client / company names so they come out right
    "ReSimpli, HubSpot, Dealonomy, Haven Senior, Biancardi, Smithton, "
    "Boone, CIC Partners, Giancarlo, Shiraz, Premier Site Solutions, "
    "Sir Charles, Scott Fuller, "
    # Phonetic alphabet — preserves spelled names/emails without biasing
    "alpha, bravo, charlie, delta, echo, foxtrot, golf, hotel, india, "
    "juliet, kilo, lima, mike, november, oscar, papa, quebec, romeo, "
    "sierra, tango, uniform, victor, whiskey, yankee, zulu"
)

WHISPER_HALLUCINATIONS = [
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "like and subscribe",
    "email addresses should be written",
    "not spelled out letter by letter",
]
