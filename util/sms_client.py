import os
import datetime
from pathlib import Path

def send_sms(msg: str):
    """
    Safely send an SMS alert without crashing the bot if it fails.
    If no TWILIO environment variables are found, it logs to a mock file.
    """
    try:
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        twilio_from = os.getenv("TWILIO_FROM_NUMBER")
        twilio_to = os.getenv("TWILIO_TO_NUMBER")

        if twilio_sid and twilio_token and twilio_from and twilio_to:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            client.messages.create(
                body=msg,
                from_=twilio_from,
                to=twilio_to
            )
        else:
            # Fall back to logging
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            mock_log = log_dir / "sms_mock.log"
            
            with open(mock_log, "a") as f:
                ts = datetime.datetime.now().isoformat()
                f.write(f"[{ts}] SMS_MOCK: {msg}\n")
    except Exception as e:
        # ABSOLUTELY DO NOT CRASH THE ENGINE IF SMS FAILS
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        try:
            with open(log_dir / "sms_errors.log", "a") as f:
                f.write(f"[{datetime.datetime.now()}] SMS ERROR: {e}\n")
        except:
            pass
