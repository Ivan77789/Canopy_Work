from playwright.async_api import async_playwright

from browser.adspawer_api_utils import start_browser, close_browser


class ManagerBrowserContext:
    UNLOCK_TIMEOUT = 10000

    def __init__(self, human):
        self.profile_number = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.human = human

    async def start(self, profile_number) -> bool:
        """
        Запускает профиль AdsPower и подключается к нему через Playwright.
        Возвращает True при успехе.
        """
        self.profile_number = profile_number

        try:
            puppeteer_ws = start_browser(profile_number)
            if not puppeteer_ws:
                print(f"Failed to launch browser for profile {profile_number}.")
                return False

            self.playwright = await async_playwright().start()

            self.browser = await self.playwright.chromium.connect_over_cdp(puppeteer_ws)

            self.context = (
                self.browser.contexts[0]
                if self.browser.contexts
                else await self.browser.new_context()
            )

            await self.context.add_init_script("""
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

            self.page = await self.context.new_page()
            return True
        except Exception as e:
            print(f"error for profile {profile_number}: {e}")
            await self.close()
            return False

    async def _get_rabby_extension_id(self) -> str | None:
        """
        Расширения (MV3) читаются со страницы chrome://extensions/, а не через
        context.service_workers — их воркер Chrome усыпляет через ~30с простоя,
        и к моменту проверки он может уже не значиться среди активных.
        """
        page = await self.context.new_page()
        try:
            await page.goto("chrome://extensions/", timeout=self.UNLOCK_TIMEOUT)
            return await page.evaluate("""
                () => {
                    const manager = document.querySelector('extensions-manager');
                    const list = manager.shadowRoot.querySelector('extensions-item-list');
                    const items = list.shadowRoot.querySelectorAll('extensions-item');
                    for (const item of items) {
                        const name = item.shadowRoot.querySelector('#name')?.textContent || '';
                        if (name.toLowerCase().includes('rabby')) {
                            return item.id;
                        }
                    }
                    return null;
                }
            """)
        except Exception:
            return None
        finally:
            await page.close()

    async def unlock_wallet(self, password: str) -> bool:
        """
        Открывает popup Rabby Wallet и разблокирует его паролем.
        Возвращает True, если кошелёк разблокирован (или уже был разблокирован).
        """
        extension_id = await self._get_rabby_extension_id()
        if not extension_id:
            print("[Rabby] Не удалось найти расширение кошелька в профиле.")
            return False

        page = await self.context.new_page()
        try:
            await page.goto(f"chrome-extension://{extension_id}/popup.html", timeout=self.UNLOCK_TIMEOUT)

            password_input = page.locator('input[type="password"]')
            try:
                await password_input.wait_for(state="visible", timeout=5000)
            except Exception:
                print("[Rabby] Кошелёк уже разблокирован.")
                return True

            await password_input.fill(password)
            await page.locator('button:has-text("Unlock")').click()
            await page.wait_for_timeout(1500)

            print("[Rabby] Кошелёк разблокирован.")
            return True
        except Exception as e:
            print(f"[Rabby] Ошибка при разблокировке: {e}")
            return False
        finally:
            await page.close()

    async def goto(self, url: str, timeout: int = 15000):
        """Переход по URL с одним повтором, если навигацию оборвало (например net::ERR_ABORTED)."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except Exception as e:
            print(f"Профиль {self.profile_number}: навигация прервана ({e}), повтор...")
            await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)

    async def close(self):
        """Корректно закрывает страницу/контекст/браузер/playwright и профиль в AdsPower."""
        if self.page and not self.page.is_closed():
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.profile_number is not None:
            close_browser(self.profile_number)

    async def isvisible_txt_button(self, button, txt):
        try:
            await button.wait_for(state="visible", timeout=5000)
            button_text = await button.inner_text()
            return txt in button_text  # вернёт True/False
        except Exception as e:
            print(f"[authorization] кнопка не появилась за 5с: {e}")
            return False

    async def authorization(self, selector, txt, page):
        button = page.locator(selector).first
        is_visible = await self.isvisible_txt_button(button, txt)
        if is_visible:
            # Кнопка видна и содержит нужный текст – ничего не делаем
            return
        else:
            # Иначе кликаем
            await self.human.click_on_selector(page=page, selector=selector)

