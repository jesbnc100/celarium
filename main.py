import uvicorn
import os
import uuid
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from presidio_analyzer import AnalyzerEngine
from faker import Faker

# ============ CONFIG ============

app = FastAPI(
    title="Celarium AI",
    description="Privacy middleware for multi-agent LLM systems",
    version="0.1.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# API Keys (hardcoded for MVP)
VALID_API_KEYS = {
    "sk_test_celarium_founder_001",
    "sk_test_celarium_beta_001",
    "sk_test_celarium_beta_002",
}

# Sessions store (in-memory, expires after 1 hour)
SESSIONS = {}

# ============ INIT ============

fake = Faker()
analyzer = AnalyzerEngine()


# ============ AUTH ============

async def get_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key


# ============ DATA MODELS ============

class AnonymizeRequest(BaseModel):
    text: str


class AnonymizeResponse(BaseModel):
    anonymized_text: str
    session_id: str
    entities_found: int


class RestoreRequest(BaseModel):
    session_id: str
    text: str


class RestoreResponse(BaseModel):
    restored_text: str


class HealthResponse(BaseModel):
    status: str
    version: str


# ============ CORE LOGIC ============

def generate_fake_value(entity_type: str, used_fakes: set) -> str:
    """Generate a realistic fake value based on entity type"""
    max_attempts = 10

    if entity_type == "PERSON":
        for _ in range(max_attempts):
            fake_val = fake.name()
            if fake_val not in used_fakes:
                return fake_val
        return f"Person_{str(uuid.uuid4())[:8]}"

    elif entity_type == "EMAIL_ADDRESS":
        for _ in range(max_attempts):
            fake_val = fake.email()
            if fake_val not in used_fakes:
                return fake_val
        return f"user_{str(uuid.uuid4())[:8]}@example.com"

    elif entity_type == "PHONE_NUMBER":
        for _ in range(max_attempts):
            fake_val = fake.phone_number()
            if fake_val not in used_fakes:
                return fake_val
        return f"+1-555-{str(uuid.uuid4())[:4]}"

    elif entity_type == "US_SSN":
        for _ in range(max_attempts):
            fake_val = fake.ssn()
            if fake_val not in used_fakes:
                return fake_val
        return f"{str(uuid.uuid4())[:3]}-{str(uuid.uuid4())[:2]}-{str(uuid.uuid4())[:4]}"

    elif entity_type == "LOCATION":
        for _ in range(max_attempts):
            fake_val = fake.city()
            if fake_val not in used_fakes:
                return fake_val
        return f"City_{str(uuid.uuid4())[:8]}"

    elif entity_type == "DATE_TIME":
        for _ in range(max_attempts):
            fake_val = str(fake.date())
            if fake_val not in used_fakes:
                return fake_val
        return "1990-01-01"

    elif entity_type == "URL":
        for _ in range(max_attempts):
            fake_val = fake.url()
            if fake_val not in used_fakes:
                return fake_val
        return "https://example.com"

    else:
        # Generic: use entity type with UUID
        fake_val = f"{entity_type}_{str(uuid.uuid4())[:8]}"
        return fake_val


def anonymize_logic(text: str):
    """
    Detect PII with Presidio, replace with realistic fakes.
    Handles overlaps by preferring longer spans.
    Returns (anonymized_text, mapping) where mapping maps fake_value -> original_value.
    """
    try:
        analyzer_results = analyzer.analyze(text=text, language="en")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    if not analyzer_results:
        return text, {}

    # Convert to tuples and sort by start position (ascending), then by span length (descending)
    spans = [(r.start, r.end, r.entity_type) for r in analyzer_results]
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    # Merge overlapping spans, preferring longer ones
    merged = []
    for start, end, etype in spans:
        if not merged:
            merged.append((start, end, etype))
            continue

        last_start, last_end, last_type = merged[-1]
        if start < last_end:  # overlapping
            # Keep the longer span
            if (end - start) > (last_end - last_start):
                merged[-1] = (start, end, etype)
        else:
            merged.append((start, end, etype))

    # Build anonymized text by replacing spans with fake values
    cursor = 0
    parts = []
    mapping = {}
    used_fakes = set()

    for start, end, etype in merged:
        # Append text before this span (preserves spacing/punctuation)
        if cursor < start:
            parts.append(text[cursor:start])

        original_value = text[start:end]

        # Generate realistic fake replacement
        fake_value = generate_fake_value(etype, used_fakes)
        used_fakes.add(fake_value)

        # Append fake replacement
        parts.append(fake_value)

        # Record mapping for restoration
        mapping[fake_value] = original_value

        cursor = end

    # Append remaining text
    if cursor < len(text):
        parts.append(text[cursor:])

    anonymized_text = "".join(parts)
    return anonymized_text, mapping


def create_session(mapping: dict, api_key: str) -> str:
    """Create a session and store mapping server-side"""
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "mapping": mapping,
        "created": datetime.now(),
        "api_key": api_key
    }
    return session_id


def get_session(session_id: str, api_key: str) -> dict:
    """Retrieve session mapping, validate expiration"""
    session = SESSIONS.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["api_key"] != api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if datetime.now() - session["created"] > timedelta(hours=1):
        del SESSIONS[session_id]
        raise HTTPException(status_code=410, detail="Session expired")

    return session


def restore_logic(mapping: dict, text: str) -> str:
    """Swap fake values back to originals"""
    restored = text
    for fake_val, real_val in mapping.items():
        restored = restored.replace(fake_val, real_val)
    return restored


# ============ ENDPOINTS ============

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check"""
    return HealthResponse(status="ok", version="0.1.0")


@app.post("/v1/anonymize", response_model=AnonymizeResponse)
async def anonymize(req: AnonymizeRequest, api_key: str = Security(get_api_key)):
    """
    Anonymize PII in text. Returns anonymized text + session ID.
    Session ID is used to restore original values later.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    anonymized_text, mapping = anonymize_logic(req.text)
    session_id = create_session(mapping, api_key)

    return AnonymizeResponse(
        anonymized_text=anonymized_text,
        session_id=session_id,
        entities_found=len(mapping)
    )


@app.post("/v1/restore", response_model=RestoreResponse)
async def restore(req: RestoreRequest, api_key: str = Security(get_api_key)):
    """
    Restore original PII using session ID.
    Replaces anonymized values with originals.
    """
    if not req.session_id or not req.text:
        raise HTTPException(status_code=400, detail="session_id and text required")

    session = get_session(req.session_id, api_key)
    mapping = session["mapping"]

    restored_text = restore_logic(mapping, req.text)

    return RestoreResponse(restored_text=restored_text)


@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str, api_key: str = Security(get_api_key)):
    """Manually delete a session"""
    session = SESSIONS.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["api_key"] != api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    del SESSIONS[session_id]
    return {"status": "deleted"}


# ============ RUN ============

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)