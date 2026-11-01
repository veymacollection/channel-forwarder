import os, requests

TG = os.environ["TG_TOKEN"]
BT = os.environ["BALE_TOKEN"]
CHAT = os.environ["BALE_CHAT"]
tg = f"https://api.telegram.org/bot{TG}"
bale = f"https://tapi.bale.ai/bot{BT}"
KINDS = [("photo", "sendPhoto"), ("video", "sendVideo"),
         ("document", "sendDocument"), ("audio", "sendAudio"),
         ("voice", "sendVoice"), ("animation", "sendAnimation")]

def send(p):
    if p.get("text"):
        return requests.post(f"{bale}/sendMessage",
                             json={"chat_id": CHAT, "text": p["text"]})
    for key, method in KINDS:
        if key in p:
            obj = p[key][-1] if key == "photo" else p[key]
            info = requests.get(f"{tg}/getFile",
                                params={"file_id": obj["file_id"]}).json()
            if not info.get("ok"):
                print("file error", info.get("description"))
                return None
            path = info["result"]["file_path"]
            data = requests.get(
                f"https://api.telegram.org/file/bot{TG}/{path}").content
            return requests.post(
                f"{bale}/{method}",
                data={"chat_id": CHAT, "caption": p.get("caption", "")},
                files={key: (os.path.basename(path), data)})
    print("unsupported type")

allowed = '["channel_post"]'
r = requests.get(f"{tg}/getUpdates",
                 params={"allowed_updates": allowed}).json()
ups = r.get("result", [])
for u in ups:
    p = u.get("channel_post")
    if p:
        res = send(p)
        print(u["update_id"], res.status_code if res is not None else "skipped")
if ups:
    requests.get(f"{tg}/getUpdates",
                 params={"offset": ups[-1]["update_id"] + 1,
                         "allowed_updates": allowed})
