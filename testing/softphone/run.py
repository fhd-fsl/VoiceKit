import os
import sys
import subprocess
from twilio.rest import Client
from dotenv import load_dotenv

def main():
    print("Starting VoiceKit Softphone...")

    # Load root .env to get the main phone number
    root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    load_dotenv(root_env_path)
    
    # Load softphone specific .env
    load_dotenv()

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")  # from root .env
    phone_number = os.getenv("TWILIO_PHONE_NUMBER")  # from root .env
    app_sid = os.getenv("TWILIO_TWIML_APP_SID")

    if not all([account_sid, auth_token, phone_number, app_sid]):
        print("Error: Missing essential Twilio environment variables. Ensure both root .env and testing/softphone/.env are set.")
        sys.exit(1)

    print("Fetching main VoiceKit webhook URL...")
    client = Client(account_sid, auth_token)
    
    # Find the main phone number to check what its voice_url is currently set to
    numbers = client.incoming_phone_numbers.list(phone_number=phone_number, limit=1)
    if not numbers:
        print(f"Error: Could not find phone number {phone_number} on your Twilio account.")
        sys.exit(1)
    
    voice_url = numbers[0].voice_url
    print(f"Main VoiceKit webhook is currently: {voice_url}")

    # Update the TwiML App to point to the same Voice URL
    print("Updating Softphone TwiML App routing...")
    client.applications(app_sid).update(voice_url=voice_url)
    print("TwiML App configured.")

    # Start the softphone UI server
    print("Starting Softphone Server on port 8001...")
    try:
        # We run the server blocking the main thread
        subprocess.run([sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"])
    except KeyboardInterrupt:
        print("\nStopping Softphone...")
    finally:
        print("Goodbye!")

if __name__ == "__main__":
    main()
