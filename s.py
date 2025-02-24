import logging
import time
import threading
import requests
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message

# Telegram Bot Config
API_ID = 16531092
API_HASH = "b073b97bd4c8c56616fc2cbbd4da845a"
BOT_TOKEN = "7524524705:AAH7aBrV5cAZNRFIx3ZZhO72kbi4tjNd8lI"
CHANNEL_ID = "-1002340139937"  # Private channel where links are sent
ADMIN_IDS = [2142536515]  # Only admins can use commands

# MongoDB Config
MONGO_URI = "mongodb+srv://FF:FF@cluster0.ryymb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "MovieBot"
COLLECTION_NAME = "Links"

# Set up logging
logging.basicConfig(level=logging.INFO)

# MongoDB Connection
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# Initialize Selenium with undetected-chromedriver
def init_driver():
    return uc.Chrome(headless=True, use_subprocess=True)

driver = init_driver()

# Pyrogram Bot Initialization
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Global Variables
category_url = None
scraping = False
sending_links = False


def extract_hubdrive_link(howblogs_url):
    """Extract HubDrive link from howblogs.xyz"""
    try:
        response = requests.get(howblogs_url)
        soup = BeautifulSoup(response.text, "html.parser")
        hubdrive_link = soup.find("a", href=True, text="Download Now")
        if hubdrive_link:
            return hubdrive_link["href"]
    except Exception as e:
        logging.error(f"Error extracting HubDrive link: {e}")
    return None


def bypass_hubdrive(hubdrive_url):
    """Bypass HubDrive to get the final download link"""
    try:
        driver.get(hubdrive_url)
        time.sleep(5)  # Wait for JavaScript execution
        final_link = driver.find_element("xpath", "//a[contains(@href, 'https://files')]").get_attribute("href")
        return final_link
    except Exception as e:
        logging.error(f"Error bypassing HubDrive: {e}")
    return None


def scrape_movies():
    """Scrape movie links from skymovieshd.video and process them"""
    global scraping
    if not category_url:
        logging.warning("Category URL is not set!")
        return

    scraping = True
    logging.info(f"Scraping started for {category_url}")
    response = requests.get(category_url)
    soup = BeautifulSoup(response.text, "html.parser")
    posts = soup.find_all("a", class_="post-title")

    for post in posts:
        if not scraping:
            break
        post_url = post["href"]
        logging.info(f"Processing post: {post_url}")

        # Extract howblogs link
        post_page = requests.get(post_url)
        post_soup = BeautifulSoup(post_page.text, "html.parser")
        howblogs_link = post_soup.find("a", href=True, text="Download Now")

        if not howblogs_link:
            continue

        howblogs_url = howblogs_link["href"]
        hubdrive_url = extract_hubdrive_link(howblogs_url)
        if not hubdrive_url:
            continue

        final_link = bypass_hubdrive(hubdrive_url)
        if not final_link:
            continue

        # Save to MongoDB
        if not collection.find_one({"url": final_link}):
            collection.insert_one({"url": final_link})
            logging.info(f"Saved: {final_link}")
        else:
            logging.info("Duplicate found, skipping.")

    logging.info("Scraping completed.")
    scraping = False


def send_links():
    """Send saved links to the Telegram channel every 3 minutes"""
    global sending_links
    sending_links = True
    while sending_links:
        links = collection.find()
        for link in links:
            bot.send_message(CHANNEL_ID, link["url"])
            time.sleep(5)  # Avoid spam
        time.sleep(180)  # Send links every 3 minutes


@bot.on_message(filters.command("sc_category") & filters.user(ADMIN_IDS))
def start_scraping(client: Client, message: Message):
    """Start scraping movies"""
    global category_url, scraping
    if scraping:
        message.reply_text("Scraping is already in progress.")
        return

    args = message.text.split(" ", 1)
    if len(args) < 2:
        message.reply_text("Usage: /sc_category {category_url}")
        return

    category_url = args[1]
    threading.Thread(target=scrape_movies, daemon=True).start()
    message.reply_text("Scraping started!")


@bot.on_message(filters.command("stop") & filters.user(ADMIN_IDS))
def stop_sending(client: Client, message: Message):
    """Stop sending links"""
    global sending_links
    sending_links = False
    message.reply_text("Stopped sending links!")


@bot.on_message(filters.command("restart") & filters.user(ADMIN_IDS))
def restart_sending(client: Client, message: Message):
    """Restart sending links"""
    global sending_links
    if sending_links:
        message.reply_text("Already sending links!")
        return
    threading.Thread(target=send_links, daemon=True).start()
    message.reply_text("Resumed sending links!")


if __name__ == "__main__":
    # Start sending links every 3 minutes
    threading.Thread(target=send_links, daemon=True).start()

    # Run the bot
    bot.run()