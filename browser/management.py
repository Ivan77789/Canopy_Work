import asyncio
import random
import re

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
        self.debag_page = None
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

            # AdsPower иногда стартует некорректно (скрипт как бы подвисает), и помогает
            # только ручной клик "новая вкладка" — открываем её сами, чтобы не делать это руками
            self.debag_page = await self.context.new_page()

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

            # print("[Rabby] Кошелёк разблокирован.")
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
        await self.wait_for_cloudflare(self.page)

    @staticmethod
    async def wait_for_cloudflare(page, max_wait: int = 30) -> bool:
        """
        Ждёт, пока исчезнет промежуточная страница проверки Cloudflare
        ("Ray ID:" в футере — стабильный маркер вне зависимости от языка
        интерфейса). Обычно она резолвится сама за несколько секунд без
        участия пользователя, поэтому просто ждём с рандомной паузой.
        Возвращает True, если капчи не было или она исчезла, False — если
        провисела дольше max_wait секунд.
        """
        elapsed = 0.0
        while elapsed < max_wait:
            try:
                is_challenge = await page.locator("text=Ray ID:").count() > 0
            except Exception:
                is_challenge = False

            if not is_challenge:
                # небольшая пауза после исчезновения заглушки — дать странице
                # догрузить контент, прежде чем искать на ней элементы
                await asyncio.sleep(random.uniform(2, 4))
                return True

            # print("[Cloudflare] Обнаружена проверка безопасности, ждём...")
            pause = random.uniform(2, 4)
            await asyncio.sleep(pause)
            elapsed += pause

        print(f"[Cloudflare] Проверка безопасности не исчезла за {max_wait}с")
        return False

    async def close(self):
        """Корректно закрывает страницу/контекст/браузер/playwright и профиль в AdsPower."""
        if self.page and not self.page.is_closed():
            await self.page.close()
        if self.debag_page and not self.debag_page.is_closed():
            await self.debag_page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.profile_number is not None:
            close_browser(self.profile_number)

    async def parse_points(self, timeout: int = 20) -> int:
        """
        Парсит текущее количество Points на странице rewards: находит span с
        текстом "Points" и берёт значение из соседнего span перед ним
        (не привязываемся к CSS-классам, они могут смениться).
        Пока данные грузятся, там стоит плейсхолдер "--" — ждём, пока
        появится настоящее число.
        Возвращает 0, если не удалось найти/распарсить.
        """
        value_locator = self.page.locator(
            'xpath=//span[normalize-space(text())="Points"]/preceding-sibling::span[1]'
        ).first

        elapsed = 0.0
        text = ""
        while elapsed < timeout:
            try:
                text = (await value_locator.inner_text()).replace(",", "").strip()
            except Exception as e:
                print(f"[Points] Не удалось найти элемент с поинтами: {e}")
                return 0

            if text.isdigit():
                return int(text)

            await asyncio.sleep(1)
            elapsed += 1

        print(f"[Points] Не удалось распарсить количество поинтов, значение так и осталось '{text}'")
        return 0

    async def parse_rank(self, timeout: int = 20) -> str:
        """
        Строка текущего пользователя в лидерборде выделена характерным фоном
        (background-color: rgb(33, 38, 45)) в отличие от обычных строк без
        подсветки — используем это как основной признак, а не формат числа,
        потому что ранг может быть и "30000+", и просто "100", если
        пользователь попадёт в топ (там плюса уже не будет).
        Резервный вариант — искать по тексту вида "<число>+", если
        подсветку почему-то не нашли.
        Блок может лениво рендериться только после прокрутки страницы вниз
        (его нет в DOM, пока до него не доскроллить) — при отсутствии сразу
        скроллим наосліп.
        Возвращает "", если не удалось найти/распарсить.
        """
        highlighted_selector = '[style*="rgb(33, 38, 45)"] span.font-mono'
        locator = self.page.locator(highlighted_selector).first

        if await locator.count() == 0:
            await self.human.scroll_down_blind(self.page)

        try:
            await locator.wait_for(state="visible", timeout=timeout * 1000)
            text = await locator.inner_text()
            return text.strip()
        except Exception as e:
            print(f"[Points] Подсвеченная строка ранга не найдена ({e}), пробуем по формату '+'")

        fallback = self.page.get_by_text(re.compile(r"^\d+\+$")).first
        try:
            await fallback.wait_for(state="visible", timeout=5000)
            text = await fallback.inner_text()
            return text.strip()
        except Exception as e:
            print(f"[Points] Не удалось распарсить ранг: {e}")
            return ""

    async def isvisible_txt_button(self, button, txt, timeout: int = 5000):
        try:
            await button.wait_for(state="visible", timeout=timeout)
            button_text = await button.inner_text() #Получить текст кнопки
            return txt.lower() in button_text.lower()  # вернёт True/False
        except Exception as e:
            # print(f"[authorization] кнопка не появилась за {timeout // 1000}с: {e}")
            return False

    async def authorization(self, selector, txt, page):
        button = page.locator(selector).first
        is_visible = await self.isvisible_txt_button(button, txt)
        if is_visible:
            # Кнопка видна и содержит нужный текст – ничего не делаем
            return

        # Клик по кнопке Connect на сайте сразу открывает popup-окно расширения
        try:
            async with self.context.expect_page(timeout=15000) as popup_info:
                await self.human.scroll_to_selector(page=page, selector=selector)
                await self.human.click_on_selector(page=page, selector=selector)
            popup = await popup_info.value
        except Exception as e:
            print(f"[authorization] Popup не открылся после клика по '{selector}' ({e}) — пропускаем.")
            return

        await popup.bring_to_front()
        await popup.wait_for_load_state()

        # В popup выбираем конкретно Rabby Wallet из списка обнаруженных кошельков
        await self.human.scroll_to_selector(page=popup, selector='div.cursor-pointer:has-text("Rabby Wallet")')
        await self.human.click_on_selector(page=popup, selector='div.cursor-pointer:has-text("Rabby Wallet")')

        try:
            await popup.locator(
                "xpath=//span[contains(@class,'cursor-pointer') and text()='Ignore all']"
            ).click(timeout=3000)
        except Exception:
            pass

        # Connect может открыть окно подписи (Sign) отдельным popup, а может
        # просто сменить экран в этом же окне — проверяем оба варианта
        try:
            async with self.context.expect_page(timeout=5000) as new_popup_info:
                await popup.get_by_role("button", name="Connect").click()
            popup = await new_popup_info.value
            await popup.wait_for_load_state()
        except Exception:
            pass

        # Sign аналогично может открыть отдельное окно для Confirm
        try:
            async with self.context.expect_page(timeout=5000) as new_popup_info:
                await popup.get_by_text("Sign", exact=True).first.click()
            popup = await new_popup_info.value
            await popup.wait_for_load_state()
        except Exception:
            pass

        await popup.get_by_text("Confirm", exact=True).first.click()


        try:
            await popup.locator("button.ant-btn-primary:has-text('Add')").click(timeout=3000)
        except Exception as e:
            print(f"[authorization] шаг 'Add' пропущен: {e}")


            



