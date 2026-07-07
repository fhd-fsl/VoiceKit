import os
import sys
import time
import subprocess
from pyngrok import ngrok
from twilio.rest import Client
from dotenv import load_dotenv

def main():
    print("Starting VoiceKit...")

    # Load environment variables
    load_dotenv()
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([account_sid, auth_token, phone_number]):
        print("Error: Missing essential Twilio environment variables in .env.")
        sys.exit(1)

    # 1. Start Ngrok
    print("Starting ngrok tunnel on port 8000...")
    ngrok_auth = os.getenv("NGROK_AUTHTOKEN")
    if ngrok_auth:
        ngrok.set_auth_token(ngrok_auth)
    
    public_url = ngrok.connect(8000).public_url
    print(f"Ngrok tunnel established at: {public_url}")

    # 2. Update Twilio Webhook
    print(f"Updating Twilio Phone Number ({phone_number}) webhook...")
    client = Client(account_sid, auth_token)
    
    # Find the phone number
    numbers = client.incoming_phone_numbers.list(phone_number=phone_number, limit=1)
    if not numbers:
        print(f"Error: Could not find phone number {phone_number} on your Twilio account.")
        ngrok.kill()
        sys.exit(1)

    twilio_number = numbers[0]
    webhook_url = f"{public_url}/voice"
    
    # Update voice URL and explicitly remove any SIP Trunk attached so Twilio honors the webhook
    twilio_number.update(voice_url=webhook_url, trunk_sid="")
    print(f"Webhook updated to: {webhook_url}")

    # 3. Start Uvicorn Server
    print("Starting FastAPI Server...")
    try:
        # We run the server blocking the main thread
        # When the user stops this via Ctrl+C, the finally block kills ngrok
        subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"])
    except KeyboardInterrupt:
        print("\nStopping VoiceKit...")
    finally:
        print("Cleaning up ngrok tunnel...")
        ngrok.kill()
        print("Goodbye!")

if __name__ == "__main__":
    main()
