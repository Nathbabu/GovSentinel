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
        
        # -> Click the 'Benign Grant' preset to load the benign grant scenario and update the proposal fields.
        # Benign Grant button
        elem = page.get_by_role('button', name='Benign Grant', exact=True)
        await elem.click(timeout=10000)
        
        # -> Click the 'Run Multi-Validator Consensus Audit' button to run the multi-validator audit and update the Audit result panel.
        # policy Run Multi-Validator Consensus Audit button
        elem = page.locator('[id="run-audit"]')
        await elem.click(timeout=10000)
        
        # --> Assertions to verify final state
        
        # --> Proposal fields are populated with the benign grant scenario details (title, description, target, recipient, amount, calldata).
        # Assert-outcome: passed
        # Assert: Title field is populated with the scenario title.
        await expect(page.locator("xpath=/html/body/main/div/section[1]/div/form/div[1]/input").nth(0)).to_have_value("Q3 developer grant for the indexer rewrite", timeout=15000), "Title field is populated with the scenario title."
        # Assert-outcome: passed
        # Assert: Description field is populated with the scenario description.
        await expect(page.locator("xpath=/html/body/main/div/section[1]/div/form/div[2]/textarea").nth(0)).to_have_value("Pay 5000 USDC to the contributor who rewrote the subgraph indexer. Scope and deliverables were approved in forum thread 214.", timeout=15000), "Description field is populated with the scenario description."
        
        # --> Decoded calldata results and whitelist status are shown in the audit panel (method, amount, approved target).
        # Assert-outcome: passed
        # Assert: Decoded calldata method is displayed in the audit results.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/table/tbody/tr[1]").nth(0)).to_contain_text("transfer(address,uint256)", timeout=15000), "Decoded calldata method is displayed in the audit results."
        # Assert-outcome: passed
        # Assert: Decoded calldata amount is displayed in the audit results.
        await expect(page.locator("xpath=/html/body/main/div/section[2]/div/div[2]/section[1]/table/tbody/tr[3]/td").nth(0)).to_have_text("5,000", timeout=15000), "Decoded calldata amount is displayed in the audit results."
        await asyncio.sleep(5)

    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()

asyncio.run(run_test())
    