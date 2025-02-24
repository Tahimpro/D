import os
import requests
import asyncio
import logging
import random
import threading
import concurrent.futures
from flask import Flask
from pymongo import MongoClient
from selenium import webdriver
import chromedriver_autoinstaller
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, CallbackContext

# ========== CONFIGURATION ==========
API_HASH = "b073b97bd4c8c56616fc2cbbd4da845a"
API_ID = 16531092
BOT_TOKEN = "7524524705:AAH7aBrV5cAZNRFIx3ZZhO72kbi4tjNd8lI"
CHANNEL_ID = "-1002340139937"
ADMIN_IDS = [2142536515]
CATEGORY_URL = "https://skymovieshd.video/index.php?dir=All-Web-Series&sort=all"
MONGO_URI = "mongodb+srv://FF:FF@cluster0.ryymb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

IS_RUNNING = False  # বটের স্টেট

# ========== DATABASE ==========
try:
    client = MongoClient(MONGO_URI)
    db = client["movie_bot"]
    collection = db["download_links"]
    print("✅ Connected to MongoDB")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

# ========== TELEGRAM BOT ==========
bot = Bot(token=BOT_TOKEN)

# ========== SETUP FLASK SERVER ==========
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# ========== SETUP SELENIUM ==========
def setup_chromedriver():
    chromedriver_autoinstaller.install()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=options)

# ========== FETCH HTML ==========
def fetch_html(url):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        response = session.get(url, allow_redirects=False, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch {url} (Status: {response.status_code})")
            return None
        return response.text
    except requests.RequestException as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

# ========== HUBDRIVE BYPASS ==========
async def get_direct_hubdrive_link(hubdrive_url):
    os.system("pkill -f chrome || true")  # Kill old sessions
    wd = setup_chromedriver()
    try:
        wd.get(hubdrive_url)
        WebDriverWait(wd, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        await asyncio.sleep(random.uniform(2, 3))

        while True:
            current_url = wd.current_url
            if "hubcloud" in current_url:
                try:
                    download_button = WebDriverWait(wd, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//a[@id='download']"))
                    )
                    wd.execute_script("arguments[0].click();", download_button)
                    await asyncio.sleep(0.05)
                except Exception:
                    pass

            while len(wd.window_handles) > 1:
                wd.switch_to.window(wd.window_handles[-1])
                await asyncio.sleep(2)
                wd.close()
                wd.switch_to.window(wd.window_handles[0])

            wd.back()
            await asyncio.sleep(3)
            if "hubcloud" not in wd.current_url:
                try:
                    final_buttons = wd.find_elements(By.XPATH, "//a[contains(@class, 'btn')]")
                    final_links = [btn.get_attribute("href") for btn in final_buttons if btn.get_attribute("href")]
                    return final_links
                except Exception:
                    pass
        return []
    finally:
        wd.quit()

# ========== EXTRACT HUBDRIVE LINKS ==========
def extract_hubdrive_links(post_url):
    soup = fetch_html(post_url)
    if not soup:
        return []

    hubdrive_links = []
    for link in soup.select('a[href*="howblogs.xyz"]'):
        nsoup = fetch_html(link["href"])
        if not nsoup:
            continue
        atag = nsoup.select('div[class="cotent-box"] > a[href]')
        for link in atag:
            if "hubdrive.dad" in link["href"]:
                hubdrive_links.append(link["href"])
    return hubdrive_links

# ========== PROCESS CATEGORY ==========
def process_category(category_url):
    soup = fetch_html(category_url)
    if not soup:
        return

    post_links = [a["href"] for a in soup.select('a[href*="/movie/"]')]
    if not post_links:
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(extract_hubdrive_links, url): url for url in post_links}
        for future in concurrent.futures.as_completed(futures):
            hubdrive_links = future.result()
            for link in hubdrive_links:
                asyncio.run(process_hubdrive_link(link))

# ========== PROCESS HUBDRIVE LINK ==========
async def process_hubdrive_link(hubdrive_url):
    if collection.find_one({"hubdrive_url": hubdrive_url}):
        return

    final_links = await get_direct_hubdrive_link(hubdrive_url)
    if final_links:
        collection.insert_one({"hubdrive_url": hubdrive_url, "final_links": final_links})
        for link in final_links:
            await bot.send_message(chat_id=CHANNEL_ID, text=link)

# ========== TELEGRAM COMMANDS ==========
async def is_admin(update: Update):
    return update.message.from_user.id in ADMIN_IDS

async def start_scraping(update: Update, context: CallbackContext):
    global CATEGORY_URL, IS_RUNNING
    if not await is_admin(update):
        await update.message.reply_text("🚫 **Unauthorized!**")
        return

    IS_RUNNING = True
    await update.message.reply_text(f"✅ **Scraping Started:** {CATEGORY_URL}")
    while IS_RUNNING:
        process_category(CATEGORY_URL)
        await asyncio.sleep(180)

async def stop_scraping(update: Update, context: CallbackContext):
    global IS_RUNNING
    if not await is_admin(update):
        await update.message.reply_text("🚫 **Unauthorized!**")
        return

    IS_RUNNING = False
    await update.message.reply_text("🛑 **Scraping Stopped!**")

async def restart_scraping(update: Update, context: CallbackContext):
    global IS_RUNNING
    if not await is_admin(update):
        await update.message.reply_text("🚫 **Unauthorized!**")
        return

    if CATEGORY_URL:
        IS_RUNNING = True
        await update.message.reply_text(f"🔄 **Restarting Scraping:** {CATEGORY_URL}")
    else:
        await update.message.reply_text("⚠️ **No category found to restart!**")

# ========== MAIN FUNCTION ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("sc_category", start_scraping))
    app.add_handler(CommandHandler("stop", stop_scraping))
    app.add_handler(CommandHandler("restart", restart_scraping))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
