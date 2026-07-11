import asyncio
import os
import random
import tempfile

import requests
from PIL import Image

from config import OPENAI_API_KEY
from name_chaine import NAME_SHAIN


class QuestsCanopy:
    def __init__(self, human, manager):
        self.human = human
        self.manager = manager

    # ==================================================================
    # Публичные задачи (вызываются из runer.py)
    # ==================================================================

    # launch_virtual_hain() — задача "запустить новый чейн": открывает свою
    # вкладку и гарантированно закрывает её в finally, что бы ни случилось внутри
    async def launch_virtual_hain(self, twitter_handle: str = ""):
        page = await self.manager.context.new_page()
        try:
            await self._launch_virtual_hain_body(page, twitter_handle)
        finally:
            await page.close()

    async def _launch_virtual_hain_body(self, page, twitter_handle: str = ""):
        # открываем визард запуска чейна
        await page.goto(
            "https://testnet.app.canopynetwork.org/launchpad/",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        # ждём, пока пройдёт проверка Cloudflare, прежде чем искать элементы на странице
        await self.manager.wait_for_cloudflare(page)
        await asyncio.sleep(random.uniform(3, 6))

        # Случайные значения по умолчанию — на случай, если шаг "Main Info" уже
        # пройден и пропущен (тогда fill_main_info не выполнится и не переприсвоит их),
        # а chain_name всё равно используется в описании на шаге "Branding & Media".
        chain_name = self._get_random_chain_name()
        ticker = self._get_random_ticker()

        # ---- Ниже — по одной функции-заполнителю на каждый шаг визарда запуска чейна ----

        # Шаг 1 "Language": выбираем язык проекта (Python) и жмём Continue
        async def fill_language():
            await self.human.scroll_to_selector(page=page, selector='img[alt="python logo"]')
            await self.human.click_on_selector(page=page, selector='img[alt="python logo"]')
            await self.human.scroll_to_selector(page=page, selector='button:has-text("Continue")')
            await self.human.click_on_selector(page=page, selector='button:has-text("Continue")')

        # Шаг 2 "Connect Repo": авторизуем GitHub (если ещё не авторизован),
        # ищем и подключаем репозиторий "canopy"
        async def fill_connect_repo():
            # if await page.locator('button:has-text("Authorize GitHub")').count() > 0:
            #     await self.human.scroll_to_selector(page=page, selector='button:has-text("Authorize GitHub")')
            #     await self.human.click_on_selector(page=page, selector='button:has-text("Authorize GitHub")')
            # else:
            #     print("[QuestsCanopy] Кнопка 'Authorize GitHub' не найдена — GitHub уже авторизован, пропускаем.")

            await self.human.scroll_to_selector(page=page, selector='button:has-text("Select Repository")')
            await self.human.click_on_selector(page=page, selector='button:has-text("Select Repository")')
            await self.human.type_text_selector(
                page=page, selector='input[placeholder="Search repositories..."]', text="canopy"
            )
            await self.human.scroll_to_selector(page=page, selector='div.border-2.cursor-pointer')
            await self.human.click_on_selector(page=page, selector='div.border-2.cursor-pointer')
            await self.human.scroll_to_selector(page=page, selector='text=Connect Repository')
            await self.human.click_on_selector(page=page, selector='text=Connect Repository')
            await self.human.scroll_to_selector(page=page, selector='text=Continue')
            await self.human.click_on_selector(page=page, selector='text=Continue')

        # Шаг 3 "Main Info": подбираем свободные имя чейна и тикер
        # (resolve_available_value сам перебирает варианты, пока сайт не подтвердит доступность)
        async def fill_main_info():
            nonlocal chain_name, ticker

            await self.human.scroll_to_top(page)

            chain_name = await self._resolve_available_value(
                page, '[placeholder="Enter chain name"]', "Chain name is available!", self._get_random_chain_name
            )
            ticker = await self._resolve_available_value(
                page, '[placeholder="Enter your ticker"]', "Ticker is available!", self._get_random_ticker
            )
            await self.human.scroll_to_selector(page=page, selector='text=Continue')
            await self.human.click_on_selector(page=page, selector='text=Continue')


        # Шаг 4 "Branding & Media": загружаем сгенерированное лого и описание (через GPT)
        async def fill_branding():
            logo_path = self._generate_random_logo()
            try:
                await page.locator("input#logo").set_input_files(logo_path)
            finally:
                os.remove(logo_path)

            # Даём странице отрисовать превью лого и блок "Brand Color" —
            # иначе вёрстка съезжает, пока курсор летит к textarea, и клик мажет мимо поля.
            await asyncio.sleep(random.uniform(1, 2))

            description = self._generate_description_via_gpt(chain_name)
            await self.human.scroll_to_selector(page=page, selector="textarea#chainDescription")
            await self.human.type_text_selector(
                page=page, selector="textarea#chainDescription", text=description
            )
            await self.human.scroll_to_selector(page=page, selector='text=Continue')
            await self.human.click_on_selector(page=page, selector='text=Continue')

        # Шаг 5 "Links & Documentation": вводим Twitter/X (если задан для профиля)
        # и прикладываем сгенерированный PDF с документацией
        async def fill_links_and_documentation():
            if twitter_handle:
                await self.human.scroll_to_selector(page=page, selector='button:has-text("Twitter/X")')
                await self.human.click_on_selector(page=page, selector='button:has-text("Twitter/X")')
                try:
                    await self.human.type_text_selector(
                        page=page,
                        selector="input[placeholder*='@yourchainhandle']",
                        text=twitter_handle,
                    )
                except Exception as e:
                    print(f"[QuestsCanopy] Не удалось найти поле ввода Twitter/X: {e}")
            else:
                print("[QuestsCanopy] Twitter handle не задан для этого профиля, пропускаем.")

            pdf_path = self._generate_random_pdf()
            try:
                await page.locator('input[accept*="pdf"]').set_input_files(pdf_path)
            finally:
                os.remove(pdf_path)

            await self.human.scroll_to_selector(page=page, selector='text=Continue')
            await self.human.click_on_selector(page=page, selector='text=Continue')

        # Шаг 6 "Launch Settings": указываем сумму первоначальной покупки токена
        async def fill_launch_settings():
            await self.human.type_text_selector(page=page, selector="input#initialPurchaseAmount", text="1")
            await self.human.scroll_to_selector(page=page, selector='text=Continue')
            await self.human.click_on_selector(page=page, selector='text=Continue')

        # Шаг 7 "Review & Payment": последний шаг — разблокируем кошелёк (если просят),
        # жмём "Pay & Launch Chain" и ждём редиректа на страницу запущенного чейна
        async def fill_review_and_payment():
            await asyncio.sleep(2)
            # докручиваем внутренний скролл-контейнер до конца, чтобы кнопка оплаты стала видна
            await page.evaluate("""
                () => {
                    const el = document.querySelector('#launchpad-content');
                    if (el) {
                        el.scrollTop = el.scrollHeight;
                    } else {
                        window.scrollTo(0, document.body.scrollHeight);
                    }
                }
            """)

            if await page.locator('button:has-text("Unlock wallet to pay")').count() > 0:
                await self.human.scroll_to_selector(page=page, selector='button:has-text("Unlock wallet to pay")')
                await self.human.click_on_selector(page=page, selector='button:has-text("Unlock wallet to pay")')
                await self.human.scroll_to_selector(page=page, selector='[data-testid="wallet-unlock-submit-button"]')
                await self.human.click_on_selector(page=page, selector='[data-testid="wallet-unlock-submit-button"]')
                await asyncio.sleep(2)

            await self.human.scroll_to_selector(page=page, selector='button:has-text("Pay & Launch Chain")')
            await self.human.click_on_selector(page=page, selector='button:has-text("Pay & Launch Chain")')

            try:
                await page.wait_for_url("**/chains/**", timeout=120000)
                print(f"[QuestsCanopy] Чейн успешно запущен: {page.url}")
            except Exception as e:
                print(f"[QuestsCanopy] Не дождались подтверждения запуска чейна: {e}")

        # порядок шагов визарда — должен совпадать с порядком в сайдбаре "Launch Steps"
        steps = [
            ("Language", fill_language),
            ("Connect Repo", fill_connect_repo),
            ("Main Info", fill_main_info),
            ("Branding & Media", fill_branding),
            ("Links & Documentation", fill_links_and_documentation),
            ("Launch Settings", fill_launch_settings),
            ("Review & Payment", fill_review_and_payment),
        ]

        # проходим шаги визарда с повторами: если что-то упадёт по пути —
        # перезагружаем страницу и продолжаем с того места, где остановились
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                # Галочка в сайдбаре не гарантирует, что шаг реально до конца сохранён
                # (кнопка Continue может быть неактивна) — поэтому последний "зелёный"
                # шаг не пропускаем, а принудительно перезаходим и заполняем заново.
                last_done_index = await self._get_last_done_index(page, steps)
                start_index = max(last_done_index, 0)

                for index, (step_name, fill_action) in enumerate(steps):
                    if index < start_index:
                        print(f"[QuestsCanopy] Шаг '{step_name}' уже пройден, пропускаем.")
                        continue

                    if index == start_index and last_done_index >= 0:
                        print(f"[QuestsCanopy] Перезаходим на последний пройденный шаг '{step_name}' и заполняем заново.")
                        await self.human.scroll_to_selector(page=page, selector=f'button:has-text("{step_name}")')
                        await self.human.click_on_selector(page=page, selector=f'button:has-text("{step_name}")')
                    else:
                        went_in = await self._go_to_step(page, step_name)
                        if not went_in:
                            continue

                    await asyncio.sleep(1)
                    await fill_action()
                break  # все шаги прошли успешно
            except Exception as e:
                print(
                    f"[QuestsCanopy] Ошибка на попытке {attempt}/{max_retries}: {e}. "
                    "Перезагружаем страницу и продолжаем с последнего пройденного шага."
                )
                await page.reload(wait_until="domcontentloaded", timeout=15000)
                await self.manager.wait_for_cloudflare(page)
                await asyncio.sleep(2)
        else:
            print(f"[QuestsCanopy] Не удалось пройти все шаги визарда за {max_retries} попыток.")

    # faucet() — задача "получить тестовые токены": тоже своя вкладка, закрывается в finally
    async def faucet(self):
        page_faucet = await self.manager.context.new_page()
        try:
            await self._faucet_body(page_faucet)
        finally:
            await page_faucet.close()

    async def _faucet_body(self, page_faucet):
        await page_faucet.goto(
            "https://testnet.app.canopynetwork.org/faucet/",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        await self.manager.wait_for_cloudflare(page_faucet)

        # если кнопка уже показывает "Check Again" — значит токены сегодня уже получены,
        # клик не нужен вообще
        already_claimed = await page_faucet.locator('button:has-text("Check Again")').count() > 0
        if already_claimed:
            print("[Faucet] Кнопка 'Check Again' — токены уже получены сегодня, пропускаем клик")

            return

        # иначе проверяем, что кнопка реально доступна для клейма, и жмём её
        button = page_faucet.locator('button:has-text("Claim Test Funds")').first
        is_visible = await self.manager.isvisible_txt_button(button, "Claim Test Funds", timeout=10000)
        if is_visible:
            await self.human.scroll_to_selector(page=page_faucet, selector='button:has-text("Claim Test Funds")')
            await self.human.click_on_selector(page=page_faucet, selector='button:has-text("Claim Test Funds")')
            # ждём подтверждение "Funds Claimed!" — без этого не знаем, прошёл клейм или нет
            try:
                await page_faucet.locator('text=Funds Claimed!').wait_for(state="visible", timeout=20000)
                print("[Faucet] Funds Claimed! тестовые токены получены")
            except Exception:
                print("[Faucet] Не дождались подтверждения 'Funds Claimed!' за 20с")
        else:
            print("[Faucet] Кнопка 'Claim Test Funds' недоступна (вероятно, уже получено сегодня)")

    # bay_token() — задача "купить токен своего чейна": своя вкладка, закрывается в finally
    async def bay_token(self):
        page_trade = await self.manager.context.new_page()
        try:
            await self._bay_token_body(page_trade)
        finally:
            await page_trade.close()

    async def _bay_token_body(self, page_trade):
        # список всех проектов — стартовая точка, на неё же возвращаемся при повторных попытках
        projects_url = "https://testnet.app.canopynetwork.org/projects"
        await page_trade.goto(projects_url, wait_until="domcontentloaded", timeout=15000)
        await self.manager.wait_for_cloudflare(page_trade)

        # вся цепочка кликов (фильтр -> выбор чейна -> сумма -> Continue -> Confirm)
        # обёрнута в retry: если любой шаг не удался — возвращаемся на /projects и пробуем заново
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                # фильтруем список проектов только по своим запущенным чейнам
                # (таймаут увеличен — страница тяжёлая, много асинхронных виджетов)
                await self.human.scroll_to_selector(page=page_trade, selector='button:has-text("My Chains")', timeout=15000)
                await asyncio.sleep(random.uniform(1, 2))
                clicked_my_chains = await self.human.click_on_selector(
                    page=page_trade, selector='button:has-text("My Chains")', timeout=15000
                )
                if not clicked_my_chains:
                    raise RuntimeError("кнопка 'My Chains' не найдена")

                await asyncio.sleep(random.uniform(1, 2))
                await self.human.scroll_down_blind(page_trade, steps=random.randint(1, 3))

                # открываем первый попавшийся свой чейн из отфильтрованного списка
                await self.human.scroll_to_selector(page=page_trade, selector='a[href^="/chains/"]')
                await asyncio.sleep(random.uniform(1, 3))

                clicked_project = await self.human.click_on_selector(page=page_trade, selector='a[href^="/chains/"]')
                await asyncio.sleep(random.uniform(2, 3))
                if not clicked_project:
                    raise RuntimeError("не удалось открыть страницу проекта")

                # поле суммы свопа уже сфокусировано после перехода на страницу чейна —
                # повторный клик (focus_first=True) иногда сбивал состояние страницы
                await self.human.type_text_selector(
                    page=page_trade, selector='input[data-testid="swap-amount-input"]', text="1", focus_first=False
                )

                await self.human.scroll_to_selector(page=page_trade, selector='text=Continue')
                clicked_continue = await self.human.click_on_selector(page=page_trade, selector='text=Continue')
                if not clicked_continue:
                    raise RuntimeError("кнопка 'Continue' не найдена")

                await self.human.scroll_to_selector(page=page_trade, selector='text=Confirm')
                clicked_confirm = await self.human.click_on_selector(page=page_trade, selector='text=Confirm')
                if not clicked_confirm:
                    raise RuntimeError("кнопка 'Confirm' не найдена")

                break  # весь путь до "Confirm" пройден успешно
            except Exception as e:
                # print(f"[Trade] Попытка {attempt}/{max_retries} не удалась ({e}), возвращаемся к списку проектов")
                await page_trade.goto(projects_url, wait_until="domcontentloaded", timeout=15000)
                await self.manager.wait_for_cloudflare(page_trade)
                await asyncio.sleep(random.uniform(2, 4))
        else:
            print(f"[Trade] Не удалось выполнить своп за {max_retries} попыток.")
            return

        # после "Confirm" ещё не значит, что транзакция подтвердилась в блокчейне —
        # ждём диалог успеха с кнопкой "Done"
        confirmed = await self._wait_for_tx_confirmed(page_trade, timeout=90)
        if confirmed:
            print("[Trade] Транзакция подтверждена (диалог 'Done')")
        else:
            print("[Trade] Не дождались подтверждения транзакции за 90с")

    # ==================================================================
    # Вспомогательные методы
    # ==================================================================

    @staticmethod
    def _get_random_chain_name() -> str:
        """Название чейна: случайное слово из NAME_SHAIN + 5-7 случайных цифр (для уникальности)."""
        name = random.choice(NAME_SHAIN)
        digits_count = random.randint(5, 7)
        digits = "".join(random.choice("0123456789") for _ in range(digits_count))
        return f"{name}{digits}"

    @staticmethod
    def _get_random_ticker() -> str:
        """Тикер: 6-9 случайных заглавных латинских букв."""
        letters_count = random.randint(6, 9)
        return "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(letters_count))

    @staticmethod
    def _generate_random_logo() -> str:
        """Создаёт случайный сплошной 1000x1000 PNG во временном файле, возвращает путь к нему."""
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        image = Image.new("RGB", (1000, 1000), color)

        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        image.save(path, "PNG")
        return path

    @staticmethod
    def _generate_random_pdf() -> str:
        """Создаёт случайный PDF (1-3 страницы) во временном файле, возвращает путь к нему."""
        pages_count = random.randint(1, 3)
        pages = [
            Image.new("RGB", (850, 1100), (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
            for _ in range(pages_count)
        ]

        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        pages[0].save(path, save_all=True, append_images=pages[1:])
        return path

    @staticmethod
    def _generate_description_via_gpt(chain_name: str) -> str:
        """Генерирует описание чейна через OpenAI GPT. При ошибке/без ключа — запасной шаблон."""
        fallback = (
            f"{chain_name} is a next-generation blockchain built on Canopy's "
            "infrastructure, enabling seamless digital token management and exchange."
        )

        if not OPENAI_API_KEY:
            return fallback

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Write a very short marketing description, strictly 70-100 characters total "
                                f"(including spaces and punctuation), for a new blockchain project called "
                                f"'{chain_name}', built on the Canopy network. Plain English, no markdown, "
                                "no quotes around it. Avoid any words "
                                "that could be mistaken for profanity by a naive substring filter (for "
                                "example avoid 'asset', 'class', 'assassin', 'password', 'grass'). "
                                "Return only the description text, nothing else."
                            ),
                        }
                    ],
                    "max_tokens": 150,
                    "temperature": 0.9,
                },
                timeout=20,
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"].strip()
            return text or fallback
        except Exception as e:
            print(f"[QuestsCanopy] Ошибка генерации описания через GPT: {e}")
            return fallback

    async def _run_step_sequence(self, page, steps, max_iterations: int = 20):
        """
        Проходит шаги мастера по тому, что РЕАЛЬНО видно на странице сейчас,
        а не по фиксированному порядку — так при рестарте скрипт сам находит,
        на каком шаге остановился сайт (он помнит прогресс), вместо того чтобы
        кликать по кнопкам, которых уже нет.

        steps — список (селектор_маркер_шага, async_действие_без_аргументов)
        в логическом порядке. На каждой итерации ищем первый ещё видимый маркер
        и выполняем только его действие.
        """
        for _ in range(max_iterations):
            current = None
            for marker, action in steps:
                try:
                    if await page.locator(marker).first.is_visible():
                        current = (marker, action)
                        break
                except Exception:
                    continue

            if current is None:
                print("[QuestsCanopy] Ни один известный шаг не найден — завершено или незнакомый экран.")
                return

            marker, action = current
            print(f"[QuestsCanopy] Текущий шаг: {marker}")
            await action()
            await asyncio.sleep(1.5)  # дать странице среагировать перед повторным сканом

        print("[QuestsCanopy] Достигнут лимит итераций, шаги не завершились.")

    async def _wait_for_tx_confirmed(self, page, timeout: int = 90) -> bool:
        """
        Ждёт появления кнопки "Done" в диалоге успешной транзакции
        (data-testid="transaction-done-button") — прямой и однозначный
        признак того, что своп/покупка завершились успешно. При появлении
        кликает по ней, чтобы закрыть диалог.
        """
        done_button = page.locator('[data-testid="transaction-done-button"]')
        try:
            await done_button.wait_for(state="visible", timeout=timeout * 1000)
        except Exception:
            return False

        await self.human.click_on_selector(page=page, selector='[data-testid="transaction-done-button"]')
        return True

    async def _is_step_done(self, page, step_name: str) -> bool:
        """Шаг в сайдбаре 'Launch Steps' помечен зелёной галочкой (svg.lucide-check), если уже пройден."""
        step_button = page.locator(f'button:has-text("{step_name}")').first
        checkmark = step_button.locator("svg.lucide-check")
        return await checkmark.count() > 0

    async def _go_to_step(self, page, step_name: str) -> bool:
        """
        Переходит на шаг визарда в сайдбаре, если он ещё не пройден.
        Возвращает True, если перешли (и нужно заполнять поля), False — если шаг уже готов.
        """
        if await self._is_step_done(page, step_name):
            print(f"[QuestsCanopy] Шаг '{step_name}' уже пройден, пропускаем.")
            return False

        await self.human.scroll_to_selector(page=page, selector=f'button:has-text("{step_name}")')
        await self.human.click_on_selector(page=page, selector=f'button:has-text("{step_name}")')
        return True

    async def _get_last_done_index(self, page, steps) -> int:
        """
        Индекс последнего ПОДРЯД пройденного шага (с галочкой), или -1, если ни один не пройден.
        Останавливается на первом непройденном шаге, потому что шаги визарда идут по порядку.
        """
        last_done = -1
        for i, (step_name, _) in enumerate(steps):
            if await self._is_step_done(page, step_name):
                last_done = i
            else:
                break
        return last_done

    async def _resolve_available_value(self, page, selector: str, success_text: str, get_new_value) -> str:
        """
        Вводит значение в поле, перезагружает страницу и проверяет, появилось ли
        сообщение success_text (например 'Chain name is available!'). Если нет —
        берёт новое значение через get_new_value() и повторяет, максимум 10 раз.
        Возвращает итоговое (последнее использованное) значение.
        """
        value = get_new_value()

        for attempt in range(1, 11):
            # print(f"[QuestsCanopy] {selector} (попытка {attempt}/10): {value}")

            await self.human.type_text_selector(page=page, selector=selector, text=value)
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            await self.manager.wait_for_cloudflare(page)
            await asyncio.sleep(4)

            if await page.locator(f'p:has-text("{success_text}")').count() > 0:
                # print(f"[QuestsCanopy] '{value}' доступно.")
                return value

            # print(f"[QuestsCanopy] '{value}' недоступно, пробуем новое.")
            value = get_new_value()

        print(f"[QuestsCanopy] Не удалось подобрать свободное значение за 10 попыток ({selector}).")
        return value
