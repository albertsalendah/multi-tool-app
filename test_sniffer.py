import asyncio
import os
import shutil
from patchright.async_api import async_playwright

RESET_SESSION_EACH_RUN = True  # Keep True to test Turnstile auto-click on fresh sessions

async def solve_turnstile_if_present(page):
    """Detects Cloudflare Turnstile and clicks the checkbox inside its frame context."""
    try:
        # Locate the Turnstile iframe
        iframe = page.locator("iframe[src*='challenges.cloudflare.com']").first

        if await iframe.is_visible(timeout=5000):
            print("[!] Turnstile interactive challenge detected.")
            
            # CRITICAL: Wait for Turnstile's internal JS event listeners to bind
            print("[+] Waiting 2.5s for Cloudflare event listeners to initialize...")
            await page.wait_for_timeout(2500)

            # Strategy 1: Target internal DOM elements inside the cross-origin iframe
            cf_frame = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
            clicked = False
            
            for selector in ["#challenge-stage", "input[type='checkbox']", ".cb-i", "label"]:
                target = cf_frame.locator(selector).first
                if await target.is_visible(timeout=1000):
                    print(f"[+] Found element '{selector}' inside iframe. Dispatching click...")
                    await target.click()
                    clicked = True
                    break

            # Strategy 2: Fallback to physical mouse hardware click at exact checkbox coordinates
            if not clicked:
                box = await iframe.bounding_box()
                if box:
                    # Checkbox center is roughly 30px from left, centered vertically in widget
                    click_x = box["x"] + 30
                    click_y = box["y"] + (box["height"] / 2)
                    
                    print(f"[+] Falling back to physical mouse click at ({click_x:.1f}, {click_y:.1f})...")
                    await page.mouse.move(click_x, click_y, steps=5)
                    await page.wait_for_timeout(200)
                    await page.mouse.down()
                    await page.wait_for_timeout(100)
                    await page.mouse.up()

            print("[+] Waiting 6 seconds for Cloudflare verification...")
            await page.wait_for_timeout(6000)

    except Exception as e:
        print(f"[-] Turnstile check log: {e}")

async def get_stream(target_url: str):
    session_dir = "./patchright_session"
    
    if RESET_SESSION_EACH_RUN and os.path.exists(session_dir):
        print("[+] Wiping session directory for fresh Cloudflare challenge...")
        shutil.rmtree(session_dir)

    found_streams = []

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            headless=False,
            channel="chrome",
            args=["--no-sandbox"]  # Removed flags that trigger Chrome warning banners
        )

        page = context.pages[0] if context.pages else await context.new_page()

        async def handle_response(response):
            url = response.url
            if ".m3u8" in url and not url.endswith(".ts"):
                req = response.request
                found_streams.append({
                    "stream_url": url,
                    "referer": req.headers.get("referer", "https://megaplay.buzz/"),
                })
                print(f"\n🎯 [STREAM CAPTURED] {url}")

        context.on("response", handle_response)

        print(f"[+] Navigating to: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded")

        # Check and solve Turnstile
        await solve_turnstile_if_present(page)

        # Monitor network traffic
        print("[+] Monitoring network for video stream...")
        for _ in range(10):
            if found_streams:
                break
            await page.wait_for_timeout(1000)

        await context.close()

    return found_streams

if __name__ == "__main__":
    TARGET = "https://yomi.to/watch/135865/1"
    results = asyncio.run(get_stream(TARGET))
    
    if results:
        print(f"\nSuccess! Stream captured: {results[0]['stream_url']}")
    else:
        print("\n[-] Failed to capture stream.")