# setup_chatgpt.py
import os
from playwright.sync_api import sync_playwright

profile_dir = os.path.abspath("./chatgpt_profile")
print(f"Opening browser with profile in: {profile_dir}")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://chatgpt.com")

    print("\n" + "="*60)
    print("ACTION REQUIRED:")
    print("1. Log in to your OpenAI account in the browser window.")
    print("2. Ensure you can see the ChatGPT chat bar.")
    print("3. Return here and press ENTER when done.")
    print("="*60 + "\n")

    input("Press ENTER once you have logged in...")
    context.close()
    print("Session saved successfully!")
