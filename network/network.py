

class Network:
    def __init__(self):
        pass




    @staticmethod
    def get_fresh_ip():
        import requests
        import time
        import base64
        import json
        import os

        BASE_URL = "http://192.168.8.1"
        POST_URL = BASE_URL + "/reqproc/proc_post"
        GET_URL = BASE_URL + "/reqproc/proc_get"

        IP_CHECK_URL = "https://api.ipify.org?format=json"
        IP_HISTORY_FILE = "ip_history.json"

        MAX_SAME_IP = 10

        session = requests.Session()

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/index.html",
            "User-Agent": "Mozilla/5.0"
        }

        # ========= HISTORY =========
        def load_history():
            if not os.path.exists(IP_HISTORY_FILE):
                return {}

            try:
                with open(IP_HISTORY_FILE, "r") as f:
                    data = json.load(f)
            except Exception as e:
                print("LOAD HISTORY ERROR:", e)
                return {}

            now = time.time()
            max_age = 25 * 3600

            cleaned = {ip: ts for ip, ts in data.items() if (now - ts) <= max_age}

            if cleaned != data:
                save_history(cleaned)

            return cleaned

        def save_history(data):
            try:
                with open(IP_HISTORY_FILE, "w") as f:
                    json.dump(data, f)
            except Exception as e:
                print("SAVE HISTORY ERROR:", e)

        # ========= IP =========
        def get_ip():
            try:
                r = requests.get(IP_CHECK_URL, timeout=10)
                return r.json().get("ip")
            except Exception as e:
                print("IP ERROR:", e)
                return None

        def is_ip_valid(ip, history):
            return ip not in history or (time.time() - history[ip]) > 86400

        # ========= STATUS =========
        def get_status():
            params = {
                "multi_data": "1",
                "isTest": "false",
                "cmd": "ppp_status,network_type,signalbar"
            }

            try:
                r = session.get(GET_URL, params=params, timeout=5)
                return r.text
            except Exception as e:
                print("STATUS ERROR:", e)
                return None

        # ========= ROTATE =========
        def rotate():
            try:
                session.post(POST_URL, headers=headers, data={
                    "isTest": "false",
                    "notCallback": "true",
                    "goformId": "DISCONNECT_NETWORK"
                })
                time.sleep(5)

                session.post(POST_URL, headers=headers, data={
                    "isTest": "false",
                    "goformId": "SET_BEARER_PREFERENCE",
                    "BearerPreference": "Only_LTE"
                })
                time.sleep(2)

                session.post(POST_URL, headers=headers, data={
                    "isTest": "false",
                    "notCallback": "true",
                    "goformId": "CONNECT_NETWORK"
                })

                # ждём подключение
                for _ in range(20):
                    status = get_status()
                    if status and "connected" in status.lower():
                        return True
                    time.sleep(2)

                print("ROTATE TIMEOUT")
                return False

            except Exception as e:
                print("ROTATE ERROR:", e)
                return False

        # ========= START =========
        try:
            session.get(BASE_URL, timeout=5)
        except Exception as e:
            print("MODEM OPEN ERROR:", e)
            return None, None

        # логин
        try:
            password = base64.b64encode("admin".encode()).decode()

            session.post(POST_URL, headers=headers, data={
                "isTest": "false",
                "goformId": "LOGIN",
                "password": password
            })
        except Exception as e:
            print("LOGIN ERROR:", e)
            return None, None

        history = load_history()

        last_ip = None
        same_ip_count = 0

        while True:
            if not rotate():
                print("ROTATE FAILED → RETRY")
                continue

            ip = get_ip()
            print("CURRENT IP:", ip)

            if not ip:
                print("IP NOT RECEIVED → RETRY")
                continue

            if ip == last_ip:
                same_ip_count += 1
            else:
                same_ip_count = 0
                last_ip = ip

            print("SAME IP COUNT:", same_ip_count)

            if same_ip_count >= MAX_SAME_IP:
                print("❌ SAME IP LIMIT → STOP")
                return None, None

            if is_ip_valid(ip, history):
                print("✅ IP OK")
                history[ip] = time.time()
                save_history(history)
                return "SUCCESS", ip
            else:
                print("IP USED RECENTLY → ROTATE AGAIN")