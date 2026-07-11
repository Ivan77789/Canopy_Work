import asyncio
import random
import math
from typing import Optional, Tuple
from playwright.async_api import Page


class HumanMouse:
    def __init__(self):
        self._last_x = 0
        self._last_y = 0
        # Головне блокування, щоб уникнути "телепортації" миші
        self._lock = asyncio.Lock()

    async def _get_viewport_size(self, page: Page) -> Tuple[int, int]:
        viewport = page.viewport_size
        if viewport:
            return (viewport["width"], viewport["height"])
        try:
            size = await page.evaluate(
                "({ width: window.innerWidth, height: window.innerHeight })"
            )
            if size and size.get("width"):
                return (size["width"], size["height"])
        except Exception:
            pass
        return (1280, 720)

    async def _get_start_position(self, page: Page) -> Tuple[int, int]:
        if self._last_x == 0 and self._last_y == 0:
            w, h = await self._get_viewport_size(page)
            return (w // 2, h // 2)
        return (self._last_x, self._last_y)

    async def scroll_to_selector(self, page: Page, selector: str, timeout: int = 5000) -> bool:
        """
        Плавно докручує сторінку до елемента колесом миші невеликими кроками,
        замість миттєвого scroll_into_view_if_needed (він телепортує без анімації).
        Викликається окремо, до hover_on_selector/click_on_selector.
        Повертає True, якщо елемент опинився у видимій області.
        """
        element = page.locator(selector).first
        try:
            await element.wait_for(state="visible", timeout=timeout)
        except Exception:
            print(f"[HumanMouse] scroll_to_selector: '{selector}' не появился за {timeout / 1000:.0f}с")
            return False

        # Мышь должна быть над контентом, иначе wheel может уйти не туда
        w, h = await self._get_viewport_size(page)
        await page.mouse.move(w // 2, h // 2)

        for _ in range(20):
            box = await element.bounding_box()
            if not box:
                return False

            if 0 <= box["y"] and box["y"] + box["height"] <= h:
                return True  # вже у видимій області

            # скільки реально треба доскролити, щоб елемент влаштувався у в'юпорт —
            # обмежуємо крок цією відстанню, інакше випадковий крок 150-350px
            # може проскочити кнопку наскрізь
            if box["y"] < 0:
                direction = -1
                distance = -box["y"]
            else:
                direction = 1
                distance = (box["y"] + box["height"]) - h

            step = min(random.randint(150, 350), max(int(distance), 30))
            await page.mouse.wheel(0, direction * step)
            await asyncio.sleep(random.uniform(0.05, 0.15))

        print(f"[HumanMouse] scroll_to_selector: не удалось докрутить до '{selector}'")
        return False

    async def scroll_down_blind(self, page: Page, steps: int = 20) -> None:
        """
        Прокручує сторінку вниз наосліп, без орієнтира на елемент — для
        лениво відрендерюваних блоків, яких ще немає в DOM, поки до них
        не доскролити (на відміну від scroll_to_selector, який вимагає,
        щоб елемент вже існував).
        """
        w, h = await self._get_viewport_size(page)
        await page.mouse.move(w // 2, h // 2)
        for _ in range(steps):
            await page.mouse.wheel(0, random.randint(200, 400))
            await asyncio.sleep(random.uniform(0.1, 0.25))

    async def scroll_to_top(self, page: Page, max_steps: int = 30) -> None:
        """
        Прокручує сторінку колесом миші вгору, поки скрол не стане 0
        (або поки не вичерпаються спроби) — людиноподібна альтернатива
        миттєвому scrollTo(0, 0). Деякі сторінки (наприклад лончпад)
        скролляться не через window, а через внутрішній контейнер
        #launchpad-content — перевіряємо його, якщо є, інакше window.scrollY.
        """
        w, h = await self._get_viewport_size(page)
        await page.mouse.move(w // 2, h // 2)
        get_scroll_top_js = """
            () => {
                const el = document.querySelector('#launchpad-content');
                return el ? el.scrollTop : window.scrollY;
            }
        """
        for _ in range(max_steps):
            scroll_top = await page.evaluate(get_scroll_top_js)
            if scroll_top <= 0:
                return
            await page.mouse.wheel(0, -random.randint(200, 400))
            await asyncio.sleep(random.uniform(0.1, 0.25))

    def _ease_in_out(self, t: float) -> float:
        """Плавна крива прискорення/гальмування (синусоїдальна)."""
        return (1 - math.cos(math.pi * t)) / 2

    def _speed_factor(self, progress: float) -> float:
        """
        Реалістичний профіль швидкості:
        - Розгін: 0..20% → фактор 0.4..1.0
        - Крейсер: 20..80% → фактор 0.8..1.2 (додано більше шуму)
        - Гальмування: 80..100% → фактор 1.0..0.4
        """
        if progress < 0.2:
            t = progress / 0.2
            return 0.4 + 0.6 * self._ease_in_out(t)
        elif progress < 0.8:
            # Більше хаотичності в крейсерській швидкості
            return random.uniform(0.75, 1.25)
        else:
            t = (progress - 0.8) / 0.2
            return 1.0 - 0.6 * self._ease_in_out(t)

    # --------------------------------------------------------------
    # БАЗОВИЙ РУХ (без блокування) - використовується всередині класу
    # --------------------------------------------------------------
    async def _move_to_raw(
        self,
        page: Page,
        end_x: int,
        end_y: int,
        duration: float,
        urgent: bool = False,
    ):
        """
        Реалізація фізичного переміщення курсора.
        Викликається тільки з-під self._lock!
        """
        start_x, start_y = await self._get_start_position(page)
        dist = math.hypot(end_x - start_x, end_y - start_y)
        if dist < 3:
            return

        # ---- КРОК 1: Розраховуємо кількість точок (ТЕПЕР ЇХ БАГАТО) ----
        # Мінімум 60 точок навіть для коротких відстаней, щоб не було ривків
        steps = max(60, min(150, int(dist / 3)))

        # ---- КРОК 2: Додаємо випадкову "паузу-роздум" перед рухом ----
        await asyncio.sleep(random.uniform(0.03, 0.12))

        # ---- КРОК 3: Будуємо криву Безьє з 4 контрольними точками ----
        # Додаємо більше випадковості у вигин траєкторії
        angle = math.atan2(end_y - start_y, end_x - start_x)
        perp = angle + math.pi / 2

        # Основний вигин
        bend_amount = dist * random.uniform(0.06, 0.25)  # Більше варіацій
        bend_sign = random.choice([-1, 1])
        mid_x = (start_x + end_x) / 2 + math.cos(perp) * bend_amount * bend_sign
        mid_y = (start_y + end_y) / 2 + math.sin(perp) * bend_amount * bend_sign

        # Контрольні точки з додатковим рандомом
        cx1 = start_x + (mid_x - start_x) * random.uniform(0.25, 0.75)
        cy1 = start_y + (mid_y - start_y) * random.uniform(0.25, 0.75)
        cx2 = end_x + (mid_x - end_x) * random.uniform(0.25, 0.75)
        cy2 = end_y + (mid_y - end_y) * random.uniform(0.25, 0.75)

        # ---- КРОГ 4: Затримки між кроками ----
        # Мінімум 5-8 мс, щоб Playwright встигав генерувати події
        base_delay = duration / steps
        min_delay = (
            0.005 if not urgent else 0.003
        )  # Терміново трохи швидше, але не менше 3мс

        # ---- КРОК 5: Цикл руху ----
        for i in range(steps + 1):
            if page.is_closed():
                break

            t = i / steps
            # Точка на кривій Безьє
            x = (
                (1 - t) ** 3 * start_x
                + 3 * (1 - t) ** 2 * t * cx1
                + 3 * (1 - t) * t**2 * cx2
                + t**3 * end_x
            )
            y = (
                (1 - t) ** 3 * start_y
                + 3 * (1 - t) ** 2 * t * cy1
                + 3 * (1 - t) * t**2 * cy2
                + t**3 * end_y
            )

            # Мікротремор (затухає до кінця)
            tremor = 0.8 * (1 - t) + random.uniform(0.1, 0.3)  # додано базовий шум
            x += random.gauss(0, tremor)
            y += random.gauss(0, tremor)

            # Відправка позиції в Playwright
            await page.mouse.move(x, y)

            # ---- ВАЖЛИВО: Випадкова мікропауза всередині руху (20-50мс) ----
            # Людина іноді "замислюється" на півдорозі
            if i == int(steps * 0.4) and random.random() < 0.35:
                await asyncio.sleep(random.uniform(0.025, 0.075))
            if i == int(steps * 0.7) and random.random() < 0.25:
                await asyncio.sleep(random.uniform(0.015, 0.05))

            # Розрахунок затримки з урахуванням профілю швидкості
            speed = self._speed_factor(t)
            # Додаємо випадковий шум до швидкості (від 0.8 до 1.2 від розрахункової)
            speed_noise = random.uniform(0.85, 1.15)
            delay = max(min_delay, base_delay / (speed * speed_noise))
            await asyncio.sleep(delay)

        # Фінальне точне позиціонування (без тремору)
        await page.mouse.move(end_x, end_y)
        self._last_x = end_x
        self._last_y = end_y

    # --------------------------------------------------------------
    # ПУБЛІЧНИЙ РУХ (з блокуванням та логікою промаху)
    # --------------------------------------------------------------
    async def move_to(
        self,
        page: Page,
        end_x: int,
        end_y: int,
        duration: Optional[float] = None,
        overshoot_prob: float = 0.0,
    ):
        """
        Основний метод руху з антидетект-фічами:
        - Блокування (Lock) для уникнення гонок.
        - Випадковий промах (overshoot) з поверненням.
        """
        async with self._lock:
            # Якщо це терміновий рух (наприклад, Buy) - промахів немає або майже немає
            if overshoot_prob > 0 and random.random() < overshoot_prob:
                # ---- Розраховуємо точку "перельоту" (промах) ----
                start_x, start_y = await self._get_start_position(page)
                dist = math.hypot(end_x - start_x, end_y - start_y)

                # Кут напрямку до цілі
                if dist < 5:
                    angle = random.uniform(0, 2 * math.pi)
                else:
                    angle = math.atan2(end_y - start_y, end_x - start_x)

                # Відстань перельоту: чим менша кнопка, тим більший промах
                overshoot_dist = random.randint(15, 50) + (1 - overshoot_prob) * 20

                overshoot_x = int(
                    end_x + math.cos(angle) * overshoot_dist + random.randint(-15, 15)
                )
                overshoot_y = int(
                    end_y + math.sin(angle) * overshoot_dist + random.randint(-15, 15)
                )

                # Обмежуємо, щоб не вилетіти за межі екрану
                w, h = await self._get_viewport_size(page)
                overshoot_x = max(10, min(w - 10, overshoot_x))
                overshoot_y = max(10, min(h - 10, overshoot_y))

                # Час для промаху (швидкий ривок)
                overshoot_dur = (
                    random.uniform(0.08, 0.18) if duration is None else duration * 0.6
                )
                await self._move_to_raw(
                    page, overshoot_x, overshoot_y, overshoot_dur, urgent=True
                )

                # Пауза "усвідомлення помилки" (людина помічає, що промахнулась)
                await asyncio.sleep(random.uniform(0.12, 0.35))

                # Повертаємось до цілі (трохи повільніше, бо прицілюється)
                return_dur = (
                    random.uniform(0.12, 0.25) if duration is None else duration * 0.5
                )
                await self._move_to_raw(page, end_x, end_y, return_dur, urgent=False)
            else:
                # ---- Звичайний рух (без промаху) ----
                if duration is None:
                    # Більше випадковості в часі: люди рухаються з різною швидкістю
                    base = 0.15 + (
                        math.hypot(end_x - self._last_x, end_y - self._last_y) / 1200
                    )
                    duration = base + random.uniform(-0.08, 0.18)
                    duration = max(0.1, min(0.9, duration))

                await self._move_to_raw(
                    page, end_x, end_y, duration, urgent=(overshoot_prob == 0)
                )

    #--------------------------------------------------------------
    #ДІЇ НАД СЕЛЕКТОРАМИ
    #--------------------------------------------------------------
    async def hover_on_selector(
        self,
        page: Page,
        selector: str,
        duration: Optional[float] = None,
    ):
        """Навести курсор на елемент."""
        try:
            element = page.locator(selector).first
            try:
                await element.wait_for(state="visible", timeout=5000)
            except Exception:
                print(f"[HumanMouse] '{selector}' не появился за 5с")
                return
            box = await element.bounding_box()
            if not box:
                return

            # Рандомна точка всередині, але з можливістю краю
            target_x = int(box["x"] + box["width"] * random.uniform(0.1, 0.9))
            target_y = int(box["y"] + box["height"] * random.uniform(0.1, 0.9))

            await self.move_to(page, target_x, target_y, duration, overshoot_prob=0.0)

            # Пауза після наведення
            await asyncio.sleep(random.uniform(0.08, 0.25))
        except Exception as e:
            print(f"[HumanMouse] hover_on_selector error '{selector}': {e}")

    async def click_on_selector(
        self,
        page: Page,
        selector: str,
        duration: Optional[float] = None,
        urgent: bool = False,
        timeout: int = 5000,
    ):
        """
        Клік на селекторі з людською поведінкою.
        Якщо urgent=True - летимо швидко і без промахів.
        Повертає True, якщо клік реально відбувся, інакше False.
        """
        try:
            element = page.locator(selector).first
            try:
                await element.wait_for(state="visible", timeout=timeout)
            except Exception:
                print(f"[HumanMouse] '{selector}' не появился за {timeout / 1000:.0f}с")
                return False
            box = await element.bounding_box()
            if not box:
                return False

            # ---- КРОК 1: Клікаємо не ідеально в центр, а з випадковим зсувом ----
            # Діапазон -0.1 .. 1.1 дозволяє клікнути трохи за межі кнопки
            # ---- КЛІКАЄМО ВСЕРЕДИНІ КНОПКИ, АЛЕ З ВИПАДКОВИМ ЗСУВОМ ----
            # Гарантовано в межах [0, 1] – клік завжди спрацює
            offset_x = random.uniform(0.15, 0.85)  # не притискаємось до країв
            offset_y = random.uniform(0.15, 0.85)

            target_x = int(box["x"] + box["width"] * offset_x)
            target_y = int(box["y"] + box["height"] * offset_y)

            # Обмежуємо, щоб не вийти за межі в'юпорту
            w, h = await self._get_viewport_size(page)
            target_x = max(5, min(w - 5, target_x))
            target_y = max(5, min(h - 5, target_y))

            # ---- КРОК 2: Розраховуємо ймовірність промаху ----
            # Якщо кнопка маленька (< 50px) - промах частіше
            # Якщо терміновий клік - промахів немає
            if urgent:
                overshoot_prob = 0.0
            else:
                btn_width = box["width"]
                if btn_width < 40:
                    overshoot_prob = 0.30  # маленькі кнопки (стоп-лоси)
                elif btn_width < 80:
                    overshoot_prob = 0.20  # середні
                else:
                    overshoot_prob = 0.12  # великі кнопки (Buy/Sell)

            # ---- КРОГ 3: Рух до цілі ----
            await self.move_to(page, target_x, target_y, duration, overshoot_prob)

            # ---- КРОГ 4: Пауза перед натисканням (рефлекс) ----
            await asyncio.sleep(random.uniform(0.05, 0.22))

            # ---- КРОК 5: Клік ----
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.03, 0.12))  # тривалість натискання
            await page.mouse.up()

            # ---- КРОК 6: Пауза після кліку ----
            await asyncio.sleep(random.uniform(0.1, 0.35)) #0.1 - 0.35

            return True
        except Exception as e:
            print(f"[HumanMouse] click_on_selector error '{selector}': {e}")
            return False

    async def type_text_selector(
        self,
        page: Page,
        selector: str,
        text: str,
        mistake_prob: float = 0.04,
        focus_first: bool = True,
    ):
        """
        Людський ввід тексту: клік у поле (якщо focus_first=True), потім
        посимвольний ввід з випадковими затримками, паузами "на подумати"
        і рідкісними опечатками з виправленням через Backspace.

        focus_first=False пропускає клік — для полів, які вже у фокусі
        (курсор вже блимає всередині), де повторний клік може збити стан
        сторінки (наприклад, викликати небажаний ре-рендер/перезавантаження).
        """
        try:
            if focus_first:
                clicked = await self.click_on_selector(page=page, selector=selector, urgent=True)
                if not clicked:
                    raise RuntimeError(f"клік по '{selector}' не удался, ввод текста пропущен")
            else:
                # Навіть якщо клік пропускаємо (припускаємо, що поле вже у фокусі),
                # переконуємось, що елемент реально існує — інакше Ctrl+A вдарить
                # по всій сторінці замість поля.
                try:
                    await page.locator(selector).first.wait_for(state="visible", timeout=5000)
                except Exception:
                    raise RuntimeError(f"'{selector}' не появился за 5с (focus_first=False)")

            # Очищаємо попередній вміст поля перед вводом нового тексту.
            # Ctrl+A/Backspace інколи не спрацьовує (втрата фокуса, react-стейт
            # переписує значення асинхронно), тому перевіряємо результат і,
            # якщо поле все ще не пусте, чистимо примусово через .fill("").
            locator = page.locator(selector).first
            for _ in range(3):
                await page.keyboard.press("Control+A")
                await asyncio.sleep(random.uniform(0.05, 0.1))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))

                current_value = await locator.input_value()
                if not current_value:
                    break
            else:
                await locator.fill("")
                await asyncio.sleep(random.uniform(0.05, 0.15))

            for char in text:
                if random.random() < mistake_prob:
                    wrong_char = random.choice("asdfghjklqwertyuiopzxcvbnm")
                    await page.keyboard.type(wrong_char)
                    await asyncio.sleep(random.uniform(0.08, 0.2))
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.04, 0.18))

                # Пауза "на подумати" між словами/символами
                if random.random() < 0.05:
                    await asyncio.sleep(random.uniform(0.2, 0.6))

            await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            print(f"[HumanMouse] type_text_selector error '{selector}': {e}")
            raise

