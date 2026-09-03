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
        
        # -> Click the 'Benign Grant' preset to load the benign grant scenario
        # Benign Grant button
        elem = page.get_by_role('button', name='Benign Grant', exact=True)
        await elem.click(timeout=10000)
        
        # -> Click the 'Benign Grant' preset to load the benign grant scenario
        # What the proposal says it will do, in the... text area
        elem = page.locator('[id="proposal-description"]')
        await elem.wait_for(state="visible", timeout=10000)
        await elem.fill("Pay 5000 USDC to 0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF. This intent claims the recipient is 0xDEADBEEF... which does not match the calldata recipient.")
        
        # -> Click the 'Benign Grant' preset to load the benign grant scenario
        # policy Run Multi-Validator Consensus Audit button
        elem = page.locator('[id="run-audit"]')
        await elem.click(timeout=10000)
        
        # -> Overwrite the Intent description to claim payment to 0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF (conflicting recipient) and click the 'Run Multi-Validator Consensus Audit' button.
        # What the proposal says it will do, in the... text area
        elem = page.locator('[id="proposal-description"]')
        await elem.wait_for(state="visible", timeout=10000)
        await elem.fill("Pay 5000 USDC to 0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF. This intent claims the recipient is 0xDEADBEEF which does not match the calldata recipient.")
        
        # -> Overwrite the Intent description to claim payment to 0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF (conflicting recipient) and click the 'Run Multi-Validator Consensus Audit' button.
        # policy Run Multi-Validator Consensus Audit button
        elem = page.locator('[id="run-audit"]')
        await elem.click(timeout=10000)
        
        # -> Click the 'Run Multi-Validator Consensus Audit' button to re-run the audit and trigger UI feedback.
        # policy Run Multi-Validator Consensus Audit button
        elem = page.locator('[id="run-audit"]')
        await elem.click(timeout=10000)
        
        # --> Assertions to verify final state
        
        # --> The app should flag identified discrepancies for the intent vs calldata mismatch but it did not.
        # Assert-outcome: failed
        # Assert: Expected the 'Nothing flagged' confirmation (no-issues check) to be absent so discrepancy indicators can appear.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[2]/div/div/span[1]").nth(0)).not_to_be_visible(timeout=15000), "Expected the 'Nothing flagged' confirmation (no-issues check) to be absent so discrepancy indicators can appear."
        
        # --> The final audit verdict should be non-passed when intent and calldata disagree, but the UI shows a PASSED verdict.
        # Assert-outcome: failed
        # Assert: Expected the 'Nothing flagged' confirmation to be absent so the audit verdict can be non-passed.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[2]/div/div/span[1]").nth(0)).not_to_be_visible(timeout=15000), "Expected the 'Nothing flagged' confirmation to be absent so the audit verdict can be non-passed."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    