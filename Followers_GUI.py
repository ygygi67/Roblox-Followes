import requests
import re
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk
import json
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageTk
from io import BytesIO

DEFAULT_TARGET = 3535260140
WEBHOOK_URL = ""  # ใส่ Discord Webhook URL ตรงนี้

current_threads = []
stop_flags = {}
user_status = {}
status_cards = {}
last_sent_state = {}

LOG_FILE = "follow_checker_log.txt"

# ---------------- ฟังก์ชันเสริม ----------------

def get_user_info(user_id):
    """ดึงข้อมูลผู้ใช้จาก Roblox API"""
    try:
        # ข้อมูลพื้นฐาน
        url = f"https://users.roblox.com/v1/users/{user_id}"
        r = requests.get(url)
        if r.status_code != 200:
            return None
        
        user_data = r.json()
        
        # ข้อมูลสถานะออนไลน์
        presence_url = f"https://presence.roblox.com/v1/presence/users"
        presence_r = requests.post(presence_url, json={"userIds": [user_id]})
        presence_data = {}
        if presence_r.status_code == 200:
            presence_info = presence_r.json()
            if presence_info.get("userPresences"):
                presence_data = presence_info["userPresences"][0]
        
        # ข้อมูลเพื่อนและผู้ติดตาม
        friends_url = f"https://friends.roblox.com/v1/users/{user_id}/friends/count"
        friends_r = requests.get(friends_url)
        friends_count = friends_r.json().get("count", 0) if friends_r.status_code == 200 else 0
        
        followers_url = f"https://friends.roblox.com/v1/users/{user_id}/followers/count"
        followers_r = requests.get(followers_url)
        followers_count = followers_r.json().get("count", 0) if followers_r.status_code == 200 else 0
        
        followings_url = f"https://friends.roblox.com/v1/users/{user_id}/followings/count"
        followings_r = requests.get(followings_url)
        followings_count = followings_r.json().get("count", 0) if followings_r.status_code == 200 else 0
        
        # URL รูปโปรไฟล์
        avatar_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=false"
        avatar_r = requests.get(avatar_url)
        avatar_image_url = None
        if avatar_r.status_code == 200:
            avatar_data = avatar_r.json()
            if avatar_data.get("data") and len(avatar_data["data"]) > 0:
                avatar_image_url = avatar_data["data"][0].get("imageUrl")
        
        return {
            "id": user_data.get("id"),
            "name": user_data.get("name"),
            "displayName": user_data.get("displayName"),
            "description": user_data.get("description", "ไม่มีคำอธิบาย"),
            "created": user_data.get("created"),
            "isBanned": user_data.get("isBanned", False),
            "hasVerifiedBadge": user_data.get("hasVerifiedBadge", False),
            "presence": presence_data.get("userPresenceType", 0),  # 0=Offline, 1=Online, 2=InGame, 3=InStudio
            "lastLocation": presence_data.get("lastLocation", "ไม่ทราบ"),
            "friends": friends_count,
            "followers": followers_count,
            "followings": followings_count,
            "avatar_url": avatar_image_url
        }
    except Exception as e:
        print(f"Error getting user info: {e}")
        return None


def download_avatar(url):
    """ดาวน์โหลดรูป Avatar"""
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img = img.resize((80, 80), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
    except:
        pass
    return None


def send_discord_webhook(user_id, is_follow, user_info=None):
    """ส่งการแจ้งเตือนพร้อมข้อมูลละเอียดและรูปโปรไฟล์ไปยัง Discord Webhook"""
    if not WEBHOOK_URL:
        return
    
    try:
        status = "✅ กำลัง Follow" if is_follow else "❌ ไม่ได้ Follow"
        color = 3066993 if is_follow else 15158332  # เขียว : แดง
        
        # สร้าง Embed พื้นฐาน
        embed = {
            "title": f"🔔 การตรวจสอบ Follow - User {user_id}",
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Roblox Follow Checker"}
        }
        
        # เพิ่มข้อมูลถ้ามี
        if user_info:
            presence_status = {
                0: "🔴 Offline",
                1: "🟢 Online", 
                2: "🎮 กำลังเล่นเกม",
                3: "🛠️ อยู่ใน Studio"
            }.get(user_info["presence"], "❓ ไม่ทราบ")
            
            created_date = datetime.fromisoformat(user_info["created"].replace("Z", "+00:00"))
            created_str = created_date.strftime("%d/%m/%Y")
            
            profile_link = f"https://www.roblox.com/users/{user_id}/profile"
            
            embed["description"] = f"**สถานะการ Follow:** {status}\n\n**[🔗 คลิกเพื่อดูโปรไฟล์]({profile_link})**"
            embed["fields"] = [
                {
                    "name": "👤 ชื่อผู้ใช้",
                    "value": f"**{user_info['displayName']}** (@{user_info['name']})",
                    "inline": False
                },
                {
                    "name": "📊 สถานะปัจจุบัน",
                    "value": presence_status,
                    "inline": True
                },
                {
                    "name": "📅 วันที่สร้างบัญชี",
                    "value": created_str,
                    "inline": True
                },
                {
                    "name": "👥 เพื่อน",
                    "value": f"{user_info['friends']:,} คน",
                    "inline": True
                },
                {
                    "name": "📢 ผู้ติดตาม",
                    "value": f"{user_info['followers']:,} คน",
                    "inline": True
                },
                {
                    "name": "➕ กำลังติดตาม",
                    "value": f"{user_info['followings']:,} คน",
                    "inline": True
                }
            ]
            
            # เพิ่มข้อมูลเพิ่มเติม
            extra_info = []
            if user_info["isBanned"]:
                extra_info.append("🚫 ถูกแบน")
            if user_info["hasVerifiedBadge"]:
                extra_info.append("✓ มีตราสัญลักษณ์ยืนยัน")
            
            if extra_info:
                embed["fields"].append({
                    "name": "ℹ️ ข้อมูลเพิ่มเติม",
                    "value": " | ".join(extra_info),
                    "inline": False
                })
            
            if user_info["description"] and user_info["description"] != "ไม่มีคำอธิบาย":
                desc_preview = user_info["description"][:200] + "..." if len(user_info["description"]) > 200 else user_info["description"]
                embed["fields"].append({
                    "name": "📝 คำอธิบายโปรไฟล์",
                    "value": desc_preview,
                    "inline": False
                })
            
            # เพิ่มรูป Avatar
            if user_info["avatar_url"]:
                embed["thumbnail"] = {
                    "url": user_info["avatar_url"]
                }
        else:
            embed["description"] = f"**User ID:** {user_id}\n**สถานะ:** {status}\n\n*ไม่สามารถดึงข้อมูลเพิ่มเติมได้*"
        
        payload = {"embeds": [embed]}
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Webhook Error: {e}")


def log_to_file(message):
    """บันทึกข้อมูลลงไฟล์ log"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass


# ---------------- ฟังก์ชันหลัก ----------------

def extract_user_ids(text):
    """แยก User ID หลายตัวจากข้อความ"""
    matches = re.findall(r"(\d{7,})", text)
    unique_ids = []
    seen = set()
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_ids.append(int(m))
    return unique_ids


def is_following(user_id, target_id=DEFAULT_TARGET):
    url = f"https://friends.roblox.com/v1/users/{user_id}/followings?sortOrder=Asc&limit=100"

    while True:
        r = requests.get(url)
        if r.status_code != 200:
            return False

        data = r.json()
        for user in data["data"]:
            if user["id"] == target_id:
                return True

        if data.get("nextPageCursor"):
            url = f"https://friends.roblox.com/v1/users/{user_id}/followings?sortOrder=Asc&limit=100&cursor={data['nextPageCursor']}"
        else:
            break

    return False


def create_user_card(container, user_id):
    """สร้างการ์ดแสดงข้อมูลผู้ใช้แบบสวยงาม"""
    # กรอบการ์ด
    card_frame = tk.Frame(container, bg="#2b2d42", relief=tk.RAISED, bd=3, highlightthickness=2, highlightbackground="#5865f2")
    card_frame.pack(fill=tk.X, padx=15, pady=8)
    
    # ส่วนหัวการ์ด
    header_frame = tk.Frame(card_frame, bg="#5865f2")
    header_frame.pack(fill=tk.X)
    
    header_label = tk.Label(header_frame,
                           text=f"👤 User ID: {user_id}",
                           font=("Arial", 12, "bold"),
                           bg="#5865f2",
                           fg="white",
                           anchor="w",
                           padx=15,
                           pady=10)
    header_label.pack(side=tk.LEFT)
    
    # ส่วนเนื้อหา
    content_frame = tk.Frame(card_frame, bg="#2b2d42")
    content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # ส่วนซ้าย - รูปโปรไฟล์
    left_frame = tk.Frame(content_frame, bg="#2b2d42")
    left_frame.pack(side=tk.LEFT, padx=10)
    
    # พื้นที่สำหรับรูป Avatar
    avatar_label = tk.Label(left_frame, 
                           text="📷",
                           font=("Arial", 40),
                           bg="#1e1e2e",
                           fg="#888888",
                           width=5,
                           height=3)
    avatar_label.pack()
    
    # ส่วนขวา - ข้อมูล
    right_frame = tk.Frame(content_frame, bg="#2b2d42")
    right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
    
    # ชื่อผู้ใช้
    name_label = tk.Label(right_frame,
                         text="🔄 กำลังโหลดข้อมูล...",
                         font=("Arial", 11, "bold"),
                         bg="#2b2d42",
                         fg="white",
                         anchor="w")
    name_label.pack(fill=tk.X, pady=2)
    
    # สถานะ Follow
    status_label = tk.Label(right_frame,
                           text="📊 สถานะ: กำลังตรวจสอบ...",
                           font=("Arial", 11, "bold"),
                           bg="#2b2d42",
                           fg="#aaaaaa",
                           anchor="w")
    status_label.pack(fill=tk.X, pady=2)
    
    # ข้อมูลเพิ่มเติม
    info_label = tk.Label(right_frame,
                         text="",
                         font=("Arial", 9),
                         bg="#2b2d42",
                         fg="#cccccc",
                         anchor="w",
                         justify=tk.LEFT)
    info_label.pack(fill=tk.X, pady=2)
    
    # เวลาอัพเดท
    time_label = tk.Label(right_frame,
                         text="⏰ อัพเดทล่าสุด: -",
                         font=("Arial", 9),
                         bg="#2b2d42",
                         fg="#888888",
                         anchor="w")
    time_label.pack(fill=tk.X, pady=(5, 0))
    
    return card_frame, avatar_label, name_label, status_label, info_label, time_label


def loop_check(user_id, container, status_cards, interval=5):
    """ตรวจสอบ User ซ้ำๆ และอัพเดทการ์ด"""
    card_frame, avatar_label, name_label, status_label, info_label, time_label = create_user_card(container, user_id)
    status_cards[user_id] = (card_frame, avatar_label, name_label, status_label, info_label, time_label)
    
    avatar_photo = None
    
    while not stop_flags.get(user_id, False):
        try:
            result = is_following(user_id)
            user_status[user_id] = result
            
            # ดึงข้อมูลผู้ใช้
            user_info = get_user_info(user_id)
            
            # อัพเดทรูป Avatar (ครั้งเดียว)
            if user_info and user_info["avatar_url"] and avatar_photo is None:
                avatar_photo = download_avatar(user_info["avatar_url"])
                if avatar_photo:
                    avatar_label.config(image=avatar_photo, text="")
                    avatar_label.image = avatar_photo  # เก็บ reference
            
            # เปลี่ยนสีตามสถานะ
            if result:
                status_text = "✅ กำลัง Follow อยู่!"
                color = "#00ff00"
                bg_color = "#1a3a1a"
                border_color = "#00ff00"
            else:
                status_text = "❌ ไม่ได้ Follow"
                color = "#ff4444"
                bg_color = "#3a1a1a"
                border_color = "#ff4444"
            
            # อัพเดทข้อมูล
            if user_info:
                name_label.config(text=f"👤 {user_info['displayName']} (@{user_info['name']})")
                
                presence_status = {
                    0: "🔴 Offline",
                    1: "🟢 Online", 
                    2: "🎮 กำลังเล่นเกม",
                    3: "🛠️ อยู่ใน Studio"
                }.get(user_info["presence"], "❓ ไม่ทราบ")
                
                info_text = f"{presence_status}\n"
                info_text += f"👥 เพื่อน: {user_info['friends']:,} | 📢 ผู้ติดตาม: {user_info['followers']:,} | ➕ ติดตาม: {user_info['followings']:,}"
                info_label.config(text=info_text)
            
            # อัพเดทสถานะ
            card_frame.config(bg=bg_color, highlightbackground=border_color)
            status_label.config(text=f"📊 {status_text}", 
                              fg=color, 
                              bg=bg_color,
                              font=("Arial", 12, "bold"))
            
            # อัพเดทส่วนอื่นๆ
            for widget in [name_label, info_label, time_label]:
                widget.config(bg=bg_color)
            
            current_time = datetime.now().strftime("%H:%M:%S")
            time_label.config(text=f"⏰ อัพเดทล่าสุด: {current_time}")
            
            # ส่ง Webhook เฉพาะเมื่อมีการเปลี่ยนแปลงข้อมูลสำคัญ
            current_state = {
                "is_following": result,
                "presence": user_info["presence"] if user_info else None,
                "followers": user_info["followers"] if user_info else None,
                "followings": user_info["followings"] if user_info else None,
                "friends": user_info["friends"] if user_info else None,
            }
            last_state = last_sent_state.get(user_id)
            if last_state != current_state:
                if result:
                    send_discord_webhook(user_id, True, user_info)
                    log_to_file(f"ผู้ใช้ {user_id} ({user_info['name'] if user_info else 'Unknown'}) กำลัง Follow {DEFAULT_TARGET}")
                else:
                    send_discord_webhook(user_id, False, user_info)
                    log_to_file(f"ผู้ใช้ {user_id} ({user_info['name'] if user_info else 'Unknown'}) ไม่ได้ Follow {DEFAULT_TARGET}")
                last_sent_state[user_id] = current_state
                
        except Exception as e:
            status_label.config(text=f"⚠️ ERROR: {str(e)[:30]}", 
                              fg="#ff9900",
                              bg="#3a2a1a")
            card_frame.config(bg="#3a2a1a", highlightbackground="#ff9900")
            log_to_file(f"ERROR - User {user_id}: {str(e)}")

        # หน่วงเวลา
        for _ in range(interval * 10):
            if stop_flags.get(user_id, False):
                return
            threading.Event().wait(0.1)


def start_checking_multi(text, container, main_status_label):
    """เริ่มตรวจสอบหลาย User พร้อมกัน"""
    global current_threads, stop_flags, user_status, status_cards
    
    user_ids = extract_user_ids(text)
    if not user_ids:
        from tkinter import messagebox
        messagebox.showerror("ข้อผิดพลาด", "❌ ไม่พบ UserID ในข้อความ")
        return
    
    # คัดเฉพาะ User ID ที่ยังไม่ได้ตรวจสอบอยู่ เพื่อไม่สร้างการ์ดซ้ำ
    existing_ids = set(status_cards.keys())
    new_user_ids = [uid for uid in user_ids if uid not in existing_ids]
    if not new_user_ids:
        main_status_label.config(text=f"📊 กำลังตรวจสอบ {len(existing_ids)} คน (ไม่มีผู้ใช้ใหม่)")
        return
    
    main_status_label.config(text=f"📊 เพิ่มการตรวจสอบใหม่ {len(new_user_ids)} คน (รวม {len(existing_ids) + len(new_user_ids)} คน)")
    log_to_file(f"เพิ่มการตรวจสอบ {len(new_user_ids)} User: {new_user_ids}")
    
    for user_id in new_user_ids:
        stop_flags[user_id] = False
        thread = threading.Thread(
            target=loop_check,
            args=(user_id, container, status_cards),
            daemon=True
        )
        thread.start()
        current_threads.append((user_id, thread))


def stop_all_threads():
    """หยุดการทำงานทั้งหมด"""
    global stop_flags, current_threads
    
    for user_id in stop_flags:
        stop_flags[user_id] = True
    
    for user_id, thread in current_threads:
        if thread.is_alive():
            thread.join(timeout=0.1)
    
    current_threads = []
    stop_flags = {}


# ---------------- GUI ----------------

root = tk.Tk()
root.title("🎮 Roblox Follow Checker - Enhanced")
root.geometry("800x750")
root.configure(bg="#1e1e2e")

# สไตล์
style = ttk.Style()
style.theme_use("clam")
style.configure("TButton", 
                background="#5865f2", 
                foreground="white",
                borderwidth=0,
                focuscolor="none",
                font=("Arial", 11, "bold"))
style.map("TButton", background=[("active", "#4752c4")])

# Header
title_frame = tk.Frame(root, bg="#5865f2", height=70)
title_frame.pack(fill=tk.X)
title_frame.pack_propagate(False)

title = tk.Label(title_frame, 
                 text="🎮 Roblox Follow Checker", 
                 font=("Arial", 20, "bold"),
                 bg="#5865f2",
                 fg="white")
title.pack(pady=15)

# Status Bar
status_label = tk.Label(root, 
                        text="📊 พร้อมใช้งาน",
                        font=("Arial", 10),
                        bg="#2b2d42",
                        fg="#00ff00",
                        anchor="w",
                        padx=10)
status_label.pack(fill=tk.X)

# Input Section
input_frame = tk.Frame(root, bg="#1e1e2e")
input_frame.pack(pady=15)

label = tk.Label(input_frame, 
                 text="💬 ใส่ UserID หรือ ลิงก์ (สามารถใส่หลาย User ได้):",
                 font=("Arial", 11),
                 bg="#1e1e2e",
                 fg="white")
label.pack()

input_entry = tk.Entry(input_frame, 
                       width=60, 
                       font=("Arial", 12),
                       bg="#2b2d42",
                       fg="white",
                       insertbackground="white",
                       relief=tk.FLAT,
                       bd=2)
input_entry.pack(pady=8, ipady=5)

# Scrollable Container สำหรับการ์ด
canvas_frame = tk.Frame(root, bg="#1e1e2e")
canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

canvas = tk.Canvas(canvas_frame, bg="#0d1117", highlightthickness=0)
scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
scrollable_frame = tk.Frame(canvas, bg="#0d1117")

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# ปุ่มควบคุม
button_frame = tk.Frame(root, bg="#1e1e2e")
button_frame.pack(pady=10)

def paste_and_start():
    try:
        text = root.clipboard_get()
        input_entry.delete(0, tk.END)
        input_entry.insert(0, text)
        start_checking_multi(text, scrollable_frame, status_label)
    except:
        from tkinter import messagebox
        messagebox.showerror("ข้อผิดพลาด", "⚠️ ไม่สามารถวางข้อความได้")

paste_btn = ttk.Button(button_frame, 
                       text="📋 วางข้อความ & เริ่ม (Paste)", 
                       command=paste_and_start,
                       width=25)
paste_btn.grid(row=0, column=0, padx=5)

start_btn = ttk.Button(button_frame,
                       text="▶️ เริ่มตรวจสอบ (Start)",
                       command=lambda: start_checking_multi(input_entry.get(), scrollable_frame, status_label),
                       width=25)
start_btn.grid(row=0, column=1, padx=5)

style.configure("Stop.TButton", background="#ed4245", foreground="white")
style.map("Stop.TButton", background=[("active", "#c03537")])

stop_btn = ttk.Button(button_frame,
                      text="⏹️ หยุดการตรวจสอบ (STOP)",
                      command=stop_all_threads,
                      style="Stop.TButton",
                      width=25)
stop_btn.grid(row=1, column=0, columnspan=2, pady=8)

# ข้อความด้านล่าง
footer = tk.Label(root,
                  text="💡 Tip: สามารถใส่หลาย User ID พร้อมกัน คั่นด้วยช่องว่างหรือบรรทัดใหม่",
                  font=("Arial", 9),
                  bg="#1e1e2e",
                  fg="#888888")
footer.pack(pady=5)

# สร้างไฟล์ log ถ้ายังไม่มี
Path(LOG_FILE).touch(exist_ok=True)

root.mainloop()