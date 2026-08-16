import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load API key from .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# The complaint we want the AI to analyze (a test example)
complaint = "The wifi in the boys hostel has not worked for 3 days and no one is responding."

# Instructions we give the AI
prompt = f"""
You are a complaint-handling assistant for a college.
Read the complaint below and do three things:
1. Decide which department it should go to. Choose ONE from:
   IT, Hostel, Examination, Maintenance, Library, Administration, Other.
2. Decide the urgency. Choose ONE from: Low, Medium, High.
3. Write a short, polite acknowledgement reply (2 sentences max) for the person.

Complaint: "{complaint}"
"""

# Tell Gemini to reply as clean JSON with exactly these fields
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "urgency": {"type": "string"},
                "reply": {"type": "string"}
            },
            "required": ["category", "urgency", "reply"]
        }
    )
)

# The reply comes back as JSON text; turn it into a Python dictionary
result = json.loads(response.text)

print("Category:", result["category"])
print("Urgency :", result["urgency"])
print("Reply   :", result["reply"])