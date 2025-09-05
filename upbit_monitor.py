import os

import requests
import time
import json
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Dict, Set
from extract import extract_from_text
from dotenv import load_dotenv
from tabdeal import TabdealAPI

load_dotenv()

TABDEAL_API_KEY = os.getenv('TABDEAL_API_KEY')
TABDEAL_API_SECRET = os.getenv('TABDEAL_API_SECRET')

USDT_VALUE_FOR_EACH_ORDER = 500

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('upbit_monitor.log'),
        logging.StreamHandler()
    ]
)


def kst_to_utc(kst_str):
    utc_date = datetime.fromisoformat(kst_str).astimezone(timezone.utc)
    second_passed = (datetime.now(tz=timezone.utc) - utc_date).total_seconds()

    return utc_date.strftime('%Y-%m-%d %H:%M'), second_passed


class UpbitAnnouncementMonitor:
    def __init__(self, telegram_bot_token: str, telegram_chat_id: str, proxy_list: List[str] = None):
        """
        Initialize the Upbit announcement monitor

        Args:
            telegram_bot_token: Your Telegram bot token
            telegram_chat_id: Your Telegram chat ID to send messages to
            proxy_list: List of proxy strings in format "ip:port:username:password"
        """
        self.upbit_api_url = "https://api-manager.upbit.com/api/v1/announcements"
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.telegram_api_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"

        # Store seen announcement IDs to avoid duplicates
        self.seen_announcements: Set[int] = set()

        self.last_refresh_time = None
        self.tabdeal_client = TabdealAPI(api_key=TABDEAL_API_KEY, secret_key=TABDEAL_API_SECRET)

        # Proxy configuration
        self.proxy_list = proxy_list or []
        self.proxy_index = 0
        self.banned_proxies = []
        self.parsed_proxies = self._parse_proxy_list()

        # API parameters
        self.api_params = {
            'os': 'web',
            'page': 1,
            'per_page': 1,
            'category': 'trade'
        }

        logging.info(f"Upbit Announcement Monitor initialized with {len(self.proxy_list)} proxies")

    def _parse_proxy_list(self) -> List[Dict]:
        """
        Parse proxy list from string format to dictionary format

        Returns:
            List of proxy dictionaries
        """
        parsed_proxies = []

        for proxy_str in self.proxy_list:
            try:
                parts = proxy_str.strip().split(':')
                if len(parts) == 4:
                    ip, port, username, password = parts
                    proxy_dict = {
                        'http': f'http://{username}:{password}@{ip}:{port}',
                        'https': f'http://{username}:{password}@{ip}:{port}'
                    }
                    parsed_proxies.append(proxy_dict)
                    logging.info(f"Parsed proxy: {ip}:{port}")
                else:
                    logging.warning(f"Invalid proxy format: {proxy_str}")
            except Exception as e:
                logging.error(f"Error parsing proxy {proxy_str}: {e}")

        return parsed_proxies

    def get_next_proxy(self) -> Dict:
        """
        Get the next proxy in rotation

        Returns:
            Proxy dictionary or None if no proxies available
        """
        if not self.parsed_proxies:
            return None

        proxy = self.parsed_proxies[self.proxy_index]
        self.proxy_index = (self.proxy_index + 1) % len(self.parsed_proxies)

        return proxy

    def fetch_announcements(self) -> List[Dict]:
        """
        Fetch announcements from Upbit API using rotating proxies

        Returns:
            List of announcement dictionaries
        """
        proxy = self.get_next_proxy()

        try:
            headers = {"accept-language": "en-US,en;q=0.5"}

            if proxy:
                logging.info(f"Using proxy: {proxy['http'].split('@')[1]}")
                response = requests.get(
                    self.upbit_api_url,
                    params=self.api_params,
                    timeout=10,
                    headers=headers,
                    proxies=proxy
                )

                if response.status_code != 200:
                    self.banned_proxies.append([proxy['http']])
                    print("banned_proxies", self.banned_proxies)
            else:
                logging.info("No proxy available, using direct connection")
                response = requests.get(
                    self.upbit_api_url,
                    params=self.api_params,
                    timeout=10,
                    headers=headers
                )

            response.raise_for_status()

            data = response.json()
            announcements = data["data"]["notices"]
            announcements.reverse()

            logging.info(f"Fetched {len(announcements)} announcements")
            return announcements

        except requests.exceptions.ProxyError as e:
            logging.error(f"Proxy error: {e}")
            # Try without proxy as fallback
            try:
                logging.info("Attempting direct connection as fallback")
                headers = {"accept-language": "en-US,en;q=0.5"}
                response = requests.get(self.upbit_api_url, params=self.api_params, timeout=10, headers=headers)
                response.raise_for_status()

                data = response.json()
                announcements = data["data"]["notices"]
                announcements.reverse()

                logging.info(f"Fetched {len(announcements)} announcements via direct connection")
                return announcements
            except Exception as fallback_error:
                logging.error(f"Direct connection fallback also failed: {fallback_error}")
                return []

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching announcements: {e}")
            return []
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing JSON response: {e}")
            return []

    def is_recent_announcement(self, announcement_date: datetime, minutes_threshold: int = 5) -> bool:
        """
        Check if announcement is within the specified time window

        Args:
            announcement_date: Date of the announcement
            minutes_threshold: Time window in minutes (default: 5)

        Returns:
            True if announcement is within time window
        """
        now = datetime.now()
        time_threshold = now - timedelta(minutes=minutes_threshold)
        return announcement_date >= time_threshold

    def process_new_announcement_message(self, announcement: dict) -> bool:
        message = self.format_announcement_message(announcement)
        data = extract_from_text(announcement['title'])

        try:
            response = self.tabdeal_client.place_order(
                usdt_value=USDT_VALUE_FOR_EACH_ORDER,
                currency_symbol=data["symbol"],
            )
        except Exception as e:
            response = str(e)
        """
        Send message to Telegram

        Args:
            message: Message to send

        Returns:
            True if message sent successfully, False otherwise
        """

        message += "\n\n"
        message += f"tabdeal response {response}"

        self.send_new_telegram_message(message=message)

    def send_new_telegram_message(self, message: str) -> bool:
        """
        Send message to Telegram

        Args:
            message: Message to send

        Returns:
            True if message sent successfully, False otherwise
        """

        try:
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }

            response = requests.post(self.telegram_api_url, json=payload, timeout=10)
            response.raise_for_status()

            logging.info("Telegram message sent successfully")
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending Telegram message: {e}")
            return False

    def format_announcement_message(self, announcement: Dict) -> str:

        """
        Format announcement data into a readable message

        Args:
            announcement: Announcement dictionary

        Returns:
            Formatted message string
        """
        title = announcement.get('title', 'No title')
        date = announcement.get('listed_at', 'Unknown date')
        date, second_passed = kst_to_utc(date)
        url = announcement.get('url', '')

        data = extract_from_text(title)

        message = f"🚨 <b>New Upbit Announcement</b>\n\n"
        message += f"📋 <b>Title:</b> {title}\n"
        message += f"📅 <b>Date:</b> {date}\n\n"
        message += f"symbol: {data['symbol']}\n"
        message += f"name: <b>{data['name']}</b>\n"
        message += f"quote: <b>{data['quote']}</b>\n\n"
        message += f"seconds passed: {second_passed}"

        if url:
            message += f"🔗 <b>Link:</b> {url}"

        return message

    def check_new_announcements(self) -> None:
        """
        Check for new announcements and send notifications
        """
        announcements = self.fetch_announcements()

        if not announcements:
            return

        new_announcements = []

        for announcement in announcements:
            announcement_id = announcement.get('id')
            created_at = announcement.get('created_at', '')

            # Skip if we've already seen this announcement
            if announcement_id in self.seen_announcements:
                continue

            new_announcements.append(announcement)
            logging.info(f"New recent announcement found: {announcement.get('title', 'No title')}")

            # Add to seen announcements regardless of age
            self.seen_announcements.add(announcement_id)

        # Send notifications for new announcements

        if len(new_announcements) == 0:
            if self.last_refresh_time is None or time.time() - self.last_refresh_time > 3600:
                message = (f"🚨 <b>New Upbit Announcement</b>\n\n"
                           f"nothing new here!!")
                self.send_new_telegram_message(message)
                self.last_refresh_time = time.time()

        for announcement in new_announcements:
            self.process_new_announcement_message(announcement)
            time.sleep(1)  # Small delay between messages

    def run_monitor(self, check_interval_seconds: float = 60) -> None:
        """
        Run the monitoring loop

        Args:
            check_interval_seconds: Interval between checks in seconds (default: 60)
        """
        logging.info(f"Starting Upbit announcement monitor (checking every {check_interval_seconds} seconds)")

        # Initial population of seen announcements to avoid spam on startup
        initial_announcements = self.fetch_announcements()
        for announcement in initial_announcements:
            self.seen_announcements.add(announcement.get('id'))

        logging.info(f"Initialized with {len(self.seen_announcements)} existing announcements")

        while True:
            try:
                self.check_new_announcements()
                time.sleep(check_interval_seconds)

            except KeyboardInterrupt:
                logging.info("Monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Unexpected error in monitor loop: {e}")
                time.sleep(check_interval_seconds)


def main():
    """
    Main function to run the monitor
    """
    # Configuration - Replace with your actual tokens
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

    # Proxy configuration - Add your proxies here
    PROXY_LIST = os.environ.get("PROXIES").split(",")
    # Validate configuration
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ Please configure your Telegram bot token in the script")
        return

    if TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID_HERE":
        print("❌ Please configure your Telegram chat ID in the script")
        return

    # Create and run monitor
    monitor = UpbitAnnouncementMonitor(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PROXY_LIST)
    monitor.run_monitor(check_interval_seconds=0)  # Check every 60 seconds


if __name__ == "__main__":
    main()