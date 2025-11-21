import uvicorn
import os
import uuid
import re
import random
import json
from datetime import datetime
from typing import Union, List, Dict, Any
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from faker import Faker
from gliner import GLiNER

app = FastAPI(title="Celarium AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
VALID_API_KEYS = {"sk_test_celarium_founder_001", "sk_test_celarium_beta_001"}
SESSIONS = {}
fake = Faker()

# Load Model
print("Loading GLiNER...")
model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
print("Loaded.")

# Regex & Labels
REGEX_PATTERNS = {
    "EMAIL_ADDRESS": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "PHONE_NUMBER": r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    "MRN": r'\bMRN[-_]\w+\b',
    "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
    "INSURANCE_GROUP": r'\bG\d{5,}\b',
    "INSURANCE_POLICY": r'\b(POL|POLICY)[-_]?\d+\b',
    "FULL_ADDRESS": r'\d+\s+[A-Za-z0-9\s\.]+,\s+[A-Za-z\s\.]+,\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?'
}
AI_LABELS = ["person", "physical address", "organization", "date of birth"]


# Generators
def generate_clean_name():
    return f"{fake.first_name()} {fake.last_name()}"


def generate_matching_email(fake_name: str):
    if not fake_name: return f"user{random.randint(1000, 9999)}@example.com"
    parts = fake_name.lower().split()
    base = f"{parts[0]}{parts[1]}" if len(parts) >= 2 else parts[0]
    return f"{base}{random.randint(100, 9999)}@example.com"


# --- UPDATED GENERATORS ---

def generate_clean_phone():
    """Matches the requested format: +1-XXX-XXX-XXXX"""
    return f"+1-{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}"


def generate_medical_org():
    """Generates realistic Healthcare/Clinical names"""
    suffixes = [
        "Medical Center", "Regional Health", "General Hospital",
        "Health Group", "Family Clinic", "Community Care",
        "Medical Associates", "Health System", "Diagnostics Lab"
    ]
    # 50% chance of City-based name (e.g. "Austin Regional Health")
    # 50% chance of Name-based name (e.g. "Rivera Medical Group")
    prefix = fake.city() if random.random() > 0.5 else fake.last_name()
    return f"{prefix} {random.choice(suffixes)}"


def get_fake_value(label: str, context: dict) -> str:
    label = label.upper()

    if "PERSON" in label:
        val = generate_clean_name()
        context["last_person"] = val
        return val

    if "EMAIL" in label:
        return generate_matching_email(context.get("last_person", ""))

    if "PHONE" in label:
        return generate_clean_phone()  # <--- Uses new format

    if "ADDRESS" in label or "LOCATION" in label:
        # Fixes address leak by generating full block
        return f"{fake.street_address()}, {fake.city()}, {fake.state_abbr()} {fake.zipcode()}"

    if "MRN" in label:
        return f"MRN-{fake.random_number(digits=8, fix_len=True)}"
    if "SSN" in label:
        return fake.ssn()
    if "DATE" in label:
        return str(fake.date_of_birth(minimum_age=18, maximum_age=90))
    if "POLICY" in label:
        return f"POL-{fake.random_number(digits=9, fix_len=True)}"
    if "GROUP" in label:
        return f"G{fake.random_number(digits=5, fix_len=True)}"

    if "ORGANIZATION" in label:
        return generate_medical_org()  # <--- Uses new medical generator

    return f"REDACTED_{uuid.uuid4().hex[:6]}"


def analyze_and_replace(text: str) -> (str, dict):
    """Core logic to anonymize a single string block"""
    findings = []
    # Regex
    for label, pattern in REGEX_PATTERNS.items():
        for match in re.finditer(pattern, text):
            findings.append({"start": match.start(), "end": match.end(), "label": label, "score": 1.0})
    # AI
    try:
        ai_preds = model.predict_entities(text, AI_LABELS, threshold=0.35)
        for p in ai_preds:
            findings.append({"start": p["start"], "end": p["end"], "label": p["label"], "score": p["score"]})
    except:
        pass

    # Merge
    findings.sort(key=lambda x: x["start"])
    merged = []
    for f in findings:
        if not merged:
            merged.append(f)
            continue
        last = merged[-1]
        if f["start"] < last["end"]:
            if f["score"] > last["score"] or (f["end"] - f["start"]) > (last["end"] - last["start"]):
                merged[-1] = f
        else:
            merged.append(f)

    # Generate Fakes
    mapping = {}
    replacements = []
    context = {"last_person": ""}
    used_fakes = set()

    for ent in merged:
        original = text[ent["start"]:ent["end"]]
        # Skip JSON Keys
        if original.lower() in ["person_name", "date_of_birth", "ssn", "mrn", "email", "phone", "address"]:
            continue

        fake_val = get_fake_value(ent["label"], context)
        if fake_val in used_fakes:
            fake_val = f"{fake_val}_{random.randint(1, 99)}"
        used_fakes.add(fake_val)

        mapping[fake_val] = original
        replacements.append({"start": ent["start"], "end": ent["end"], "fake": fake_val})

    # Replace
    replacements.sort(key=lambda x: x["start"], reverse=True)
    text_chars = list(text)
    for r in replacements:
        text_chars[r["start"]:r["end"]] = list(r["fake"])

    return "".join(text_chars), mapping


# --- ENDPOINTS ---

async def get_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(401, "Invalid API Key")
    return api_key


class AnonymizeRequest(BaseModel):
    text: Union[str, List[Any], Dict[str, Any]]


class RestoreRequest(BaseModel):
    session_id: str
    text: str


@app.post("/v1/anonymize")
async def anonymize(req: AnonymizeRequest, api_key: str = Security(get_api_key)):
    input_data = req.text
    global_mapping = {}
    final_output_str = ""

    # LOGIC: Handle List vs Single String
    if isinstance(input_data, list):
        # Process each item individually to avoid Token Limit
        anonymized_list = []
        for item in input_data:
            item_str = json.dumps(item)
            anon_str, item_map = analyze_and_replace(item_str)
            anonymized_list.append(json.loads(anon_str))  # Convert back to dict
            global_mapping.update(item_map)

        # Return as formatted JSON string
        final_output_str = json.dumps(anonymized_list, indent=2)

    else:
        # Single object or string
        text_to_process = json.dumps(input_data) if isinstance(input_data, dict) else str(input_data)
        final_output_str, global_mapping = analyze_and_replace(text_to_process)

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {"mapping": global_mapping, "created": datetime.now(), "api_key": api_key}

    return {
        "anonymized_text": final_output_str,
        "session_id": session_id,
        "entities_found": len(global_mapping)
    }


@app.post("/v1/restore")
async def restore(req: RestoreRequest, api_key: str = Security(get_api_key)):
    session = SESSIONS.get(req.session_id)
    if not session or session["api_key"] != api_key:
        raise HTTPException(404, "Session not found")

    text = req.text
    mapping = session["mapping"]

    # --- Helper: Normalize text to just digits for phone matching ---
    def get_digits(s):
        return "".join(filter(str.isdigit, s))

    # --- 1. Exact Match (Highest Priority) ---
    # Sort by length (longest first) to prevent substring collisions
    # e.g. Replace "Joanna Torres" before "Joanna"
    for fake, real in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        text = text.replace(fake, real)

    # --- 2. Build Partial Mappings (Smart Repair) ---
    partial_map = {}
    phone_map = {}

    for fake_full, real_full in mapping.items():
        # A. Phone Numbers: Map digits -> Real Number
        # If the fake value has 10+ digits, store it for fuzzy matching
        f_digits = get_digits(fake_full)
        if len(f_digits) >= 10:
            phone_map[f_digits] = real_full

        # B. Names & Organizations: Split into parts
        if " " in fake_full:
            fake_parts = fake_full.split()
            real_parts = real_full.split()

            # Strategy 1: 1-to-1 Word Mapping (Best for Names: "John Doe" -> "Jane Smith")
            if len(fake_parts) == len(real_parts):
                for i, f_part in enumerate(fake_parts):
                    # Only map parts that look like names (Capitalized, >2 chars) to avoid mapping "The" -> "A"
                    if len(f_part) > 2 and f_part[0].isupper():
                        partial_map[f_part] = real_parts[i]

            # Strategy 2: Last Word Fallback (Best for "Madison Jackson" -> "Dr. Sarah Johnson")
            # If lengths differ, the Last Name is usually the safest anchor.
            elif len(fake_parts) > 1 and len(real_parts) > 0:
                f_last = fake_parts[-1]
                r_last = real_parts[-1]
                if len(f_last) > 2 and f_last[0].isupper():
                    partial_map[f_last] = r_last

            # Strategy 3: Organization Root Word (Best for Emails)
            # If fake is "Kennethburgh General Hospital", map "Kennethburgh" -> "Blue Cross"
            # This fixes hallucinated emails like "support@kennethburghhealth.org"
            if len(fake_parts) > 0 and len(fake_parts[0]) > 5:
                # Store root word mapping
                partial_map[fake_parts[0]] = real_full

    # --- 3. Apply Phone Number Fixes (Regex) ---
    # Captures various formats: +1-555... | (555)... | 555.555... | 555 555...
    # \W matches non-word chars, including unicode hyphens the LLM might use
    phone_pattern = r'(?:\+?1[\W_]?)?\(?\d{3}\)?[\W_]?\d{3}[\W_]?\d{4}'

    def phone_replacer(match):
        found_num = match.group(0)
        found_digits = get_digits(found_num)
        # Check if the found digits match any of our fake numbers
        for fake_digits, real_num in phone_map.items():
            if fake_digits in found_digits:
                return real_num
        return found_num

    text = re.sub(phone_pattern, phone_replacer, text)

    # --- 4. Apply Partial Text Fixes (Regex Boundaries) ---
    # Sort keys by length to replace "Kennethburgh" before "Ken"
    for fake_part, real_part in sorted(partial_map.items(), key=lambda x: len(x[0]), reverse=True):
        # Case 1: Word Boundary Match (Preserves whole words)
        # Matches "Joanna" in "Hello Joanna," but not in "Joannasaurus"
        pattern = r'\b' + re.escape(fake_part) + r'\b'
        text = re.sub(pattern, real_part, text)

        # Case 2: Aggressive Org Cleanup (Case-Insensitive)
        # Handles the email domain issue: "info@kennethburghhealth.org"
        # If we have a long unique keyword (like Kennethburgh), replace it even inside other strings
        if len(fake_part) > 5:
            # Collapse spaces in real_part for email compatibility (Blue Cross -> BlueCross)
            clean_real = real_part.replace(" ", "")
            text = re.sub(re.escape(fake_part), clean_real, text, flags=re.IGNORECASE)

    return {"restored_text": text}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)