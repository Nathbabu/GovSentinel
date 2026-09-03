import asyncio
import re
from playwright import async_api
from playwright.async_api import expect

async def run_test():
    pw = None
    browser = None
    context = None

    try:
        # Start a Playwright session in asynchronous mode
        pw = await async_api.async_playwright().start()

        # Launch a Chromium browser in headless mode with custom arguments
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--window-size=1280,720",
                "--disable-dev-shm-usage",
                "--ipc=host",
                "--single-process"
            ],
        )

        # Create a new browser context (like an incognito window)
        context = await browser.new_context()
        # Wider default timeout to match the agent's DOM-stability budget;
        # auto-waiting Playwright APIs (expect, locator.wait_for) inherit this.
        context.set_default_timeout(15000)

        # Open a new page in the browser context
        page = await context.new_page()

        # Interact with the page elements to simulate user flow
        # -> navigate
        await page.goto("http://localhost:8000/")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        
        # -> Click the 'Stealth Hijack' preset button.
        # Stealth Hijack button
        elem = page.get_by_role('button', name='Stealth Hijack', exact=True)
        await elem.click(timeout=10000)
        
        # -> Verify the Proposal title reads 'Adjust quorum parameter to 12 percent' and confirm the previous benign title 'Q3 developer grant for the indexer rewrite' (and other benign values) are not present on the page.
        # [internal] extract_content: 
        
        # --> Assertions to verify final state
        
        # --> Switching to the Stealth Hijack preset updated the proposal inputs: the title and calldata reflect the Stealth Hijack scenario.
        # Assert-outcome: passed
        # Assert: The proposal title matches the Stealth Hijack scenario.
        await expect(page.locator("xpath=/html/body/main/div/section[1]/div/form/div[1]/input").nth(0)).to_have_value("Adjust quorum parameter to 12 percent", timeout=15000), "The proposal title matches the Stealth Hijack scenario."
        # Assert-outcome: passed
        # Assert: The proposal calldata matches the Stealth Hijack scenario.
        await expect(page.locator("xpath=/html/body/main/div/section[1]/div/form/div[6]/textarea").nth(0)).to_have_value("0xf2fde38b0000000000000000000000003c44cdddb6a900fa2b585dd299e03d12fa4293bc", timeout=15000), "The proposal calldata matches the Stealth Hijack scenario."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    