import os, requests

TG = os.environ["TG_TOKEN"]
BT = os.environ["BALE_TOKEN"]
BC = os.environ["BALE_CHAT"]
RT = os.environ.get("RUBIKA_TOKEN", "")
RC = os.environ.get("RUBIKA_CHAT", "")
tg = f"https://api.telegram.org/bot{TG}"
bale = f"https://tapi.bale.ai/bot{BT}"
rub = f"https://botapi.rubika.ir/v3/{RT}"
KINDS = [("photo", "sendPhoto", "Image"), ("video", "sendVideo", "Video"),
         ("document", "sendDocument", "File"), ("audio", "sendAudio", "Music"),
         ("voice", "sendVoice", "Voice"), ("animation", "sendAnimation", "Gif")]

def bale_send(key, method, text, name, data):
    if key is None:
        r = requests.post(f"{bale}/sendMessage",
                          json={"chat_id": BC, "text": text})
    else:
        r = requests.post(f"{bale}/{method}",
                          data={"chat_id": BC, "caption": text},
                          files={key: (name, data)})
    print("bale", r.status_code)

def rubika_send(rtype, text, name, data):
    if not (RT and RC):
        return
    if rtype is None:
        r = requests.post(f"{rub}/sendMessage",
                          json={"chat_id": RC, "text": text})
    else:
        u = requests.post(f"{rub}/requestSendFile",
                          json={"type": rtype}).json()
        up = requests.post(u["data"]["upload_url"],
                           files={"file": (name, data)}).json()
        r = requests.post(f"{rub}/sendFile",
                          json={"chat_id": RC,
                                "file_id": up["data"]["file_id"],
                                "text": text})
    print("rubika", r.status_code, r.text[:200])

def run(fn, *a):
    try:
        fn(*a)
    except Exception as e:
        print(fn.__name__, "error:", e)

def handle(p):
    text = p.get("text") or p.get("caption") or ""
    for key, method, rtype in KINDS:
        if key in p:
            obj = p[key][-1] if key == "photo" else p[key]
            info = requests.get(f"{tg}/getFile",
                                params={"file_id": obj["file_id"]}).json()
            if not info.get("ok"):
                print("file error", info.get("description"))
                return
            path = info["result"]["file_path"]
            data = requests.get(
                f"https://api.telegram.org/file/bot{TG}/{path}").content
            name = os.path.basename(path)
            run(bale_send, key, method, text, name, data)
            run(rubika_send, rtype, text, name, data)
            return
    if p.get("text"):
        run(bale_send, None, None, text, None, None)
        run(rubika_send, None, text, None, None)

if RT and not RC:
    try:
        print("RUBIKA UPDATES:",
              requests.post(f"{rub}/getUpdates", json={"limit": 20}).text)
    except Exception as e:
        print("rubika updates error:", e)

allowed = '["channel_post"]'
ups = requests.get(f"{tg}/getUpdates",
                   params={"allowed_updates": allowed}).json().get("result", [])
for u in ups:
    if u.get("channel_post"):
        handle(u["channel_post"])
if ups:
    requests.get(f"{tg}/getUpdates",
                 params={"offset": ups[-1]["update_id"] + 1,
                         "allowed_updates": allowed})
