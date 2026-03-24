#!/usr/bin/env python3
"""
Google Sheets OAuth Setup — Run this ONCE to authorize.
Creates credentials that gspread uses for real sync.
"""
import json
import os
import sys

# Step 1: Check for service account key
SA_KEY_PATH = os.path.join(os.path.dirname(__file__), 'service_account.json')

if os.path.exists(SA_KEY_PATH):
    print(f"✅ Service account key found at {SA_KEY_PATH}")
    import gspread
    gc = gspread.service_account(filename=SA_KEY_PATH)
    sh = gc.open_by_key('1rkgRG95lxUgeplceekMY3Z_NZIBKxjTKNwLSpw04xgQ')
    print(f"✅ Connected to spreadsheet: {sh.title}")
    print(f"✅ Sheets: {[ws.title for ws in sh.worksheets()]}")
    print("\nGoogle Sheets sync is ready!")
    sys.exit(0)

print("""
╔══════════════════════════════════════════════════════════╗
║        Google Sheets Service Account Setup               ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Follow these steps (takes 2 minutes):                   ║
║                                                          ║
║  1. Go to: https://console.cloud.google.com              ║
║     Log in with: kipasdinding6969@gmail.com              ║
║                                                          ║
║  2. Create a new project (or use existing):              ║
║     → Click "Select a project" → "New Project"           ║
║     → Name: "TeamRecordsBot" → Create                    ║
║                                                          ║
║  3. Enable Google Sheets API:                            ║
║     → Go to: APIs & Services → Library                   ║
║     → Search "Google Sheets API" → Enable                ║
║                                                          ║
║  4. Create Service Account:                              ║
║     → Go to: APIs & Services → Credentials               ║
║     → Create Credentials → Service Account               ║
║     → Name: "team-records-bot"                           ║
║     → Role: Editor → Done                                ║
║                                                          ║
║  5. Download the key:                                    ║
║     → Click on the service account                       ║
║     → Keys tab → Add Key → Create new key → JSON         ║
║     → Download the file                                  ║
║                                                          ║
║  6. Place the file here:                                 ║
║     {sa_path}
║                                                          ║
║  7. Share the spreadsheet with the service account:      ║
║     → Open the downloaded JSON                           ║
║     → Copy the "client_email" value                      ║
║     → Open the Google Sheet → Share → paste email         ║
║     → Give "Editor" access                               ║
║                                                          ║
║  8. Run this script again to verify.                     ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""".format(sa_path=SA_KEY_PATH))
