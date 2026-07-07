import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

# Load .env specific to the softphone
load_dotenv()

app = FastAPI(title="VoiceKit Softphone")

# Serve the static UI files
app.mount("/static", StaticFiles(directory="static"), name="static")

TWILIO_API_KEY = os.getenv("TWILIO_API_KEY")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET")
TWILIO_TWIML_APP_SID = os.getenv("TWILIO_TWIML_APP_SID")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")

@app.get("/")
async def root():
    """Redirect to the softphone UI."""
    return RedirectResponse(url="/static/index.html")

@app.get("/token")
async def get_token():
    """Generates an Access Token for the Twilio Voice JavaScript SDK."""
    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity="browser-user"
    )

    voice_grant = VoiceGrant(
        outgoing_application_sid=TWILIO_TWIML_APP_SID,
        incoming_allow=True
    )
    token.add_grant(voice_grant)
    
    return {"token": token.to_jwt()}
