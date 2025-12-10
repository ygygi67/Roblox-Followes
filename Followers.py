import requests
import re
import threading
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import os

DEFAULT_TARGET = 
WEBHOOK_URL = ""  # ใส่ Discord Webhook URL ตรงนี้

current_threads = []
stop_flags = {}
user_status = {}
last_sent_state = {}

LOG_FILE = "follow_checker_log.txt"

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
        if presence_r.status_code == 200:
            presence_info = presence_r.json()
            if presence_info.get("userPresences"):
                presence_data = presence_info["userPresences"][0]
        
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
            "friends": friends_count,
            "followers": followers_count,
            "followings": followings_count,
            "avatar_url": avatar_image_url
        }
    except Exception as e:
        print(f"⚠️ Error getting user info: {e}")
        return None


def send_discord_webhook(user_id, is_follow, user_info=None):
    """ส่งการแจ้งเตือนพร้อมข้อมูลละเอียดและรูปโปรไฟล์ไปยัง Discord Webhook"""
    if not WEBHOOK_URL:
        return
    
    try:
        status = "✅ กำลัง Follow" if is_follow else "❌ ไม่ได้ Follow"
        color = 3066993 if is_follow else 15158332  # เขียว : แดง
        
        embed = {
            "title": f"🔔 การตรวจสอบ Follow - User {user_id}",
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Roblox Follow Checker"}
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
            embed["description"] = f"**User ID:** {user_id}\n**สถานะ:** {status}\n\n*ไม่สามารถดึงข้อมูลเพิ่มเติมได้*"
        
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


def is_following(user_id, target_id=DEFAULT_TARGET):
    """ตรวจสอบว่า user_id กำลัง follow target_id หรือไม่"""
    url = f"https://friends.roblox.com/v1/users/{user_id}/followings?sortOrder=Asc&limit=100"

    while True:
        try:
            r = requests.get(url, timeout=10)
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
        except:
            return False

    return False


def display_user_status():
    """แสดงสถานะของผู้ใช้ทั้งหมดบนหน้าจอ"""
    clear_screen()
    print("=" * 80)
    print("🎮 Roblox Follow Checker - Termux Edition".center(80))
    print("=" * 80)
    print()
    
    if not user_status:
        print("⏳ กำลังรอข้อมูล...")
        return
    
    for user_id, status_info in user_status.items():
        is_following_status = status_info.get("is_following", False)
        user_info = status_info.get("user_info")
        last_update = status_info.get("last_update", "-")
        
        border = "+" + "-" * 78 + "+"
        print(border)
        
        if is_following_status:
            print(f"| {'✅ กำลัง FOLLOW อยู่!'.center(76)} |")
        else:
            print(f"| {'❌ ไม่ได้ FOLLOW'.center(76)} |")
        
        print(border)
        
        if user_info:
            print(f"| 👤 User ID: {user_id:<63} |")
            print(f"| 📝 ชื่อ: {user_info['displayName']} (@{user_info['name']}){' ' * (60 - len(user_info['displayName']) - len(user_info['name']))} |")
            
            presence_status = {
                0: "🔴 Offline",
                1: "🟢 Online", 
                2: "🎮 กำลังเล่นเกม",
                3: "🛠️ อยู่ใน Studio"
            }.get(user_info["presence"], "❓ ไม่ทราบ")
            
            print(f"| 📊 สถานะ: {presence_status:<62} |")
            print(f"| 👥 เพื่อน: {user_info['friends']:,} | 📢 ผู้ติดตาม: {user_info['followers']:,} | ➕ ติดตาม: {user_info['followings']:,}{' ' * 10} |")
        else:
            print(f"| 👤 User ID: {user_id:<63} |")
            print(f"| ⚠️ ไม่สามารถดึงข้อมูลได้{' ' * 54} |")
        
        print(f"| ⏰ อัพเดทล่าสุด: {last_update:<59} |")
        print(border)
        print()
    
    print(f"\n📊 กำลังตรวจสอบ: {len(user_status)} คน")
    print("💡 กด Ctrl+C เพื่อหยุดโปรแกรม")
    print()


def loop_check(user_id, interval=5):
    """ตรวจสอบ User ซ้ำๆ"""
    while not stop_flags.get(user_id, False):
        try:
            result = is_following(user_id)
            user_info = get_user_info(user_id)
            
            current_time = datetime.now().strftime("%H:%M:%S")
            
            user_status[user_id] = {
                "is_following": result,
                "user_info": user_info,
                "last_update": current_time
            }
            
            # ส่ง Webhook เฉพาะเมื่อมีการเปลี่ยนแปลง
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


def start_checking(user_ids):
    """เริ่มตรวจสอบหลาย User พร้อมกัน"""
    global current_threads, stop_flags
    
    log_to_file(f"เริ่มตรวจสอบ {len(user_ids)} User: {user_ids}")
    print(f"\n🔄 เริ่มตรวจสอบ {len(user_ids)} คน...")
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
    
    print("\n⏹️ กำลังหยุดการตรวจสอบ...")
    for user_id in stop_flags:
        stop_flags[user_id] = True
    
    time.sleep(1)
    print("✅ หยุดการทำงานเรียบร้อย")


def main():
    """ฟังก์ชันหลัก"""
    clear_screen()
    print("=" * 80)
    print("🎮 Roblox Follow Checker - Termux Edition".center(80))
    print("=" * 80)
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
    print("💬 ใส่ UserID หรือ ลิงก์ (สามารถใส่หลาย User ได้, คั่นด้วยเว้นวรรค):")
    user_input = input("   > ").strip()
    
    if not user_input:
        print("❌ ไม่พบ UserID")
        return
    
    user_ids = extract_user_ids(user_input)
    
    if not user_ids:
        print("❌ ไม่พบ UserID ที่ถูกต้อง")
        return
    
    try:
        start_checking(user_ids)
        
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
