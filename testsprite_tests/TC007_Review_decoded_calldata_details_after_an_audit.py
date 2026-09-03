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
        
        # -> Click the 'Unapproved Target' preset and then click the 'Run Multi-Validator Consensus Audit' button.
        # Unapproved Target button
        elem = page.get_by_role('button', name='Unapproved Target', exact=True)
        await elem.click(timeout=10000)
        
        # -> Click the 'Unapproved Target' preset and then click the 'Run Multi-Validator Consensus Audit' button.
        # policy Run Multi-Validator Consensus Audit button
        elem = page.locator('[id="run-audit"]')
        await elem.click(timeout=10000)
        
        # --> Assertions to verify final state
        
        # --> A Decoded calldata section is visible and the decoded method is shown.
        # Assert-outcome: passed
        # Assert: Decoded calldata section label is 'data_object'.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/h3/span").nth(0)).to_have_text("data_object", timeout=15000), "Decoded calldata section label is 'data_object'."
        
        # --> The decoded recipient is shown as 0x70997970c51812dc3a010c7d01b50e0d17dc79c8.
        # Assert-outcome: passed
        # Assert: Decoded recipient equals the expected address.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/table/tbody/tr[2]/td").nth(0)).to_have_text("0x70997970c51812dc3a010c7d01b50e0d17dc79c8", timeout=15000), "Decoded recipient equals the expected address."
        
        # --> The decoded amount is 750 and the whitelist status element is displayed.
        # Assert-outcome: passed
        # Assert: Decoded amount equals 750.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/table/tbody/tr[3]/td").nth(0)).to_have_text("750", timeout=15000), "Decoded amount equals 750."
        await page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/table/tbody/tr[4]/td").nth(0).scroll_into_view_if_needed()
        # Assert-outcome: passed
        # Assert: Whitelist status element is visible.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/table/tbody/tr[4]/td").nth(0)).to_be_visible(timeout=15000), "Whitelist status element is visible."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    