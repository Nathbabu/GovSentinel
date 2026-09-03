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
        
        # -> Enter a malformed value into the 'Raw calldata hex' field and click the 'Run Multi-Validator Consensus Audit' button.
        # 0xa9059cbbâ€¦ text area
        elem = page.locator('[id="calldata-hex"]')
        await elem.wait_for(state="visible", timeout=10000)
        await elem.fill("0x12345G")
        
        # -> Enter a malformed value into the 'Raw calldata hex' field and click the 'Run Multi-Validator Consensus Audit' button.
        # policy Run Multi-Validator Consensus Audit button
        elem = page.locator('[id="run-audit"]')
        await elem.click(timeout=10000)
        
        # --> Assertions to verify final state
        
        # --> Malformed calldata '0x12345G' is rejected: an inline validation says it does not decode and the audit flagged discrepancies.
        # Assert-outcome: passed
        # Assert: The Raw calldata hex field contains the malformed input '0x12345G'.
        await expect(page.locator("xpath=/html/body/main/div/section[1]/div/form/div[6]/textarea").nth(0)).to_have_value("0x12345G", timeout=15000), "The Raw calldata hex field contains the malformed input '0x12345G'."
        # Assert-outcome: passed
        # Assert: The page lists 3 identified discrepancies explaining the rejection.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[2]/h3/span[2]").nth(0)).to_have_text("3", timeout=15000), "The page lists 3 identified discrepancies explaining the rejection."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    