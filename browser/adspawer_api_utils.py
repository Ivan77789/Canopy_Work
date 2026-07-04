import requests
import json


API_URL = "http://local.adspower.net:50325"

def start_browser(profile_number):
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-popup-blocking",
        "--disable-default-apps"
    ]

    params = {
        'serial_number': profile_number,
        'launch_args': json.dumps(launch_args),
        'open_tabs': 1
    }

    try:
        response = requests.get(f'{API_URL}/api/v1/browser/start', params=params)
        print(f"Raw response: {response.text}")
        response.raise_for_status()
        data = response.json()

        if data.get("code") == 0:
            puppeteer_ws = data["data"]["ws"]["puppeteer"]
            print(f"Browser started successfully for profile {profile_number}.")
            return puppeteer_ws

        else:
            print(f"Failed to start browser for profile {profile_number}: {data['msg']}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Request error while starting browser: {e}")
        return None





def check_browser_status(profile_number):
    try:
        response = requests.get(f'{API_URL}/api/v1/browser/active', params={'serial_number': profile_number})
        print(f"Raw response: {response.text}")
        response.raise_for_status()
        data = response.json()

        if data.get("code") == 0 and data["data"]["status"] == "Active":
            print(f"Browser is active for profile {profile_number}.")
            return True

        else:
            print(f"Browser is NOT active for profile {profile_number}.")
            return False


    except requests.exceptions.RequestException as e:
        print(f"Request error while checking browser status: {e}")
        return False





def close_browser(profile_number):
    try:
        response = requests.get(f'{API_URL}/api/v1/browser/stop', params={'serial_number': profile_number})
        print(f"Raw response: {response.text}")
        response.raise_for_status()
        data = response.json()

        if data.get("code") == 0:
            print(f"Browser closed successfully for profile {profile_number}.")
            return True

        else:
            print(f"Failed to close browser for profile {profile_number}: {data['msg']}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Request error while closing browser: {e}")
        return False


