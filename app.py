import re
import ssl
import time
import smtplib
from email.mime.text import MIMEText
import streamlit as st
from google import genai
from google.genai import types, errors
from twilio.rest import Client as TwilioClient
from prompts import SYSTEM_PROMPT

# -----------------------------------------------------------------------------
# Model Configuration
# -----------------------------------------------------------------------------
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.5-flash-lite"

# -----------------------------------------------------------------------------
# Configuration and Secrets Verification
# -----------------------------------------------------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.error(
        "Missing required secret `GEMINI_API_KEY` in `.streamlit/secrets.toml`. "
        "Please provide your Gemini API key to use AI Doubt Clarifier."
    )
    st.info(
        "For local development, define `GEMINI_API_KEY` in `.streamlit/secrets.toml`. "
        "For Streamlit Community Cloud, add it in App Settings > Secrets."
    )
    st.stop()

# Optional sharing integrations
GMAIL_ADDRESS = st.secrets.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = st.secrets.get("GMAIL_APP_PASSWORD")
email_configured = bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)

TWILIO_ACCOUNT_SID = st.secrets.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = st.secrets.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = st.secrets.get("TWILIO_WHATSAPP_NUMBER")
whatsapp_configured = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER)

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
@st.cache_resource
def get_gemini_client(api_key: str):
    """Initializes and caches the Google GenAI Client."""
    return genai.Client(api_key=api_key)

gemini_client = get_gemini_client(GEMINI_API_KEY)


def generate_doubt_explanation(client, contents, system_prompt):
    """
    Attempts generation with PRIMARY_MODEL.
    Falls back to FALLBACK_MODEL only on model/server-availability errors (5xx, 429, 404).
    Permanent client/auth errors (400, 401, 403) are raised immediately.
    """
    try:
        response = client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return response, PRIMARY_MODEL
    except errors.APIError as err:
        # Do not retry on permanent authentication or bad request errors
        if err.code in (400, 401, 403):
            raise
        # Fallback for server availability (5xx), rate limits (429), or model availability (404)
        response = client.models.generate_content(
            model=FALLBACK_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return response, FALLBACK_MODEL


def is_valid_email(email: str) -> bool:
    """Validates standard email address format."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))


def is_valid_phone(phone: str) -> bool:
    """Validates international phone format with country code (e.g., +1234567890)."""
    cleaned = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    pattern = r"^\+?[1-9]\d{6,14}$"
    return bool(re.match(pattern, cleaned))


def normalize_whatsapp_number(number: str) -> str:
    """Ensures a clean phone number with E.164 + and exactly one whatsapp: prefix."""
    cleaned = number.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned[len("whatsapp:"):]
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    return f"whatsapp:{cleaned}"


def split_whatsapp_message(body: str, max_chunk_size: int = 1400) -> list[str]:
    """
    Splits long messages to safely stay below Twilio's 1,600 character WhatsApp limit,
    accounting for multi-part header prefixes.
    """
    if len(body) <= max_chunk_size:
        return [body]

    lines = body.split("\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for line in lines:
        if len(line) > max_chunk_size:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            for i in range(0, len(line), max_chunk_size):
                chunks.append(line[i : i + max_chunk_size])
            continue

        if current_len + len(line) + 1 > max_chunk_size:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line) + 1
        else:
            current_chunk.append(line)
            current_len += len(line) + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    if len(chunks) > 1:
        return [
            f"*Part {idx}/{len(chunks)}*\n\n{chunk}"
            for idx, chunk in enumerate(chunks, start=1)
        ]
    return chunks


def send_email(to_address: str, subject: str, body: str):
    """Sends explanation via Gmail SMTP with detailed exception handling."""
    if not email_configured:
        return False, "Gmail credentials are not configured in secrets.toml."

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to_address

        secure_context = ssl.create_default_context()

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls(context=secure_context)
            server.ehlo()
            server.login(GMAIL_ADDRESS.strip(), GMAIL_APP_PASSWORD.replace(" ", ""))
            server.send_message(msg)
        return True, "Email sent successfully"

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Gmail authentication failed. Please verify your Gmail address and ensure "
            "you are using a valid 16-character App Password (not your standard Google account password). "
            "Also ensure 2-Step Verification is active on the account."
        )
    except smtplib.SMTPServerDisconnected:
        return False, (
            "Gmail server disconnected unexpectedly. This typically occurs when Gmail rejects the "
            "App Password / credentials during authentication or when network security interrupts the session."
        )
    except Exception as e:
        return False, f"SMTP error: {e}"


def send_whatsapp(to_number: str, body: str):
    """
    Splits message into parts, dispatches via Twilio WhatsApp API, and fetches
    the updated delivery status.
    """
    if not whatsapp_configured:
        return False, "Twilio credentials are not configured in secrets.toml."

    try:
        twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        from_formatted = normalize_whatsapp_number(TWILIO_WHATSAPP_NUMBER)
        to_formatted = normalize_whatsapp_number(to_number)

        message_parts = split_whatsapp_message(body)
        dispatched_messages = []

        for part in message_parts:
            message = twilio_client.messages.create(
                body=part,
                from_=from_formatted,
                to=to_formatted,
            )
            # Brief pause to allow Twilio's asynchronous pipeline to process/route the message
            time.sleep(1.5)
            # Query updated status
            fetched = twilio_client.messages(message.sid).fetch()

            dispatched_messages.append({
                "sid": fetched.sid,
                "status": fetched.status,
                "error_code": fetched.error_code,
                "error_message": fetched.error_message,
            })

        return True, dispatched_messages

    except Exception as error:
        return False, str(error)


# -----------------------------------------------------------------------------
# Streamlit User Interface
# -----------------------------------------------------------------------------
st.title("AI Doubt Clarifier")

if "explanation" not in st.session_state:
    st.session_state.explanation = ""

if "last_question" not in st.session_state:
    st.session_state.last_question = ""

question = st.text_input("Ask your question here")
if question:
    st.write("You asked:", question)

uploaded_image = st.file_uploader(
    "Upload an image to clarify your doubt", type=["png", "jpg", "jpeg"]
)

if uploaded_image:
    st.image(uploaded_image)

clarify_button = st.button("Clarify My Doubt")

if clarify_button:
    if not question and not uploaded_image:
        st.warning("Please enter a question or upload an image")
    else:
        parts = []
        if question:
            parts.append(question)
        if uploaded_image:
            image_bytes = uploaded_image.getvalue()
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=uploaded_image.type,
            )
            parts.append(image_part)
            if not question:
                parts.append("Explain the question or concept shown in this image clearly.")

        try:
            with st.spinner("Clarifying your doubt..."):
                response, used_model = generate_doubt_explanation(
                    gemini_client, parts, SYSTEM_PROMPT
                )

                if response.text and response.text.strip():
                    st.session_state.explanation = response.text
                    st.session_state.last_question = (
                        question if question else "Doubt uploaded as an image"
                    )
                else:
                    st.warning(
                        "Gemini did not return any explanation text. "
                        "This can occur if the prompt triggered safety filters. Please try rephrasing."
                    )
        except Exception as e:
            st.error(f"Gemini API Error: {e}")

# -----------------------------------------------------------------------------
# Explanation Display & Share Options
# -----------------------------------------------------------------------------
if st.session_state.explanation:
    st.subheader("Explanation")
    st.write(st.session_state.explanation)
    st.divider()

    st.subheader("Share Explanation")

    col1, col2 = st.columns(2)

    # Email Column
    with col1:
        st.markdown("#### 📧 Email")
        if not email_configured:
            st.info(
                "Email sharing is disabled because Gmail credentials (`GMAIL_ADDRESS`, "
                "`GMAIL_APP_PASSWORD`) are not configured in `.streamlit/secrets.toml`."
            )
        else:
            recipient_email = st.text_input(
                "Recipient Email Address",
                placeholder="student@example.com",
                key="email_input",
            )

            if st.button("Send Explanation to Email"):
                if not recipient_email.strip():
                    st.warning("Please enter the recipient's email address.")
                elif not is_valid_email(recipient_email):
                    st.warning("Please enter a valid email address (e.g., student@example.com).")
                else:
                    email_body = f"""AI Doubt Clarifier

Question:
{st.session_state.last_question}

Explanation:
{st.session_state.explanation}
"""
                    with st.spinner("Sending email..."):
                        success, message = send_email(
                            recipient_email.strip(),
                            "Your AI Doubt Clarifier Explanation",
                            email_body,
                        )

                    if success:
                        st.success("Explanation sent successfully! Check your inbox.")
                    else:
                        st.error(f"Email could not be sent: {message}")

    # WhatsApp Column
    with col2:
        st.markdown("#### 💬 WhatsApp")
        if not whatsapp_configured:
            st.info(
                "WhatsApp sharing is disabled because Twilio credentials (`TWILIO_ACCOUNT_SID`, "
                "`TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`) are not configured in `.streamlit/secrets.toml`."
            )
        else:
            whatsapp_number = st.text_input(
                "Recipient WhatsApp Number (with country code)",
                placeholder="+1234567890",
                key="whatsapp_input",
            )

            if st.button("Send Explanation to WhatsApp"):
                cleaned_number = whatsapp_number.strip().replace(" ", "").replace("-", "")
                if not cleaned_number:
                    st.warning("Please enter the recipient's WhatsApp number.")
                elif not is_valid_phone(cleaned_number):
                    st.warning(
                        "Please enter a valid phone number with country code (e.g., +1234567890)."
                    )
                else:
                    whatsapp_body = f"""*AI Doubt Clarifier*

*Question:*
{st.session_state.last_question}

*Explanation:*
{st.session_state.explanation}
"""
                    with st.spinner("Dispatching through WhatsApp & verifying status..."):
                        success, result = send_whatsapp(cleaned_number, whatsapp_body)

                    if success:
                        all_delivered = all(item["status"] in ("delivered", "read") for item in result)
                        any_failed = any(item["status"] in ("failed", "undelivered") for item in result)

                        summary_parts = [
                            f"Part {idx}: SID `{item['sid']}` — Status: **{item['status']}**"
                            + (f" (Error {item['error_code']})" if item['error_code'] else "")
                            for idx, item in enumerate(result, start=1)
                        ]
                        st.markdown("**Twilio Dispatch Status:**\n- " + "\n- ".join(summary_parts))

                        if all_delivered:
                            st.success("WhatsApp message confirmed delivered to recipient!")
                        elif any_failed:
                            failed_codes = [str(item["error_code"]) for item in result if item.get("error_code")]
                            if "63015" in failed_codes:
                                st.error(
                                    "Delivery Failed (Twilio Error 63015): The recipient has not opted into "
                                    "your Twilio WhatsApp Sandbox. The recipient must first send the sandbox "
                                    "keyword (e.g., `join <keyword>`) to your Twilio number."
                                )
                            else:
                                st.error("WhatsApp delivery failed. Check Twilio Console for error details.")
                        else:
                            st.warning(
                                "Message accepted and currently queued/sent by Twilio. "
                                "Final delivery status is pending carrier delivery confirmation."
                            )
                    else:
                        st.error(f"WhatsApp message could not be sent: {result}")