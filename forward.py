import os, json, time, requests

TG = os.environ["TG_TOKEN"]
BT = os.environ["BALE_TOKEN"]
BC = os.environ["BALE_CHAT"]
RT = os.environ.get("RUBIKA_TOKEN", "")
RC = os.environ.get("RUBIKA_CHAT", "")
tg = f"https://api.telegram.org/bot{TG}"
bale = f"https://tapi.bale.ai/bot{BT}"
rub = f"https://botapi.rubika.ir/v3/{RT}"
MAX_WAIT = 900  # حداکثر صبر برای ویرایش پست‌یار (عکس و ویدیو)
SETTLE = 60     # صبر برای کامل شدن آلبوم‌های بدون ویرایش

RUBIKA_REPLACE = {
    "@vahid_abasiii": "@vahiid_abasii",
    "@iman_tavakoli": "@iman_tavakolii",
}
BALE_REPLACE = {
    "@iman_tavakoli": "@iman_tavakolii",
}

def fix(t, table):
    for a, b in table.items():
        t = t.replace(a, b)
    return t

KINDS = [("photo", "sendPhoto", "Image"), ("video", "sendVideo", "Video"),
         ("document", "sendDocument", "File"), ("audio", "sendAudio", "Music"),
         ("voice", "sendVoice", "Voice"), ("animation", "sendAnimation", "Gif")]
MAP_FILE = "map.json"

try:
    with open(MAP_FILE) as f:
        MAP = json.load(f)
except Exception:
    MAP = {}

def bale_send(key, method, text, name, data, reply):
    payload = {"chat_id": BC}
    if reply:
        payload["reply_to_message_id"] = reply
    if key is None:
        payload["text"] = text
        r = requests.post(f"{bale}/sendMessage", json=payload)
    else:
        payload["caption"] = text
        r = requests.post(f"{bale}/{method}", data=payload,
                          files={key: (name, data)})
    print("bale", r.status_code, r.text[:150])
    j = r.json()
    if not j.get("ok"):
        raise Exception(j)
    return j["result"]["message_id"]

def bale_album(items, caption, reply):
    media, files = [], {}
    for i, (p, d) in enumerate(items):
        key, method, rtype, name, data = d
        att = f"f{i}"
        m = {"type": "photo" if key == "photo" else "video",
             "media": f"attach://{att}"}
        if i == 0 and caption:
            m["caption"] = caption
        media.append(m)
        files[att] = (name, data)
    payload = {"chat_id": BC, "media": json.dumps(media)}
    if reply:
        payload["reply_to_message_id"] = reply
    r = requests.post(f"{bale}/sendMediaGroup", data=payload, files=files)
    print("bale album", r.status_code, r.text[:150])
    j = r.json()
    if not j.get("ok"):
        raise Exception(j)
    return [m["message_id"] for m in j["result"]]

def rubika_send(rtype, text, name, data, reply):
    if not (RT and RC):
        return None
    if rtype is None:
        body = {"chat_id": RC, "text": text}
        if reply:
            body["reply_to_message_id"] = reply
        r = requests.post(f"{rub}/sendMessage", json=body)
    else:
        u = requests.post(f"{rub}/requestSendFile",
                          json={"type": rtype}).json()
        up = requests.post(u["data"]["upload_url"],
                           files={"file": (name, data)}).json()
        body = {"chat_id": RC, "file_id": up["data"]["file_id"],
                "text": text}
        if reply:
            body["reply_to_message_id"] = reply
        r = requests.post(f"{rub}/sendFile", json=body)
    print("rubika", r.status_code, r.text[:200])
    j = r.json()
    if j.get("status") != "OK":
        raise Exception(j)
    return j["data"].get("message_id")

def run(fn, *a):
    reply = a[-1]
    try:
        return fn(*a)
    except Exception as e:
        print(fn.__name__, "error:", e)
        if reply:
            try:
                return fn(*a[:-1], None)
            except Exception as e2:
                print(fn.__name__, "retry error:", e2)
    return None

def download(p):
    for k, m, t in KINDS:
        if k in p:
            obj = p[k][-1] if k == "photo" else p[k]
            info = requests.get(f"{tg}/getFile",
                                params={"file_id": obj["file_id"]}).json()
            if not info.get("ok"):
                print("file error", info.get("description"))
                return None
            path = info["result"]["file_path"]
            data = requests.get(
                f"https://api.telegram.org/file/bot{TG}/{path}").content
            return k, m, t, os.path.basename(path), data
    return None

def handle(p):
    text = p.get("text") or p.get("caption") or ""
    rt = p.get("reply_to_message")
    prev = MAP.get(str(rt["message_id"]), {}) if rt else {}
    d = download(p)
    if d is None:
        if not p.get("text"):
            print("unsupported or download failed")
            return
        key = method = rtype = name = data = None
    else:
        key, method, rtype, name, data = d
    b = run(bale_send, key, method, fix(text, BALE_REPLACE),
            name, data, prev.get("bale"))
    r = run(rubika_send, rtype, fix(text, RUBIKA_REPLACE),
            name, data, prev.get("rubika"))
    MAP[str(p["message_id"])] = {"bale": b, "rubika": r}

def handle_group(posts):
    posts = sorted(posts, key=lambda x: x["message_id"])
    caption = ""
    for p in posts:
        if p.get("caption"):
            caption = p["caption"]
    rt = next((p["reply_to_message"] for p in posts
               if p.get("reply_to_message")), None)
    prev = MAP.get(str(rt["message_id"]), {}) if rt else {}
    items = []
    for p in posts:
        d = download(p)
        if d:
            items.append((p, d))
    if not items:
        print("group: nothing to send")
        return
    n = len(items)
    bale_ids = [None] * n
    rubika_ids = [None] * n

    cap_b = fix(caption, BALE_REPLACE)
    done = False
    if n >= 2 and all(d[0] in ("photo", "video") for _, d in items):
        try:
            ids = bale_album(items, cap_b, prev.get("bale"))
            bale_ids = (ids + [None] * n)[:n]
            done = True
        except Exception as e:
            print("bale album failed, sending one by one:", e)
    if not done:
        for i, (p, d) in enumerate(items):
            key, method, rtype, name, data = d
            text = cap_b if i == n - 1 else ""
            bale_ids[i] = run(bale_send, key, method, text, name, data,
                              prev.get("bale") if i == 0 else None)

    cap_r = fix(caption, RUBIKA_REPLACE)
    for i, (p, d) in enumerate(items):
        key, method, rtype, name, data = d
        text = cap_r if i == n - 1 else ""
        rubika_ids[i] = run(rubika_send, rtype, text, name, data,
                            prev.get("rubika") if i == 0 else None)

    for i, (p, d) in enumerate(items):
        MAP[str(p["message_id"])] = {"bale": bale_ids[i],
                                     "rubika": rubika_ids[i]}

def needs_edit(p):
    return bool(p.get("photo") or p.get("video"))

if RT and not RC:
    try:
        print("RUBIKA UPDATES:",
              requests.post(f"{rub}/getUpdates", json={"limit": 20}).text)
    except Exception as e:
        print("rubika updates error:", e)

allowed = '["channel_post","edited_channel_post"]'
ups = requests.get(f"{tg}/getUpdates",
                   params={"allowed_updates": allowed}).json().get("result", [])

latest, first_uid, edited = {}, {}, set()
for u in ups:
    p = u.get("channel_post") or u.get("edited_channel_post")
    if not p:
        continue
    mid = str(p["message_id"])
    latest[mid] = p
    if u.get("edited_channel_post"):
        edited.add(mid)
    first_uid.setdefault(mid, u["update_id"])

groups, singles = {}, []
for mid, p in latest.items():
    gid = p.get("media_group_id")
    if gid:
        groups.setdefault(gid, []).append(p)
    else:
        singles.append((mid, p))

now = time.time()
pending = []

for mid, p in singles:
    if mid in MAP:
        continue
    if mid not in edited and needs_edit(p) and now - p["date"] < MAX_WAIT:
        pending.append(first_uid[mid])
        continue
    handle(p)

for gid, posts in groups.items():
    mids = [str(p["message_id"]) for p in posts]
    if all(m in MAP for m in mids):
        continue
    newest = max(p["date"] for p in posts)
    if not any(m in edited for m in mids):
        wait = MAX_WAIT if any(needs_edit(p) for p in posts) else SETTLE
        if now - newest < wait:
            pending.extend(first_uid[m] for m in mids)
            continue
    handle_group([p for p in posts if str(p["message_id"]) not in MAP])

if ups:
    offset = min(pending) if pending else ups[-1]["update_id"] + 1
    requests.get(f"{tg}/getUpdates",
                 params={"offset": offset, "allowed_updates": allowed})

keys = list(MAP)[-500:]
with open(MAP_FILE, "w") as f:
    json.dump({k: MAP[k] for k in keys}, f)
