import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load the environment variables from .env file
load_dotenv()

print("--- Key Test Script ---")
try:
    # 1. Load the key from the environment
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")
    
    # 2. Print a snippet of the key to confirm it loaded
    print(f"Loaded Key Snippet: {api_key[:7]}...{api_key[-4:]}")
    
    # 3. Configure the API with the key
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    # 4. Make a simple test call
    print("Sending a simple test prompt to the Gemini API...")
    response = model.generate_content("Tell me a one-sentence fun fact about space.")
    
    # 5. Print the result
    print("\nSUCCESS! The API responded:")
    print(response.text)

except Exception as e:
    print("\n--- ERROR ---")
    print(f"The test failed. Here is the error message:\n{e}")