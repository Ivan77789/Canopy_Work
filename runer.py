import asyncio
import random

from browser.playwright_client import activity, close_browser_connection


class Runner:
    def __init__(self, filename="profiles.txt"):
        self.accounts = []
        self.load_accounts(filename)
        random.shuffle(self.accounts)
        print("Аккаунты загружены и перемешаны:", self.accounts)

    def load_accounts(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                self.accounts = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Файл {filename} не найден! Список аккаунтов пуст.")
            self.accounts = []

    async def main(self):
        for idx, profile in enumerate(self.accounts, 1):
            print(f"[{idx}/{len(self.accounts)}] Запуск профиля {profile}...")
            page, playwright, browser, context = await activity(profile)

            page = await context.new_page()
            await page.goto(
                "https://bot.sannysoft.com",
                wait_until="domcontentloaded",
                timeout=15000,
            )








            await asyncio.sleep(35)
            await close_browser_connection(page, playwright, browser, context, profile)
            print(f"Профиль {profile} отработал")









if __name__ == "__main__":
    runner = Runner()  # можно передать имя файла, если оно другое
    asyncio.run(runner.main())