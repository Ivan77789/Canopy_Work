# from web3 import Web3
# from eth_account import Account
# from eth_account.messages import encode_defunct
# import requests
#
#
#
# # w3 = Web3(Web3.HTTPProvider("https://rpc-url"))  # подключение к ноде (не обязательно для подписи)
# # print(w3.is_connected())
#
# headers =  {
#     "accept": "*/*",
#     "accept-language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
#     "content-type": "application/json",
#     "priority": "u=1, i",
#     "sec-ch-ua": "\"Google Chrome\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
#     "sec-ch-ua-mobile": "?0",
#     "sec-ch-ua-platform": "\"Windows\"",
#     "sec-fetch-dest": "empty",
#     "sec-fetch-mode": "cors",
#     "sec-fetch-site": "same-origin"
#   }
#
#
#
#
# session = requests.Session()
#
# session.headers.update(headers)
#
# private_key = ''
#
# # account = Account.from_key(private_key)
# # print(account.address)  # публичный адрес, должен совпадать с walletAddress
#
# csrf_resp = session.get("https://rewards.testnet.app.canopynetwork.org/api/auth/csrf")
#
# print("STATUS CODE", csrf_resp.status_code)
# print("HEADERS", csrf_resp.headers)
# print("CSRF TOKEN", csrf_resp.text)
