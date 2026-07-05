import asyncio
import random

from browser.management import ManagerBrowserContext
from config import WALLET_PASSWORD
from network.network import Network
from browser.human_emulation_brawser import HumanMouse


class Runner:
    def __init__(self, filename="profiles.txt"):
        self.accounts = []
        self.load_accounts(filename)
        random.shuffle(self.accounts)
        print("Аккаунты загружены и перемешаны:", self.accounts)
        self.network = Network()
        self.human = HumanMouse()

    def load_accounts(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                self.accounts = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Файл {filename} не найден! Список аккаунтов пуст.")
            self.accounts = []

    async def main(self):
        for idx, profile in enumerate(self.accounts, 1):
            # self.network.get_fresh_ip()

            print(f"[{idx}/{len(self.accounts)}] Запуск профиля {profile}...")

            manager = ManagerBrowserContext(self.human)
            started = await manager.start(profile)

            if not started:
                print(f"Профиль {profile} пропущен: не удалось подключиться к браузеру.")
                continue

            await manager.unlock_wallet(WALLET_PASSWORD)
            await asyncio.sleep(1)

            await manager.goto("https://rewards.testnet.app.canopynetwork.org/")

            await manager.authorization("button.bg-green-600", "0x", page=manager.page)

            """ НАЧАЛО РАБОТЫ ПРОЕКТА В БРАУЗЕРЕ"""




            await asyncio.sleep(35)
            await manager.close()
            print(f"Профиль {profile} отработал")









if __name__ == "__main__":
    runner = Runner()  # можно передать имя файла, если оно другое
    asyncio.run(runner.main())