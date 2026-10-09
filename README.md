# AI Doubt Clarifier 🎓

An interactive AI-powered tutor and mentor built with **Streamlit** and **Google Gemini Multimodal API**. It allows students and developers to ask technical questions, upload screenshots of code, errors, or diagrams, and receive structured, step-by-step explanations. Explanations can be easily shared via **Email (Gmail SMTP)** or **WhatsApp (Twilio API)**.

---

## 🌟 Key Features

1. **Multimodal Inputs:**
   - Ask text-based programming questions.
   - Upload images (code snippets, error logs, architecture diagrams, whiteboard notes).
   - Combine text and images for comprehensive context.

2. **Pedagogical AI Mentor:**
   - Powered by Gemini using custom system instructions defined in `prompts.py`.
   - Focuses on clear explanations, identifies exact mistakes in code, gives hints before full solutions, and concludes with a concise key takeaway.

3. **Intelligent Model Fallback:**
   - Primary model: `gemini-3.8-flash` for high performance and up-to-date reasoning.
   - Automatic fallback: `gemini-3.5-flash-lite` if the primary model encounters temporary capacity spikes or server unavailability.
   - Permanent authentication and client errors are caught and surfaced without redundant retries.

4. **Multi-Channel Sharing:**
   - **Gmail SMTP:** Send formatted explanations directly to any email address.
   - **Twilio WhatsApp:** Dispatch explanations directly to WhatsApp.
   - **Smart Message Splitting:** Automatically splits long explanations into clean parts (staying strictly under Twilio's 1,600-character limit per message).
   - **Live Delivery Verification:** Queries Twilio's message status API to differentiate between queued requests, delivered messages, and common Sandbox issues (e.g., Error 63015).

5. **Graceful Modular Architecture:**
   - Only `GEMINI_API_KEY` is required to run the core app.
   - Email and WhatsApp integrations are optional—if their credentials are not configured, the rest of the application remains fully functional.

---

## 📁 Project Structure

```text
ai-doubt-clarifier/
├── .streamlit/
│   └── secrets.toml          # API keys & configuration (Ignored by Git)
├── app.py                    # Main Streamlit application
├── prompts.py                # System instructions & tutor persona
├── requirements.txt          # Python dependencies
├── .gitignore                # Git ignore rules (protects secrets & venv)
└── README.md                 # Project documentation
```

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/<your-username>/ai-doubt-clarifier.git
cd ai-doubt-clarifier
```

### 2. Set Up a Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration (`secrets.toml`)

Create a `.streamlit/secrets.toml` file in the root directory:

```toml
# =============================================================================
# Core AI Configuration (Required)
# =============================================================================
GEMINI_API_KEY = "your-google-gemini-api-key"

# =============================================================================
# Gmail SMTP Configuration (Optional - for Email sharing)
# =============================================================================
GMAIL_ADDRESS = "your-email@gmail.com"
GMAIL_APP_PASSWORD = "abcd efgh ijkl mnop"   # 16-character App Password

# =============================================================================
# Twilio WhatsApp Configuration (Optional - for WhatsApp sharing)
# =============================================================================
TWILIO_ACCOUNT_SID = "your-twilio-account-sid"
TWILIO_AUTH_TOKEN = "your-twilio-auth-token"
TWILIO_WHATSAPP_NUMBER = "+14155238886"       # Twilio Sandbox number
```

> **Security Note:** `.streamlit/secrets.toml` is included in `.gitignore` and must **never** be committed to version control.

---

## 🔑 External Service Setup Guide

### Google Gemini API Key
1. Visit [Google AI Studio](https://aistudio.google.com/).
2. Create or select a project and generate an API Key.
3. Paste the key into `GEMINI_API_KEY`.

### Gmail SMTP (App Password)
1. Go to your [Google Account Security Settings](https://myaccount.google.com/security).
2. Enable **2-Step Verification**.
3. Under Security, search for **App Passwords**.
4. Generate a new App Password for "Mail" / "Other" and copy the 16-character code into `GMAIL_APP_PASSWORD`.
5. Note: Your regular Google login password will not work for SMTP.

### Twilio WhatsApp Sandbox
1. Create a free account on [Twilio](https://www.twilio.com/).
2. Navigate to **Messaging > Try it out > Send a WhatsApp message**.
3. Follow the instructions on the screen: send the designated `join <keyword>` message from your phone's WhatsApp to the Twilio WhatsApp Sandbox number (`+1 415 523 8886`).
4. Once connected, your phone can receive explanations dispatched from the app.

---

## 💻 Running Locally

Launch the application with Streamlit:

```bash
streamlit run app.py
```

The app will open automatically in your browser at `http://localhost:8501`.

---

## ☁️ Deployment (Streamlit Community Cloud)

1. Push your repository to GitHub (ensure `.streamlit/secrets.toml` is not tracked).
2. Sign in to [share.streamlit.io](https://share.streamlit.io/).
3. Connect your repository and select `app.py` as the main entry point.
4. In the deployment settings, open **Advanced settings > Secrets** and paste your `.streamlit/secrets.toml` values.
5. Click **Deploy**.

---

## 🛠️ Tech Stack

- **Frontend / Framework:** [Streamlit](https://streamlit.io/)
- **LLM & Vision:** [Google GenAI SDK](https://github.com/google-gemini/deprecations) (`gemini-3.8-flash` & `gemini-3.5-flash-lite`)
- **Messaging:** [Twilio Python SDK](https://github.com/twilio/twilio-python)
- **Email Protocol:** Python `smtplib` + `email.mime`
- **Image Processing:** [Pillow](https://python-pillow.org/)
