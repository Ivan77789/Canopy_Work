import random

from playwright.async_api import async_playwright

from browser.adspawer_api_utils import start_browser, close_browser

################################################################################

DISPOSABLE = False


################################################################################


def load_profiles(file_name="profiles.txt"):
    with open(file_name, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


async def activity(profile_number):
    playwright = None
    browser = None
    context = None
    page = None

    try:

        puppeteer_ws = start_browser(profile_number)

        if not puppeteer_ws:
            print(f"Failed to launch browser for profile {profile_number}.")
            return None, None, None, None

            # async with async_playwright() as playwright:
            # НЕ використовуємо async with, щоб playwright не закривався
        playwright = await async_playwright().start()

        browser = await playwright.chromium.connect_over_cdp(
            puppeteer_ws,
            slow_mo=random.randint(2000, 3000),
        )

        context = (
            browser.contexts[0]
            if browser.contexts
            else await browser.new_context()
        )

        await context.add_init_script("""
                Object.defineProperty(window, 'navigator', {
                    value: new Proxy(navigator, {
                        has: (target, key) => key === 'webdriver' ? false : key in target,
                        get: (target, key) =>
                            key === 'webdriver'
                                ? undefined
                                : typeof target[key] === 'function'
                                    ? target[key].bind(target)
                                    : target[key]
                    })
                });
            """)

        page = context.pages[0] if context.pages else await context.new_page()

        return page, playwright, browser, context
    except Exception as e:
        print(f"error for profile {profile_number}: {e}")
        # При помилці закриваємо все
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        return None, None, None, None


async def close_browser_connection(page, playwright, browser, context, profile_number):
    """
    Коректне закриття браузера та звільнення ресурсів
    """
    print(f"Closing browser for profile {profile_number}...")

    # Закриваємо сторінку
    if page and not page.is_closed():
        await page.close()

    # Закриваємо контекст
    if context:
        await context.close()

    # Закриваємо браузер
    if browser:
        await browser.close()

    # Зупиняємо playwright
    if playwright:
        await playwright.stop()

    # Закриваємо профіль в AdsPower
    close_browser(profile_number)

    print(f"Browser closed for profile {profile_number}")