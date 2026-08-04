import asyncio
import csv
import random
import time
from datetime import date, datetime, timedelta, timezone


from browser.management import ManagerBrowserContext
from config import WAIT_FOR_UTC_MIDNIGHT, WALLET_PASSWORD
from network.network import Network
from browser.human_emulation_brawser import HumanMouse
from tasks.canopy_tasks import QuestsCanopy

POINTS_REPORT_FILE = "points_report.csv"


def _format_duration(seconds: float) -> str:
    """Форматирует секунды в 'M:SS' (или 'H:MM:SS', если запуск дольше часа)."""
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


async def _wait_for_utc_midnight():
    """Ждёт до ближайших 00:00 UTC (ежедневный сброс квестов/faucet)."""
    now = datetime.now(timezone.utc)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    wait_seconds = (next_midnight - now).total_seconds()
    print(
        f"Ожидаем 00:00 UTC ({next_midnight.strftime('%Y-%m-%d %H:%M:%S')} UTC), "
        f"осталось {_format_duration(wait_seconds)}..."
    )
    await asyncio.sleep(wait_seconds)
    print("00:00 UTC наступило, начинаем работу с профилями.")


def _index_sort_key(index_str: str):
    """Числовые индексы сортируются как числа (1, 2, ..., 12), нечисловые — в конец по алфавиту."""
    try:
        return (0, int(index_str))
    except ValueError:
        return (1, index_str)


def reset_points_report(accounts):
    """
    Очищает CSV и пишет по одной пустой строке на каждый свой_индекс из
    profiles.txt (отсортированные по номеру) — так у таблицы сразу фиксированная
    структура, и профили, которые не отработали за этот прогон, остаются видны
    как пустые строки, а не пропадают из таблицы.
    """
    indexes = sorted({own_index for own_index, _, _ in accounts}, key=_index_sort_key)
    with open(POINTS_REPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["profile", "date", "total_points", "points_today", "rank"])
        for own_index in indexes:
            writer.writerow([own_index, "", "", "", ""])


def save_points_report(profile: str, total_points: int, points_today: int, rank: str):
    """
    Обновляет строку с индексом profile актуальными данными (не добавляет новую) —
    читает весь CSV, заменяет нужную строку по индексу и перезаписывает файл целиком.
    """
    with open(POINTS_REPORT_FILE, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header, data_rows = rows[0], rows[1:]
    new_row = [profile, date.today().isoformat(), total_points, points_today, rank]

    updated = False
    for i, row in enumerate(data_rows):
        if row and row[0] == profile:
            data_rows[i] = new_row
            updated = True
            break
    if not updated:
        data_rows.append(new_row)

    with open(POINTS_REPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)


class Runner:
    def __init__(self, filename="profiles.txt"):
        self.accounts = []
        self.load_accounts(filename)
        random.shuffle(self.accounts)
        print("Аккаунты загружены и перемешаны:", self.accounts)
        self.network = Network()
        self.human = HumanMouse()

    def load_accounts(self, filename):
        """Строка формата 'свой_индекс:номер_профиля_adspower:twitter_handle' (twitter_handle может быть пустым)."""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                self.accounts = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    own_index, _, rest = line.partition(":")
                    profile, _, twitter = rest.partition(":")
                    self.accounts.append((own_index.strip(), profile.strip(), twitter.strip()))
        except FileNotFoundError:
            print(f"Файл {filename} не найден! Список аккаунтов пуст.")
            self.accounts = []

    async def main(self):
        if WAIT_FOR_UTC_MIDNIGHT:
            await _wait_for_utc_midnight()

        start_time = time.monotonic()
        reset_points_report(self.accounts)
        for idx, (own_index, profile, twitter) in enumerate(self.accounts, 1):
            status, fresh_ip = self.network.get_fresh_ip()
            if status != "SUCCESS":
                print(f"Профиль {profile} пропущен: не удалось сменить IP (модем недоступен?).")
                continue

            print(f"[{idx}/{len(self.accounts)}] Запуск профиля {profile} (twitter: {twitter or '—'}, IP: {fresh_ip})...")

            manager = ManagerBrowserContext(self.human)
            started = await manager.start(profile)

            if not started:
                print(f"Профиль {profile} пропущен: не удалось подключиться к браузеру.")
                continue

            try:
                await manager.unlock_wallet(WALLET_PASSWORD)
                await asyncio.sleep(1)

                await manager.goto("https://rewards.testnet.app.canopynetwork.org/")

                # страница загрузилась — значит AdsPower стартовал нормально,
                # отладочная вкладка больше не нужна
                if manager.debag_page and not manager.debag_page.is_closed():
                    await manager.debag_page.close()

                await manager.authorization("button.bg-green-600", "0x", page=manager.page)

                initial_points = await manager.parse_points()

                tasks = QuestsCanopy(self.human, manager)
                await tasks.faucet()
                await tasks.launch_virtual_hain(twitter_handle=twitter)
                await tasks.bay_token()

                await manager.goto("https://rewards.testnet.app.canopynetwork.org/")
                await manager.page.reload(wait_until="domcontentloaded", timeout=15000)
                await manager.wait_for_cloudflare(manager.page)
                total_points = await manager.parse_points()
                rank = await manager.parse_rank()
                points_today = total_points - initial_points
                save_points_report(own_index, total_points, points_today, rank)
                # print(
                #     f"[Points] Профиль {profile} (индекс {own_index}): всего {total_points}, "
                #     f"заработано сегодня {points_today}, ранг {rank}"
                # )

                """ НАЧАЛО РАБОТЫ ПРОЕКТА В БРАУЗЕРЕ"""
            except Exception as e:
                print(f"Профиль {profile}: ошибка ({e}), пропускаем.")
            finally:
                await manager.close()
                print(f"Профиль {profile} отработал")

        elapsed = time.monotonic() - start_time
        print(f"Скрипт отработал за {_format_duration(elapsed)}")









if __name__ == "__main__":
    runner = Runner()  # можно передать имя файла, если оно другое
    asyncio.run(runner.main())