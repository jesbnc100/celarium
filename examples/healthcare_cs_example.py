import requests
from langchain_openai import ChatOpenAI

CELARIUM_URL = "http://98.81.182.73"
API_KEY = "sk_test_celarium_founder_001"

llm = ChatOpenAI(
    model="gpt-oss-20b:free",
    base_url="https://openrouter.ai/api/v1",
    api_key="sk-apikey"  # Replace with your API key
)


# ============ HEALTHCARE CHATBOT ============
def healthcare_support_chat(patient_message: str):
    """Healthcare chatbot with privacy middleware - FULL VERSION"""

    print(f"\n{'=' * 70}")
    print("HEALTHCARE SUPPORT CHATBOT WITH CELARIUM PRIVACY MIDDLEWARE")
    print(f"{'=' * 70}\n")

    # ========== STEP 1: ANONYMIZE ==========
    print("STEP 1: ANONYMIZING PATIENT DATA")
    print("-" * 70)
    print(f"Original patient message:\n{patient_message}\n")

    anon_response = requests.post(
        f"{CELARIUM_URL}/v1/anonymize",
        headers={"X-API-Key": API_KEY},
        json={"text": patient_message}
    ).json()

    anonymized_message = anon_response["anonymized_text"]
    session_id = anon_response["session_id"]
    entities_found = anon_response["entities_found"]

    print(f"✓ PII Detected & Anonymized: {entities_found} entities")
    print(f"✓ Session ID: {session_id}")
    print(f"\nAnonymized message (safe to send to LLM):\n{anonymized_message}\n")

    # ========== STEP 2: SEND TO LLM ==========
    print("\n" + "=" * 70)
    print("STEP 2: PROCESSING WITH LLM (ANONYMIZED DATA ONLY)")
    print("-" * 70)
    print("Sending anonymized message to the LLM...")

    system_prompt = """You are a professional and empathetic healthcare support agent.
Your role is to help patients with:
- Appointment scheduling and rescheduling
- Insurance information and coverage questions
- General health inquiries
- Medical record access

Always be professional, caring, and clear. Never provide medical diagnosis."""

    llm_response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": anonymized_message}
    ]).content

    print(f"✓ LLM Response (with fake names/data):\n{llm_response}\n")

    # ========== STEP 3: RESTORE ==========
    print("\n" + "=" * 70)
    print("STEP 3: RESTORING ORIGINAL PATIENT DATA")
    print("-" * 70)
    print(f"Using session ID: {session_id}")
    print("Swapping fake data back to original patient data...\n")

    restored_response = requests.post(
        f"{CELARIUM_URL}/v1/restore",
        headers={"X-API-Key": API_KEY},
        json={
            "session_id": session_id,
            "text": llm_response
        }
    ).json()

    final_response = restored_response["restored_text"]

    print(f"✓ Original patient data restored\n")

    # ========== FINAL OUTPUT ==========
    print("\n" + "=" * 70)
    print("FINAL RESPONSE TO PATIENT")
    print("=" * 70)
    print(f"\n{final_response}\n")

    # ========== SUMMARY ==========
    print("\n" + "=" * 70)
    print("PRIVACY FLOW SUMMARY")
    print("=" * 70)
    print(f"✓ Patient Data Never Sent to the LLM in Raw Form")
    print(f"✓ {entities_found} PII Entities Protected")
    print(f"✓ Session ID: {session_id}")
    print(f"✓ Compliance Safe: Original data stayed on your server")
    print(f"✓ Patient Received Response With Their Original Name/Info")
    print(f"{'=' * 70}\n")

    return final_response


# ============ TEST EXAMPLES ============
if __name__ == "__main__":
    # Example 1: Appointment Rescheduling
    print("\n\n")
    print("█" * 70)
    print("█ EXAMPLE 1: APPOINTMENT RESCHEDULING")
    print("█" * 70)

    patient_input_1 = """
    Hi, I'm John Doe, MRN-123456. I need to reschedule my 
    appointment with Dr. Sarah Johnson at Austin Regional Medical Center. 
    My email is john@gmail.com and phone is (555) 123-4567.
    I prefer morning appointments if possible.
    """

    healthcare_support_chat(patient_input_1)

    # Example 2: Insurance Question
    print("\n\n")
    print("█" * 70)
    print("█ EXAMPLE 2: INSURANCE COVERAGE QUESTION")
    print("█" * 70)

    patient_input_2 = """
    Hello, my name is Jane Smith. I have an insurance policy POL-987654321
    with Blue Cross Blue Shield (Group G12345). I received a bill for $500 
    for my recent lab work. Is this covered under my plan? 
    You can reach me at jane.smith@example.com or (555) 987-6543.
    """

    healthcare_support_chat(patient_input_2)

    # Example 3: General Health Question
    print("\n\n")
    print("█" * 70)
    print("█ EXAMPLE 3: GENERAL HEALTH QUESTION")
    print("█" * 70)

    patient_input_3 = """
    Hi, I'm Michael Chen, SSN 456-78-9012. I've been experiencing 
    headaches for the past week. Should I schedule an appointment? 
    I work during the day so I prefer evening slots. 
    Contact: michael.chen@outlook.com, (555) 234-5678
    """

    healthcare_support_chat(patient_input_3)