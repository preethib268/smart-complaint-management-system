import os
from dotenv import load_dotenv
from google import genai

# Load the API key from the .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Create the Gemini client using your key
client = genai.Client(api_key=api_key)

# Send a simple test message (model name from Google's official quickstart)
response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Say hello in one short sentence."
)

# Print the AI's reply
print("AI replied:", response.text)