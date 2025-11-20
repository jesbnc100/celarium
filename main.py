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

    restored = req.text
    for fake_v, real_v in session["mapping"].items():
        restored = restored.replace(fake_v, real_v)

    return {"restored_text": restored}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)