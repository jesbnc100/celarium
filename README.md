# Celarium

**Privacy middleware for multi-agent LLM systems.**

Use LLMs on customer data without sending PII. Anonymize before processing, restore after.

---

## The Problem

You're building multi-agent systems that process customer data:
- Support bots handling customer emails
- Workflow automation on sensitive data
- AI agents analyzing customer information

Every LLM call with PII is a compliance risk.

**Options today:**
- ❌ Send raw data to LLM → GDPR/HIPAA violation risk
- ❌ Redact data → LLM loses context, outputs are garbage
- ❌ Run local models → slow, limited capability

**There's no good option.**

---

## The Solution

Celarium intercepts all agent→LLM calls, anonymizes PII, processes safely with LLM, then restores the original values.

Your data never touches the LLM in raw form.

```
Input:  "Email john.doe@gmail.com about his $50 debt"
        ↓
Anonymized: "Email william.smith@gmail.com about his $50 debt"
        ↓ (sent to LLM)
        ↓
Output: "Dear william.smith, regarding your outstanding balance..."
        ↓
Restored: "Dear john.doe, regarding your outstanding balance..."
```

---

## Why Celarium

- **Compliance-friendly:** Anonymized data is easier to justify to compliance teams
- **Simple integration:** One API call before every LLM invocation
- **Works with any LLM:** LLM, Claude, Gemini, local models
- **Multi-agent ready:** One middleware protects all your agents
- **Open source:** See exactly what we're doing with your data

---

## Quick Start

### Installation

```bash
pip install -r requirements.txt
python main.py
```

The API runs on `http://localhost:8000`

### Usage

#### Step 1: Anonymize

```bash
curl -X POST http://localhost:8000/v1/anonymize \
  -H "X-API-Key: sk_test_celarium_founder_001" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Send an email to john.doe@acme.com about his $5,000 invoice"
  }'
```

**Response:**
```json
{
  "anonymized_text": "Send an email to robert.johnson@example.com about his $5,000 invoice",
  "session_id": "abc123def456",
  "entities_found": 2
}
```

#### Step 2: Send to LLM

Use the `anonymized_text` with your LLM:

```python
import openai

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{
        "role": "user",
        "content": "Send an email to robert.johnson@example.com about his $5,000 invoice"
    }]
)

llm_response = response.choices[0].message.content
```

#### Step 3: Restore

```bash
curl -X POST http://localhost:8000/v1/restore \
  -H "X-API-Key: sk_test_celarium_founder_001" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123def456",
    "text": "Dear robert.johnson, regarding your $5,000 invoice..."
  }'
```

**Response:**
```json
{
  "restored_text": "Dear john.doe, regarding your $5,000 invoice..."
}
```

---

## API Reference

### POST `/v1/anonymize`

Anonymize PII in text and create a session.

**Headers:**
- `X-API-Key: sk_test_celarium_*` (required)

**Request:**
```json
{
  "text": "string"
}
```

**Response:**
```json
{
  "anonymized_text": "string",
  "session_id": "string (uuid)",
  "entities_found": 0
}
```

### POST `/v1/restore`

Restore original PII using a session ID.

**Headers:**
- `X-API-Key: sk_test_celarium_*` (required)

**Request:**
```json
{
  "session_id": "string",
  "text": "string"
}
```

**Response:**
```json
{
  "restored_text": "string"
}
```

### DELETE `/v1/sessions/{session_id}`

Manually delete a session (optional).

**Headers:**
- `X-API-Key: sk_test_celarium_*` (required)

---

## Security

- ✅ HTTPS encryption (use in production)
- ✅ Session-based mapping (never returned to client)
- ✅ 1-hour session expiration (automatic cleanup)
- ✅ API key authentication (hardcoded for MVP)
- ✅ Server-side storage (mappings not leaked)

**Not HIPAA/GDPR certified yet.** We're MVP stage. For enterprise, additional compliance measures may be needed. See below.

---

## For Compliance Teams

**How we help you stay compliant:**

1. **PII Protection:** We anonymize before external processing
2. **Audit Trail:** Sessions logged with timestamps
3. **Data Control:** You control the session lifecycle
4. **No Data Sharing:** We don't use your data for training or improvement
5. **DPA Available:** We provide a Data Processing Agreement on request

**Responsibility:** You (the customer) remain the data controller. Celarium is a processor helping you comply.

---

## Use Cases

### Customer Support Agents

Your support bot processes customer emails, chat history, and account info. Celarium anonymizes before LLM analyzes, then restores the response.

### Multi-Step Workflows

```
Agent 1 (Retrieval) → gets customer data
    ↓
Celarium (Anonymize) → protects PII
    ↓
Agent 2 (Analysis) → LLM processes safely
    ↓
Celarium (Restore) → restores original names
    ↓
Agent 3 (Output) → generates compliant response
```

### Automated Business Workflows

Billing agents, data processing agents, lead scoring—all calling LLMs on sensitive data. Celarium is a one-line integration that protects all of them.

---

## Limitations (MVP)

- Handles: Names, emails, phone numbers, SSNs, basic PII
- Sessions expire after 1 hour
- In-memory storage (data lost on restart)
- No audit logging (yet)
- No advanced entity types (yet)

---

## Roadmap

- [ ] Persistent session storage (database)
- [ ] Advanced entity detection (medical codes, financial data)
- [ ] Audit logging and compliance reports
- [ ] Custom entity types and rules
- [ ] Multi-language support
- [ ] Performance metrics dashboard

---

## Development

### Local Setup

```bash
git clone https://github.com/yourusername/celarium.git
cd celarium
pip install -r requirements.txt
python main.py
```

Server runs on `http://localhost:8000`

### Testing

```bash
# Test anonymize
curl -X POST http://localhost:8000/v1/anonymize \
  -H "X-API-Key: sk_test_celarium_founder_001" \
  -H "Content-Type: application/json" \
  -d '{"text": "My name is John Doe and my email is john@example.com"}'

# Test restore
curl -X POST http://localhost:8000/v1/restore \
  -H "X-API-Key: sk_test_celarium_founder_001" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "[SESSION_ID_FROM_ABOVE]", "text": "My name is William Hill and my email is william@example.com"}'
```

---

## Status

⚠️ **Early stage / MVP.** Actively seeking feedback. If you're building multi-agent systems, we'd love to hear from you.

**Feedback:** Open an issue on GitHub or email us.

---

## Contributing

We're open to contributions. Check the issues for ideas, or open your own.

---

Made with ❤️ by Celarium team
