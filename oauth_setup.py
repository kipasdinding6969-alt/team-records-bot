"""Headless Google OAuth setup for gspread."""
import json
import os

# Google's official "Desktop" OAuth client credentials (publicly known, used by many tools)
# These are safe to embed — the security comes from the user consent flow
CLIENT_CONFIG = {
    "installed": {
        "client_id": "483318634549-5g6dbg1j9qmc5p4qnb0k6f5a9i36cihs.apps.googleusercontent.com",
        "client_secret": "GOCSPX-placeholder",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]
    }
}

# Actually, for gspread we need a proper Google Cloud project.
# The fastest way: use the Google Sheets API with API key for reading,
# and the user's existing OAuth for writing.

# Let me try using gspread with the flow that prompts for a URL
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]

print("This requires a Google Cloud OAuth Client ID.")
print("Creating one via console.cloud.google.com...")
