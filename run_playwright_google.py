import asyncio
import time
import pyotp
import re
import os
from playwright.async_api import async_playwright, Playwright
from bit_api import openBrowser, closeBrowser
from create_window import get_browser_list, get_browser_info

# Helper function for automation logic
async def _automate_login_and_extract(playwright: Playwright, browser_id: str, account_info: dict, ws_endpoint: str):
    chromium = playwright.chromium
    try:
        browser = await chromium.connect_over_cdp(ws_endpoint)
        default_context = browser.contexts[0]
        page = default_context.pages[0] if default_context.pages else await default_context.new_page()

        print("Proxy warmup: Waiting for 2 seconds...")
        await asyncio.sleep(2)

        print('Navigating to accounts.google.com...')
        # Retry logic for poor network
        max_retries = 3
        
        # Check if we need to login or if we are already logged in
        # We try to go to accounts.google.com first.
        try:
            await page.goto('https://accounts.google.com', timeout=60000)
        except Exception as e:
            print(f"Initial navigation failed: {e}")

        # 1. Enter Email (if input exists)
        email = account_info.get('email')
        
        try:
             # Check if email input exists
             email_input = await page.wait_for_selector('input[type="email"]', timeout=5000)
             if email_input:
                 print(f"Entering email: {email}")
                 await email_input.fill(email)
                 await page.click('#identifierNext >> button')
                 
                 # 2. Enter Password
                 print("Waiting for password input...")
                 await page.wait_for_selector('input[type="password"]', state='visible')
                 password = account_info.get('password')
                 print("Entering password...")
                 await page.fill('input[type="password"]', password)
                 await page.click('#passwordNext >> button')

                 # 3. Handle 2FA (TOTP)
                 print("Waiting for 2FA input...")
                 try:
                      totp_input = await page.wait_for_selector('input[name="totpPin"], input[id="totpPin"], input[type="tel"]', timeout=10000)
                      if totp_input:
                          secret = account_info.get('secret')
                          if secret:
                              s = secret.replace(" ", "").strip()
                              totp = pyotp.TOTP(s)
                              code = totp.now()
                              print(f"Generating 2FA code: {code}")
                              await totp_input.fill(code)
                              await page.click('#totpNext >> button')
                          else:
                              print("2FA secret not found in account info!")
                 except Exception as e:
                     print(f"2FA step exception (maybe skipped or different challenge): {e}")

        except Exception as e:
             print(f"Login flow might be skipped or failed (maybe already logged in): {e}")

        # Wait briefly after login attempt
        await asyncio.sleep(3)

        # 4. Navigate to Google One AI page
        target_url = "https://one.google.com/ai-student?g1_landing_page=75&utm_source=antigravity&utm_campaign=argon_limit_reached"
        
        print("Opening a new page for target URL...")
        # Open new page first to ensure browser doesn't close
        new_page = await default_context.new_page()
        page = new_page # Switch to new page
        
        print(f"Navigating to {target_url}...")
        
        nav_success = False
        for attempt in range(max_retries):
            try:
                await page.goto(target_url, timeout=60000)
                print("Target navigation successful.")
                nav_success = True
                break
            except Exception as e:
                print(f"Target navigation failed (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    print("Retrying in 5 seconds...")
                    await asyncio.sleep(5)
        
        if not nav_success:
            print("Failed to navigate to target URL after retries.")
            return False

        # 5. Extract "Verify eligibility" link or check for non-eligibility
        print("Checking for eligibility...")
        
        found_link = False
        is_invalid = False
        
        # Phrases indicating the offer is not available in various languages
        not_available_phrases = [
            "This offer is not available",
            "Ưu đãi này hiện không dùng được", # Vietnamese
            "Esta oferta no está disponible", # Spanish
            "Cette offre n'est pas disponible", # French
            "Esta oferta não está disponível", # Portuguese
            "Tawaran ini tidak tersedia", # Indonesian
            "此优惠目前不可用", # Chinese Simplified
            "這項優惠目前無法使用", # Chinese Traditional
            "Oferta niedostępna", # Polish
            "Oferta nu este disponibilă", # Romanian
            "Die Aktion ist nicht verfügbar", # German
            "Il'offerta non è disponibile", # Italian
            "Această ofertă nu este disponibilă", 
            "Ez az ajánlat nem áll rendelkezésre", # Hungarian
            "Tato nabídka není k dispozici", # Czech
            "Bu teklif kullanılamıyor" # Turkish
        ]
        
        try:
            start_time = time.time()
            # Polling loop for 6 seconds (User requested strict 6s timeout)
            print("Checking for eligibility (max 6s)...")
            
            while time.time() - start_time < 6:
                # Check for Verify Link First
                if await page.locator('a[aria-label="Verify eligibility"]').is_visible():
                    found_link = True
                    break

                # Check for "This offer is not available" phrases (Optional fast fail)
                for phrase in not_available_phrases:
                    # Use get_by_text for exact or partial matches
                    if await page.locator(f'text="{phrase}"').is_visible():
                        print(f"Detected invalid state with phrase: {phrase}")
                        is_invalid = True
                        break
                
                if is_invalid:
                    break
                
                await asyncio.sleep(0.5) # Check more frequently

            if found_link:
                # Target the <a> tag directly using aria-label
                link = page.locator('a[aria-label="Verify eligibility"]')
                print("Found 'Verify eligibility' link element.")
                
                # Get href attribute
                href = await link.get_attribute("href")

                if href:
                    print(f"Extracted Link: {href}")
                    line = f"{href}----{email}"
                    
                    # Save to file
                    save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sheerIDlink.txt")
                    with open(save_path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                    print(f"Saved link to {save_path}")
                    return True
                else:
                    print("Link element found but has no href.")
                    # fallback to invalid if link has no href? Or just return False.
                    # Let's return False for now, but maybe user wants to see this.
                    await page.screenshot(path="debug_link_extraction_error.png")
            else:
                # Timeout OR Explicit Invalid -> Both treated as Invalid Account
                reason = "Offer not available" if is_invalid else "Timeout (6s allowed)"
                print(f"Account marked as NOT eligible: {reason}")
                
                save_path_invalid = os.path.join(os.path.dirname(os.path.abspath(__file__)), "无资格号.txt")
                with open(save_path_invalid, "a", encoding="utf-8") as f:
                    f.write(f"{email}\n")
                print(f"Saved to {save_path_invalid}")
                
                if not is_invalid:
                     await page.screenshot(path="debug_eligibility_timeout.png")
                
                return False 

        except Exception as e:
            print(f"Failed to extract check eligibility: {e}")
            await page.screenshot(path="debug_eligibility_error.png")

        # Brief wait before closing
        await asyncio.sleep(2)
        
    except Exception as e:
        print(f"An error occurred in automation: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return False

async def _async_process_wrapper(browser_id, account_info, ws_endpoint):
    async with async_playwright() as playwright:
        return await _automate_login_and_extract(playwright, browser_id, account_info, ws_endpoint)

def process_browser(browser_id):
    """
    Synchronous entry point for processing a single browser.
    Returns (success, message)
    """
    print(f"Fetching info for browser ID: {browser_id}")
    
    target_browser = get_browser_info(browser_id)
    if not target_browser:
        # Fallback search
        print(f"Direct info fetch failed for {browser_id}, attempting list search...")
        browsers = get_browser_list(page=0, pageSize=1000)
        for b in browsers:
             if b.get('id') == browser_id:
                 target_browser = b
                 break
    
    if not target_browser:
        return False, f"Browser {browser_id} not found."

    account_info = {}
    remark = target_browser.get('remark', '')
    parts = remark.split('----')
    if len(parts) >= 4:
        account_info = {
            'email': parts[0].strip(),
            'password': parts[1].strip(),
            'backup': parts[2].strip(),
            'secret': parts[3].strip()
        }
    else:
        # Even if password/secret missing, maybe we are already logged in?
        # But if email is missing, it's hard to log (for the file).
        # We'll try to get email from remark anyway if partial
        if len(parts) >= 1:
             account_info['email'] = parts[0].strip()
        else:
             account_info['email'] = 'unknown'
        print("Remark format invalid or empty, logging in might fail if credentials needed.")

    print(f"Opening browser {browser_id}...")
    res = openBrowser(browser_id)
    if not res or not res.get('success', False):
        return False, f"Failed to open browser: {res}"

    ws_endpoint = res.get('data', {}).get('ws')
    if not ws_endpoint:
        closeBrowser(browser_id)
        return False, "No WebSocket endpoint returned."

    try:
        # Run automation
        success = asyncio.run(_async_process_wrapper(browser_id, account_info, ws_endpoint))
        if success:
            return True, "Successfully extracted and saved link."
        else:
            return False, "Automation finished but link not found or error occurred."
    finally:
        print(f"Closing browser {browser_id}...")
        closeBrowser(browser_id)

if __name__ == "__main__":
    # Test with specific ID
    target_id = "62b1596a5e064629a7126b11feed7c89"
    success, msg = process_browser(target_id)
    print(f"Result: {success} - {msg}")
