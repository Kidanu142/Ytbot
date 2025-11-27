import os
import logging
import sqlite3
import json
import asyncio
import platform
from datetime import datetime
from yt_dlp import YoutubeDL
import telebot
from telebot import types
from pytube import YouTube

# ==============================
# CONFIGURATION
# ==============================
BOT_TOKEN = "8291849608:AAG6F669iX6Y_LAuuzFr0OQcOSyjh111xPc"
BOT_AUTHOR = "VIPER"
CONTACT_USERNAME = "@viper_5_8"
CHANNEL_USERNAME = "@python_with_viper"
CHANNEL_URL = "https://t.me/python_with_viper"
ADMIN_ID = 7929255261

bot = telebot.TeleBot(BOT_TOKEN)

# ==============================
# SETUP LOGGING
# ==============================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================
# SMART FOLDER SETUP (SAME AS TELEGRAM)
# ==============================
def setup_folders():
    """Detect platform and setup folders in the same location as Telegram"""
    system = platform.system().lower()
    
    # Working folder (temporary downloads)
    home_folder = os.path.expanduser("~")
    working_folder = os.path.join(home_folder, "yt_temp")
    
    # Target folder - Same as Telegram but in Viper subfolder
    if system == "windows":
        # Windows: Telegram saves to Users\Username\Downloads\Telegram Desktop
        telegram_folder = os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop")
        target_folder = os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop", "Viper")
    elif system == "linux":
        # Linux: Check if it's Android or regular Linux
        if "android" in platform.platform().lower():
            # Android: Telegram saves to /storage/emulated/0/Telegram
            telegram_folder = os.path.join("/storage/emulated/0", "Telegram")
            target_folder = os.path.join("/storage/emulated/0", "Telegram", "Viper")
        else:
            # Linux PC: Telegram saves to /home/username/Downloads/Telegram Desktop
            telegram_folder = os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop")
            target_folder = os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop", "Viper")
    elif system == "darwin":  # macOS
        # macOS: Telegram saves to /Users/username/Downloads/Telegram Desktop
        telegram_folder = os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop")
        target_folder = os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop", "Viper")
    else:
        # Fallback for unknown systems
        telegram_folder = os.path.join(os.path.expanduser("~"), "Telegram")
        target_folder = os.path.join(os.path.expanduser("~"), "Telegram", "Viper")
    
    # Create Viper folder inside Telegram folder
    os.makedirs(working_folder, exist_ok=True)
    os.makedirs(target_folder, exist_ok=True)
    
    return working_folder, target_folder, telegram_folder

# Initialize folders
working_folder, target_folder, telegram_folder = setup_folders()

# ==============================
# DATABASE SETUP
# ==============================
def init_database():
    conn = sqlite3.connect('viper_users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            download_count INTEGER DEFAULT 0,
            has_joined_channel BOOLEAN DEFAULT FALSE,
            is_unlimited BOOLEAN DEFAULT FALSE,
            last_download TIMESTAMP,
            join_verified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('viper_users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'download_count': user[3],
            'has_joined_channel': bool(user[4]),
            'is_unlimited': bool(user[5]),
            'last_download': user[6],
            'join_verified_at': user[7],
            'created_at': user[8]
        }
    return None

def update_user_data(user, download_increment=False):
    conn = sqlite3.connect('viper_users.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user.id,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        if download_increment:
            cursor.execute('''
                UPDATE users 
                SET download_count = download_count + 1, last_download = ?
                WHERE user_id = ?
            ''', (datetime.now(), user.id))
        else:
            cursor.execute('''
                UPDATE users 
                SET username = ?, first_name = ?
                WHERE user_id = ?
            ''', (user.username, user.first_name, user.id))
    else:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, download_count, last_download)
            VALUES (?, ?, ?, ?, ?)
        ''', (user.id, user.username, user.first_name, 1 if download_increment else 0, 
              datetime.now() if download_increment else None))
    
    conn.commit()
    conn.close()

def set_channel_joined(user_id):
    conn = sqlite3.connect('viper_users.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET has_joined_channel = TRUE, is_unlimited = TRUE, join_verified_at = ?
        WHERE user_id = ?
    ''', (datetime.now(), user_id))
    conn.commit()
    conn.close()

# ==============================
# QUALITY & FORMAT OPTIONS
# ==============================
QUALITY_OPTIONS = {
    "best": "🎯 Best Quality",
    "1080p": "📹 1080p HD", 
    "720p": "🎥 720p HD",
    "480p": "📺 480p",
    "360p": "📱 360p",
    "audio": "🎵 Audio Only"
}

FORMAT_OPTIONS = {
    "mp4": "🎬 MP4 Video",
    "webm": "🌐 WebM Video", 
    "mp3": "🎵 MP3 Audio",
    "m4a": "🔊 M4A Audio"
}

# ==============================
# OPTIMIZED YT-DLP CONFIGURATION
# ==============================
def get_ydl_options(quality, format_choice, subtitles=False):
    ydl_opts = {
        'outtmpl': os.path.join(working_folder, '%(title).100s.%(ext)s'),
        'ignoreerrors': True,
        'no_warnings': True,
        'quiet': True,
        'no_color': True,
        'socket_timeout': 30,
        'extract_timeout': 60,
    }
    
    if quality == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        if format_choice == 'mp3':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif format_choice == 'm4a':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }]
    else:
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        else:
            height = quality.replace('p', '')
            ydl_opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
        
        if format_choice == 'mp4':
            ydl_opts['merge_output_format'] = 'mp4'
        elif format_choice == 'webm':
            ydl_opts['merge_output_format'] = 'webm'
    
    # Disable subtitles to avoid rate limiting
    ydl_opts['writesubtitles'] = False
    ydl_opts['writeautomaticsub'] = False
    
    return ydl_opts

# ==============================
# CHANNEL VERIFICATION
# ==============================
def check_channel_membership(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return False

# ==============================
# DOWNLOAD ELIGIBILITY CHECK
# ==============================
def check_download_eligibility(user_id):
    user_data = get_user_data(user_id)
    
    if not user_data:
        return True
    
    if user_data['is_unlimited']:
        return True
    
    if user_data['download_count'] < 1:
        return True
    
    if user_data['has_joined_channel']:
        is_member = check_channel_membership(user_id)
        if is_member:
            set_channel_joined(user_id)
            return True
        else:
            return False
    else:
        return False

# ==============================
# BOT COMMANDS
# ==============================
@bot.message_handler(commands=['start'])
def start_command(message):
    update_user_data(message.from_user)
    user_data = get_user_data(message.from_user.id)
    
    download_count = user_data['download_count'] if user_data else 0
    is_unlimited = user_data['is_unlimited'] if user_data else False
    
    if user_data and user_data['is_unlimited']:
        status_text = "🎉 UNLIMITED ACCESS"
    elif not user_data or download_count == 0:
        status_text = "✅ 1 FREE DOWNLOAD LEFT" 
    else:
        status_text = "🔒 JOIN CHANNEL FOR UNLIMITED"
    
    welcome_text = f"""
🎬 *VIPER YouTube Downloader* 
*Created by {BOT_AUTHOR}*

💫 *Welcome {message.from_user.first_name}!* 💫

📥 *Advanced Features:*
• Multiple quality options (360p to 1080p)
• Audio extraction (MP3/M4A)
• Fast downloads
• Works on PC & Mobile

🎯 *Download Policy:*
• 1 FREE download for everyone
• Unlimited access after joining: {CHANNEL_USERNAME}

💾 *Save Location:*
• Videos are saved in the *same folder as Telegram*
• Look for: `Telegram/Viper/` folder
• Easy to find alongside your Telegram files!

📊 *Your Stats:*
• Downloads used: {download_count}/1
• Status: {status_text}

*Send me any YouTube URL to start!*
"""
    
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = f"""
🤖 *VIPER YouTube Downloader Help*
*Created by {BOT_AUTHOR}*

*Available Commands:*
/start - Start bot & see status
/help - Show this help message  
/stats - Check your download statistics
/contact - Contact {CONTACT_USERNAME}
/admin - Admin panel (Admin only)

*How to use:*
1. Send any YouTube URL
2. Choose quality (360p, 480p, 720p, 1080p, Best)
3. Select format (MP4, WebM, MP3, M4A)
4. Download!

*Save Location:*
💾 *Videos are automatically saved to:*
• `Telegram/Viper/` folder
• Same location as your Telegram files
• No need to download from Telegram - file is already on your device!

*Download Policy:*
🎁 *First Download:* FREE for everyone
🔓 *Unlimited Access:* Join {CHANNEL_USERNAME}

*Supported Platforms:*
• Windows PC
• Android Phone
• Linux PC
• macOS

*Need Help?* Use /contact or message {CONTACT_USERNAME}
"""
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data:
        bot.reply_to(message, "❌ No data found. Use /start to initialize.")
        return
    
    stats_text = f"""
📊 *Your Download Statistics*

👤 *User Info:*
• Name: {user_data['first_name']}
• Username: {user_data['username'] or 'N/A'}

📥 *Download Stats:*
• Total Downloads: {user_data['download_count']}
• Access Level: {'🎉 UNLIMITED' if user_data['is_unlimited'] else '🔒 LIMITED'}
• Channel Member: {'✅ YES' if user_data['has_joined_channel'] else '❌ NO'}

💾 *Save Location:*
• Same folder as Telegram
• Look for: `Telegram/Viper/` folder
"""
    
    if user_data['download_count'] >= 1 and not user_data['is_unlimited']:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🚀 Join Channel for Unlimited", url=CHANNEL_URL),
            types.InlineKeyboardButton("✅ I've Joined", callback_data="verify_join")
        )
        stats_text += "\n🔓 *Upgrade to unlimited access by joining our channel!*"
        bot.reply_to(message, stats_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        bot.reply_to(message, stats_text, parse_mode='Markdown')

@bot.message_handler(commands=['contact'])
def contact_command(message):
    contact_text = f"""
📞 *Contact Information*

*Bot Author:* {BOT_AUTHOR}
*Telegram:* {CONTACT_USERNAME}

💼 *For Support/Business:*
• Contact me directly on Telegram: {CONTACT_USERNAME}
• Report any issues or suggestions  
• Custom bot development available

🔧 *Technical Support:*
Please describe your issue in detail when contacting for support.
"""
    bot.reply_to(message, contact_text, parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ Access denied. Admin only.")
        return
    
    admin_text = f"""
🛡️ *VIPER Admin Panel*

*Available Admin Commands:*
/grant <user_id> - Grant unlimited access
/userinfo <user_id> - Get user information

*Save Location:*
• Telegram Folder: `{telegram_folder}`
• Viper Folder: `{target_folder}`

*Bot by {BOT_AUTHOR}*
*Contact: {CONTACT_USERNAME}*
"""
    bot.reply_to(message, admin_text, parse_mode='Markdown')

# ==============================
# ADMIN COMMANDS
# ==============================
@bot.message_handler(commands=['grant'])
def grant_command(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ Access denied.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "❌ Usage: /grant <user_id>")
        return
    
    try:
        target_user_id = int(message.text.split()[1])
        set_channel_joined(target_user_id)
        
        try:
            bot.send_message(
                target_user_id,
                "🎉 *Admin has granted you UNLIMITED access!*\n\n"
                "You now have unlimited downloads without needing to join any channels!\n\n"
                "💾 *Videos are saved in the same folder as Telegram*\n"
                "• Look for `Telegram/Viper/` folder\n\n"
                "Thank you for using VIPER YouTube Downloader!",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.reply_to(message, f"✅ Unlimited access granted to user `{target_user_id}`", parse_mode='Markdown')
        
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID format.")

@bot.message_handler(commands=['userinfo'])
def userinfo_command(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ Access denied.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "❌ Usage: /userinfo <user_id>")
        return
    
    try:
        target_user_id = int(message.text.split()[1])
        user_data = get_user_data(target_user_id)
        
        if not user_data:
            bot.reply_to(message, "❌ User not found.")
            return
        
        user_info = f"""
👤 *User Information*

*Basic Info:*
• User ID: `{user_data['user_id']}`
• Name: {user_data['first_name']}
• Username: @{user_data['username'] or 'N/A'}

*Account Status:*
• Downloads: {user_data['download_count']}
• Access: {'🎉 UNLIMITED' if user_data['is_unlimited'] else '🔒 LIMITED'}
• Channel Member: {'✅ YES' if user_data['has_joined_channel'] else '❌ NO'}

*Timestamps:*
• Joined: {user_data['created_at']}
• Last Download: {user_data['last_download'] or 'Never'}
"""
        bot.reply_to(message, user_info, parse_mode='Markdown')
        
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID format.")

# ==============================
# YOUTUBE URL HANDLER
# ==============================
@bot.message_handler(func=lambda msg: "youtube.com" in msg.text or "youtu.be" in msg.text)
def handle_youtube_url(message):
    user_id = message.from_user.id
    url = message.text.strip()

    # Check download eligibility
    if not check_download_eligibility(user_id):
        user_data = get_user_data(user_id)
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🚀 Join Channel Now", url=CHANNEL_URL),
            types.InlineKeyboardButton("✅ Verify Join", callback_data="verify_join"),
            types.InlineKeyboardButton("📊 Check Stats", callback_data="show_stats")
        )
        
        upgrade_text = f"""
🔒 *Download Limit Reached*

You've used your free download! 
Get unlimited access easily:

🎁 *Get UNLIMITED Downloads:*
1. Join: {CHANNEL_USERNAME}  
2. Click 'Verify Join' below
3. Enjoy unlimited downloads!

📊 *Your usage:* {user_data['download_count']} downloads

💾 *Videos saved in same folder as Telegram*
• Look for `Telegram/Viper/` folder

💫 *Why join?*
• Unlimited YouTube downloads
• Premium features
• Support development
• Contact: {CONTACT_USERNAME}
"""
        bot.reply_to(message, upgrade_text, reply_markup=keyboard, parse_mode='Markdown')
        return

    try:
        # Get video info with optimized settings
        ydl_info_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
        }
        
        with YoutubeDL(ydl_info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Show quality selection
        keyboard = types.InlineKeyboardMarkup()
        for key, name in QUALITY_OPTIONS.items():
            keyboard.add(types.InlineKeyboardButton(name, callback_data=f"quality_{key}"))
        
        duration = info.get('duration', 0)
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "N/A"
        
        user_data = get_user_data(user_id)
        remaining = "🎉 UNLIMITED" if user_data and user_data['is_unlimited'] else f"{1 - (user_data['download_count'] if user_data else 0)} LEFT"
        
        bot.reply_to(message,
            f"📹 *{info['title'][:100]}*...\n\n"
            f"🕓 Duration: {duration_str}\n"
            f"👤 Uploader: {info.get('uploader', 'N/A')}\n"
            f"📥 Your downloads: {remaining}\n"
            f"💾 Save location: `Telegram/Viper/` folder\n\n"
            "🎚 *Select Quality:*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error fetching video info: {e}")
        bot.reply_to(message, f"❌ Error: Could not fetch video information. {str(e)}")

# ==============================
# QUALITY SELECTION HANDLER
# ==============================
@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_quality_callback(call):
    user_id = call.from_user.id
    quality = call.data.split('_')[1]
    
    # Store quality selection and ask for format
    keyboard = types.InlineKeyboardMarkup()
    
    if quality == "audio":
        format_keys = ["mp3", "m4a"]
    else:
        format_keys = ["mp4", "webm"]
    
    for key in format_keys:
        keyboard.add(types.InlineKeyboardButton(FORMAT_OPTIONS[key], callback_data=f"format_{quality}_{key}"))
    
    bot.edit_message_text(
        f"✅ Quality: *{QUALITY_OPTIONS.get(quality, quality)}*\n\n"
        "📁 Select format:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# ==============================
# FORMAT SELECTION HANDLER
# ==============================
@bot.callback_query_handler(func=lambda call: call.data.startswith('format_'))
def handle_format_callback(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    quality = parts[1]
    format_choice = parts[2]
    
    # Start download immediately
    original_message = call.message.reply_to_message
    
    if not original_message or not any(domain in original_message.text for domain in ['youtube.com', 'youtu.be']):
        bot.answer_callback_query(call.id, "❌ Could not find YouTube URL. Please try again.")
        return
    
    url = original_message.text.strip()
    
    # Update user download count
    update_user_data(call.from_user, download_increment=True)
    
    # Start download process
    bot.edit_message_text(
        "⏬ Downloading and saving to Telegram/Viper folder...\nThis may take a while...",
        call.message.chat.id,
        call.message.message_id
    )
    
    try:
        # Configure yt-dlp options
        ydl_opts = get_ydl_options(quality, format_choice)
        
        # Download the video directly to working folder
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        
        # Find the downloaded file
        downloaded_files = []
        for file in os.listdir(working_folder):
            if file.endswith(('.mp4', '.webm', '.mp3', '.m4a')):
                downloaded_files.append(file)
        
        if downloaded_files:
            # Move file to Viper folder inside Telegram folder (SAVE ONLY - NO TELEGRAM SEND)
            file_path = os.path.join(working_folder, downloaded_files[0])
            final_path = os.path.join(target_folder, downloaded_files[0])
            
            try:
                os.rename(file_path, final_path)
            except Exception as e:
                # If rename fails, try copy and delete
                import shutil
                shutil.copy2(file_path, final_path)
                os.remove(file_path)
            
            user_stats = get_user_data(user_id)
            remaining = "🎉 UNLIMITED" if user_stats and user_stats['is_unlimited'] else f"{1 - user_stats['download_count']} LEFT"
            
            success_text = f"""
✅ *Download Complete!*

💾 *File saved to:* `Telegram/Viper/` folder
📄 *Filename:* `{downloaded_files[0]}`
📊 *Remaining downloads:* {remaining}

📍 *File Location:*
• Look for the **Viper** folder where your Telegram files are saved
• File is already on your device - no need to download from Telegram!

🎯 *Next:* You can find the file in your Telegram folder and use it directly.
"""
            
            if user_stats['download_count'] >= 1 and not user_stats['is_unlimited']:
                success_text += f"\n🔓 *Want unlimited downloads?* Join {CHANNEL_USERNAME}"
            
            bot.edit_message_text(
                success_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
            
        else:
            bot.edit_message_text(
                "❌ Download completed but no file was found in the working folder.",
                call.message.chat.id,
                call.message.message_id
            )
        
        # Clean up working folder
        for file in os.listdir(working_folder):
            try:
                os.remove(os.path.join(working_folder, file))
            except:
                pass
                
    except Exception as e:
        logger.error(f"Download error: {e}")
        bot.edit_message_text(
            f"❌ Download failed: {str(e)}",
            call.message.chat.id,
            call.message.message_id
        )

# ==============================
# VERIFICATION HANDLER
# ==============================
@bot.callback_query_handler(func=lambda call: call.data == 'verify_join')
def handle_verify_join(call):
    user_id = call.from_user.id
    
    if check_channel_membership(user_id):
        set_channel_joined(user_id)
        
        success_text = f"""
🎉 *Welcome to VIP Club!*

✅ *Channel membership verified!*
✅ *UNLIMITED ACCESS GRANTED!*

✨ *You now have:*
• Unlimited YouTube downloads
• Priority support
• All premium features

💾 *Videos saved in same folder as Telegram*
• Look for `Telegram/Viper/` folder

📥 Download as many videos as you want!
        
*Thank you for supporting!*
*- {BOT_AUTHOR}*
*Contact: {CONTACT_USERNAME}*
"""
        bot.edit_message_text(
            success_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
    else:
        error_text = f"""
❌ *Verification Failed*

We couldn't verify your channel membership.

🤔 *Please make sure:*
1. You've joined: {CHANNEL_USERNAME}
2. You're using the same Telegram account
3. The channel is not hidden

🔄 Try again after joining:
"""
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_URL),
            types.InlineKeyboardButton("🔄 Verify Again", callback_data="verify_join")
        )
        
        bot.edit_message_text(
            error_text,
            call.message.chat.id, 
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

# ==============================
# STATS CALLBACK HANDLER
# ==============================
@bot.callback_query_handler(func=lambda call: call.data == 'show_stats')
def handle_show_stats(call):
    user_id = call.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data:
        bot.answer_callback_query(call.id, "❌ No data found.")
        return
    
    stats_text = f"""
📊 *Your Statistics*

• Total Downloads: {user_data['download_count']}
• Access: {'🎉 UNLIMITED' if user_data['is_unlimited'] else '🔒 LIMITED'}
• Channel Member: {'✅ YES' if user_data['has_joined_channel'] else '❌ NO'}

💾 *Save Location:*
• Same folder as Telegram
• Look for: `Telegram/Viper/` folder
"""
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_main"))
    
    if not user_data['is_unlimited'] and user_data['download_count'] >= 1:
        keyboard.add(types.InlineKeyboardButton("🚀 Get Unlimited", callback_data="get_unlimited"))
    
    bot.edit_message_text(
        stats_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# ==============================
# START BOT
# ==============================
if __name__ == '__main__':
    # Initialize database
    init_database()
    
    print(f"🎬 VIPER YouTube Downloader by {BOT_AUTHOR} is running...")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"📞 Contact: {CONTACT_USERNAME}")
    print(f"🔗 Channel: {CHANNEL_USERNAME}")
    print(f"💻 Platform: {platform.system()}")
    print(f"💾 Telegram Folder: {telegram_folder}")
    print(f"🐍 Viper Folder: {target_folder}")
    
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        print(f"Bot crashed: {e}")