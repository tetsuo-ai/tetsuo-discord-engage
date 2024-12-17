import asyncio
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv

async def main():
    # Load environment variables
    load_dotenv()
    username = os.getenv('X_USERNAME')
    password = os.getenv('X_PASSWORD')
    
    if not username or not password:
        print("Please set X_USERNAME and X_PASSWORD in .env file")
        return

    async with async_playwright() as p:
        # Launch browser with window
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        try:
            page = await context.new_page()
            
            # Step 1: Go to login page
            print("Loading login page...")
            await page.goto('https://twitter.com/login')
            await asyncio.sleep(2)

            # Step 2: Enter username/email
            print("Entering username...")
            username_input = await page.wait_for_selector('input[autocomplete="username"]')
            await username_input.fill(username)
            await username_input.press('Enter')
            
            # Check for unusual activity screen
            print("Checking for security verification...")
            try:
                # Look for the unusual activity message
                unusual_activity = await page.wait_for_selector('text=unusual login activity', timeout=3000)
                if unusual_activity:
                    print("Detected unusual activity check, entering handle...")
                    handle = os.getenv('X_HANDLE')
                    if not handle:
                        print("X_HANDLE not set in .env!")
                        return
                    handle_input = await page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]')
                    await handle_input.fill(handle)
                    await handle_input.press('Enter')
            except:
                print("No security verification needed, proceeding...")

            # Step 3: Enter password
            print("Waiting for password field...")
            password_input = await page.wait_for_selector('input[name="password"]', timeout=5000)
            print("Entering password...")
            await password_input.fill(password)
            await password_input.press('Enter')

            # Wait for login to complete
            print("Waiting for login to complete...")
            await asyncio.sleep(3)
            
            print("Going to search...")
            await page.goto('https://twitter.com/search?q=$TETSUO&src=typed_query&f=live')
            
            print("Monitoring for new tweets...")
            # Keep script running to monitor
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nPress Ctrl+C to exit")
            await asyncio.sleep(999999)

if __name__ == "__main__":
    asyncio.run(main())