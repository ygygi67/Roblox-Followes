import requests
import re
import threading
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import os

WEBHOOK_URL = ""  # ใส่ Discord Webhook URL ตรงนี้

current_threads = []
stop_flags = {}
user_status = {}
last_sent_state = {}

LOG_FILE = "profile_tracker_log.txt"

# ---------------- ฟังก์ชันเสริม ----------------

def clear_screen():
    """ล้างหน้าจอ"""
    os.system('clear' if os.name != 'nt' else 'cls')


def get_user_info(user_id):
    """ดึงข้อมูลผู้ใช้จาก Roblox API"""
    try:
        # ข้อมูลพื้นฐาน
        url = f"https://users.roblox.com/v1/users/{user_id}"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        
        user_data = r.json()
        
        # ข้อมูลสถานะออนไลน์
        presence_url = f"https://presence.roblox.com/v1/presence/users"
        presence_r = requests.post(presence_url, json={"userIds": [user_id]}, timeout=10)
        presence_data = {}
        game_details = None
        
        if presence_r.status_code == 200:
            presence_info = presence_r.json()
            if presence_info.get("userPresences"):
                presence_data = presence_info["userPresences"][0]
                
                # ถ้ากำลังเล่นเกม ให้ดึงข้อมูลเกม
                if presence_data.get("placeId"):
                    place_id = presence_data.get("placeId")
                    game_url = f"https://games.roblox.com/v1/games?universeIds={presence_data.get('universeId', '')}"
                    try:
                        game_r = requests.get(game_url, timeout=5)
                        if game_r.status_code == 200:
                            game_data = game_r.json()
                            if game_data.get("data"):
                                game_details = game_data["data"][0]
                    except:
                        pass
        
        # ข้อมูลเพื่อนและผู้ติดตาม
        friends_url = f"https://friends.roblox.com/v1/users/{user_id}/friends/count"
        friends_r = requests.get(friends_url, timeout=10)
        friends_count = friends_r.json().get("count", 0) if friends_r.status_code == 200 else 0
        
        followers_url = f"https://friends.roblox.com/v1/users/{user_id}/followers/count"
        followers_r = requests.get(followers_url, timeout=10)
        followers_count = followers_r.json().get("count", 0) if followers_r.status_code == 200 else 0
        
        followings_url = f"https://friends.roblox.com/v1/users/{user_id}/followings/count"
        followings_r = requests.get(followings_url, timeout=10)
        followings_count = followings_r.json().get("count", 0) if followings_r.status_code == 200 else 0
        
        # URL รูปโปรไฟล์
        avatar_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=false"
        avatar_r = requests.get(avatar_url, timeout=10)
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
            "presence": presence_data.get("userPresenceType", 0),
            "lastLocation": presence_data.get("lastLocation", "ไม่ทราบ"),
            "lastOnline": presence_data.get("lastOnline", ""),
            "placeId": presence_data.get("placeId"),
            "gameId": presence_data.get("gameId"),
            "game_name": game_details.get("name") if game_details else None,
            "friends": friends_count,
            "followers": followers_count,
            "followings": followings_count,
            "avatar_url": avatar_image_url
        }
    except Exception as e:
        print(f"⚠️ Error getting user info: {e}")
        return None


def send_discord_webhook(user_id, user_info, change_type="update"):
    """ส่งการแจ้งเตือนพร้อมข้อมูลละเอียดไปยัง Discord Webhook"""
    if not WEBHOOK_URL:
        return
    
    try:
        # กำหนดสีตามประเภทการเปลี่ยนแปลง
        color_map = {
            "online": 3066993,      # เขียว - ออนไลน์
            "offline": 10197915,    # เทา - ออฟไลน์
            "playing": 3447003,     # น้ำเงิน - กำลังเล่นเกม
            "studio": 15844367,     # ส้ม - อยู่ใน Studio
            "update": 5793266       # ม่วง - อัพเดทข้อมูล
        }
        
        color = color_map.get(change_type, 5793266)
        
        embed = {
            "title": f"📊 Roblox Profile Tracker - {user_id}",
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Roblox Profile Tracker"}
        }
        
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
            
            # สร้างคำอธิบาย
            description = f"**[🔗 ดูโปรไฟล์]({profile_link})**\n\n"
            
            # แสดงข้อมูลเกมถ้ากำลังเล่นอยู่
            if user_info["presence"] == 2 and user_info["game_name"]:
                game_link = f"https://www.roblox.com/games/{user_info['placeId']}"
                description += f"🎮 **กำลังเล่น:** [{user_info['game_name']}]({game_link})\n\n"
            
            embed["description"] = description
            
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
            
            # แสดง Last Online สำหรับคนที่ออฟไลน์
            if user_info["presence"] == 0 and user_info["lastOnline"]:
                try:
                    last_online = datetime.fromisoformat(user_info["lastOnline"].replace("Z", "+00:00"))
                    last_online_str = last_online.strftime("%d/%m/%Y %H:%M:%S")
                    embed["fields"].append({
                        "name": "🕐 ออนไลน์ครั้งล่าสุด",
                        "value": last_online_str,
                        "inline": False
                    })
                except:
                    pass
            
            # ข้อมูลเพิ่มเติม
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
            
            if user_info["avatar_url"]:
                embed["thumbnail"] = {"url": user_info["avatar_url"]}
        else:
            embed["description"] = f"**User ID:** {user_id}\n\n*ไม่สามารถดึงข้อมูลได้*"
        
        payload = {"embeds": [embed]}
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Webhook Error: {e}")


def log_to_file(message):
    """บันทึกข้อมูลลงไฟล์ log"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass


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


def display_user_status():
    """แสดงสถานะของผู้ใช้ทั้งหมดบนหน้าจอ"""
    clear_screen()
    print("=" * 80)
    print("📊 Roblox Profile Tracker - Termux Edition".center(80))
    print("=" * 80)
    print()
    
    if not user_status:
        print("⏳ กำลังรอข้อมูล...")
        return
    
    for user_id, status_info in user_status.items():
        user_info = status_info.get("user_info")
        last_update = status_info.get("last_update", "-")
        
        border = "+" + "-" * 50 + "+"
        print(border)
        
        if user_info:
            presence_status = {
                0: "🔴 OFFLINE",
                1: "🟢 ONLINE", 
                2: "🎮 กำลังเล่นเกม",
                3: "🛠️ อยู่ใน STUDIO"
            }.get(user_info["presence"], "❓ ไม่ทราบ")
            
            print(f" {presence_status.center(50)} ")
            print(border)
            print(f" 👤 User ID : {user_id:<25} ")
            print(f" 📝 ชื่อ : {user_info['displayName']} (@{user_info['name']}){' ' * (60 - len(user_info['displayName']) - len(user_info['name']))} ")
            
            # แสดงข้อมูลเกมถ้ากำลังเล่นอยู่
            if user_info["presence"] == 2 and user_info["game_name"]:
                game_name = user_info["game_name"]
                if len(game_name) > 60:
                    game_name = game_name[:57] + "..."
                print(f"| 🎮 กำลังเล่น : {game_name}{' ' * (25 - len(game_name))} |")
            
            print(f" 👥 เพื่อน : {user_info['friends']:,}{' ' * (25 - len(str(user_info['friends'])))} ")
            print(f" 📢 ผู้ติดตาม : {user_info['followers']:,}{' ' * (25 - len(str(user_info['followers'])))} ")
            print(f" ➕ กำลังติดตาม : {user_info['followings']:,}{' ' * (25 - len(str(user_info['followings'])))} ")
            
            # แสดง Last Online สำหรับคนที่ออฟไลน์
            if user_info["presence"] == 0 and user_info["lastOnline"]:
                try:
                    last_online = datetime.fromisoformat(user_info["lastOnline"].replace("Z", "+00:00"))
                    last_online_str = last_online.strftime("%d/%m/%Y %H:%M")
                    print(f" 🕐 ออนไลน์ครั้งล่าสุด : {last_online_str}{' ' * (25 - len(last_online_str))} ")
                except:
                    pass
        else:
            print(f"| {'⚠️ ไม่สามารถดึงข้อมูลได้'.center(76)} |")
            print(border)
            print(f"| 👤 User ID: {user_id:<63} |")
        
        print(f" ⏰ อัพเดทล่าสุด : {last_update:<59} ")
        print(border)
        print()
    
    print(f"\n📊 กำลังติดตาม: {len(user_status)} คน")
    print("💡 กด Ctrl+C เพื่อหยุดโปรแกรม")
    print()


def loop_check(user_id, interval=5):
    """ตรวจสอบโปรไฟล์ User ซ้ำๆ"""
    while not stop_flags.get(user_id, False):
        try:
            user_info = get_user_info(user_id)
            current_time = datetime.now().strftime("%H:%M:%S")
            
            user_status[user_id] = {
                "user_info": user_info,
                "last_update": current_time
            }
            
            # ตรวจสอบการเปลี่ยนแปลง
            current_state = {
                "presence": user_info["presence"] if user_info else None,
                "followers": user_info["followers"] if user_info else None,
                "followings": user_info["followings"] if user_info else None,
                "friends": user_info["friends"] if user_info else None,
                "game_name": user_info["game_name"] if user_info else None,
            }
            
            last_state = last_sent_state.get(user_id)
            
            # ส่ง Webhook เมื่อมีการเปลี่ยนแปลง
            if last_state != current_state:
                change_type = "update"
                
                # ระบุประเภทการเปลี่ยนแปลง
                if last_state:
                    if last_state["presence"] != current_state["presence"]:
                        if current_state["presence"] == 0:
                            change_type = "offline"
                        elif current_state["presence"] == 1:
                            change_type = "online"
                        elif current_state["presence"] == 2:
                            change_type = "playing"
                        elif current_state["presence"] == 3:
                            change_type = "studio"
                
                send_discord_webhook(user_id, user_info, change_type)
                
                if user_info:
                    log_to_file(f"ผู้ใช้ {user_id} ({user_info['name']}) - สถานะเปลี่ยนเป็น: {current_state['presence']}")
                
                last_sent_state[user_id] = current_state
            
            # แสดงผลทุกครั้งหลังจากอัพเดท
            display_user_status()
                
        except Exception as e:
            print(f"⚠️ ERROR (User {user_id}): {e}")
            log_to_file(f"ERROR - User {user_id}: {str(e)}")

        # หน่วงเวลา
        for _ in range(interval):
            if stop_flags.get(user_id, False):
                return
            time.sleep(1)


def start_tracking(user_ids):
    """เริ่มติดตามหลาย User พร้อมกัน"""
    global current_threads, stop_flags
    
    log_to_file(f"เริ่มติดตาม {len(user_ids)} User: {user_ids}")
    print(f"\n🔄 เริ่มติดตามโปรไฟล์ {len(user_ids)} คน...")
    print(f"👥 User IDs: {', '.join(map(str, user_ids))}\n")
    
    for user_id in user_ids:
        stop_flags[user_id] = False
        thread = threading.Thread(
            target=loop_check,
            args=(user_id,),
            daemon=True
        )
        thread.start()
        current_threads.append((user_id, thread))


def stop_all_threads():
    """หยุดการทำงานทั้งหมด"""
    global stop_flags
    
    print("\n⏹️ กำลังหยุดการติดตาม...")
    for user_id in stop_flags:
        stop_flags[user_id] = True
    
    time.sleep(1)
    print("✅ หยุดการทำงานเรียบร้อย")


def main():
    """ฟังก์ชันหลัก"""
    clear_screen()
    print("=" * 50)
    print("📊 Roblox Profile Tracker - Termux Edition".center(40))
    print("=" * 50)
    print()
    print("📝 โปรแกรมนี้จะติดตามสถานะโปรไฟล์ของผู้ใช้ Roblox")
    print("   - สถานะออนไลน์/ออฟไลน์")
    print("   - เกมที่กำลังเล่น")
    print("   - จำนวนเพื่อน/ผู้ติดตาม")
    print("   - และอื่นๆ")
    print()
    
    # ตั้งค่า Webhook (ถ้ายังไม่ได้ตั้ง)
    global WEBHOOK_URL
    if not WEBHOOK_URL:
        print("⚙️ ตั้งค่า Discord Webhook (กด Enter เพื่อข้าม):")
        webhook_input = input("   Webhook URL: ").strip()
        if webhook_input:
            WEBHOOK_URL = webhook_input
            print("✅ ตั้งค่า Webhook เรียบร้อย!\n")
        else:
            print("⚠️ ข้ามการตั้งค่า Webhook (จะไม่ส่งการแจ้งเตือนไป Discord)\n")
    
    # รับ User ID
    print("💬 ใส่ UserID หรือ ลิงก์ของผู้ใช้ที่ต้องการติดตาม:")
    print("   (สามารถใส่หลาย User ได้, คั่นด้วยเว้นวรรค)")
    user_input = input("   > ").strip()
    
    if not user_input:
        print("❌ ไม่พบ UserID")
        return
    
    user_ids = extract_user_ids(user_input)
    
    if not user_ids:
        print("❌ ไม่พบ UserID ที่ถูกต้อง")
        return
    
    try:
        start_tracking(user_ids)
        
        # รอจนกว่าจะกด Ctrl+C
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        stop_all_threads()
        print("\n\n👋 ขอบคุณที่ใช้งาน!")


if __name__ == "__main__":
    # สร้างไฟล์ log ถ้ายังไม่มี
    Path(LOG_FILE).touch(exist_ok=True)
    
    try:
        main()
    except Exception as e:
        print(f"\n❌ เกิดข้อผิดพลาด: {e}")
        log_to_file(f"CRITICAL ERROR: {str(e)}")
