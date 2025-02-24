import os
import time
import random
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import chromedriver_autoinstaller
from pyrogram import Client

# Environment Variables
API_ID = 16531092
API_HASH = "b073b97bd4c8c56616fc2cbbd4da845a"
BOT_TOKEN = "7524524705:AAH7aBrV5cAZNRFIx3ZZhO72kbi4tjNd8lI"
CHANNEL_ID = -1002340139937  # Private channel where links are sent
ADMIN_IDS = [2142536515]  # Only admins can use commands

# MongoDB Config
MONGO_URI = "mongodb+srv://FF:FF@cluster0.ryymb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# MongoDB Connection
client = MongoClient(MONGO_URI)
db = client["sky_movies"]
collection = db["final_links"]

# Telegram Bot
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# SOCKS5 Proxy Config
SOCKS5_PROXY = "socks5h://115.127.124.234:1080"

# Requests with Proxy
PROXIES = {
    "http": SOCKS5_PROXY,
    "https": SOCKS5_PROXY
}

# Selenium Setup with Proxy
def setup_chromedriver():
    chromedriver_autoinstaller.install()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Set SOCKS5 Proxy for Selenium
    options.add_argument(f"--proxy-server={SOCKS5_PROXY.replace('socks5h://', 'socks5://')}")

    return webdriver.Chrome(options=options)

# Extract HubDrive links
def extract_hubdrive_links(post_url):
    session = requests.Session()
    session.proxies.update(PROXIES)
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    response = session.get(post_url)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    hubdrive_links = [a["href"] for a in soup.select('a[href*="howblogs.xyz"]')]

    extracted_links = []
    for link in hubdrive_links:
        nsoup = BeautifulSoup(session.get(link).text, "html.parser")
        atag = nsoup.select('div[class="cotent-box"] > a[href]')
        for a in atag:
            if "hubdrive.dad" in a["href"]:
                extracted_links.append(a["href"])

    return extracted_links

# Bypass HubDrive using Selenium
async def bypass_hubdrive(hubdrive_url):
    os.system("pkill -f chrome || true") 
    wd = setup_chromedriver()
    try:
        wd.get(hubdrive_url)        
        WebDriverWait(wd, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        await asyncio.sleep(random.uniform(2, 3))

        while "hubdrive" in wd.current_url:
            try:
                download_button = WebDriverWait(wd, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@id='download']"))
                )
                wd.execute_script("arguments[0].click();", download_button)
                await asyncio.sleep(2)
            except TimeoutException:
                break

        final_links = []
        final_buttons = wd.find_elements(By.XPATH, "//a[contains(@class, 'btn')]")
        for btn in final_buttons:
            if "Download" in btn.text:
                final_links.append(btn.get_attribute("href"))

        return final_links
    except Exception as e:
        print(f"Error bypassing {hubdrive_url}: {e}")
        return []
    finally:
        wd.quit()

# Process SkyMoviesHD Category
def process_category(category_url):
    session = requests.Session()
    session.proxies.update(PROXIES)
    response = session.get(category_url)
    if response.status_code != 200:
        print("Failed to fetch category page.")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    post_links = [a["href"] for a in soup.select('a[href*="/movie/"]')]

    for idx, post_url in enumerate(post_links, start=1):
        full_url = f"https://skymovieshd.video{post_url}" if post_url.startswith("/") else post_url
        hubdrive_links = extract_hubdrive_links(full_url)

        for hubdrive_url in hubdrive_links:
            final_links = asyncio.run(bypass_hubdrive(hubdrive_url))
            for link in final_links:
                if not collection.find_one({"final_link": link}):
                    collection.insert_one({"post_url": full_url, "final_link": link})
                    print(f"Saved to MongoDB: {link}")

# Send Links to Telegram Every 5 Minutes
async def send_links():
    async with bot:
        while True:
            links = list(collection.find({}))
            for doc in links:
                final_link = doc["final_link"]
                try:
                    await bot.send_message(CHANNEL_ID, f"{final_link}\n\n⭐Scrape From SkyMoviesHd")
                    collection.delete_one({"_id": doc["_id"]})
                    print(f"Sent to Telegram: {final_link}")
                except Exception as e:
                    print(f"Error sending to Telegram: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes

# Run Everything
if __name__ == "__main__":
    category_url = "https://skymovieshd.video/index.php?dir=All-Web-Series&sort=all"

    # Start scraping
    print("Scraping SkyMoviesHD...")
    process_category(category_url)

    # Start Telegram bot
    print("Starting Telegram bot...")
    asyncio.run(send_links())