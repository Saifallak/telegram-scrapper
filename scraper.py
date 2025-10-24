import aiohttp
import asyncio
import json
import os
import re
from datetime import datetime
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto
from typing import List, Dict, Optional

load_dotenv()

print("🚀 Scraper started...", flush=True)

# Telegram API credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE = os.getenv('TELEGRAM_PHONE')
BACKEND_URL = os.getenv('BACKEND_URL', '')

print("ENV DEBUG:", API_ID, API_HASH, PHONE, flush=True)

# قنوات التليجرام
CHANNELS = {
    'https://t.me/+VAkpot4taw_v9n2p': 'ادوات منزلية',
    'https://t.me/+UbRrLCJUETxcZmWJ': 'لعب اطفال',
    'https://t.me/+TQHOHpqeFZ4a2Lmp': 'مستحضرات تجميل',
    'https://t.me/+T1hjkvhugV4GxRYD': 'ملابس داخلية',
    'https://t.me/+Tx6OTiWMi6WS4Y2j': 'مفروشات',
    'https://t.me/+Sbbi6_lLOI2_wP41': 'شرابات',
    'https://t.me/+R5rjl2_-KV3GWYAr': 'هوم وير ولانجيري',
    'https://t.me/+WQ-FJCIwbKrcw2qC': 'ملابس اطفال',
    'https://t.me/+SSyWF7Ya89yPm2_V': 'اكسسوارات',
    'https://t.me/+TsQpYNpBaoRkz-8h': 'تصفيات',
}


class TelegramProductScraper:
    def __init__(self):
        self.client = TelegramClient('scraper_session', API_ID, API_HASH)
        self.products = []

    def extract_price(self, text: str) -> Dict[str, Optional[float]]:
        """استخراج السعر من النص"""
        price_patterns = [
            r'(\d+(?:\.\d+)?)\s*جنيه',
            r'(\d+(?:\.\d+)?)\s*ج\.م',
            r'(\d+(?:\.\d+)?)\s*LE',
            r'السعر[:\s]+(\d+(?:\.\d+)?)',
            r'بسعر[:\s]+(\d+(?:\.\d+)?)',
            r'بد(?:لاً|لا)\s+من\s+(\d+(?:\.\d+)?)',
        ]

        prices = {
            'current_price': None,
            'old_price': None
        }

        # البحث عن "بدلا من" للسعر القديم
        old_price_match = re.search(r'بد(?:لاً|لا)\s+من\s+(\d+(?:\.\d+)?)', text)
        if old_price_match:
            prices['old_price'] = float(old_price_match.group(1))

        # البحث عن السعر الحالي
        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match and 'بدلا من' not in pattern:
                prices['current_price'] = float(match.group(1))
                break

        return prices

    async def download_image(self, message, index: int) -> Optional[str]:
        """تحميل الصورة وحفظها محلياً (مع التحقق من وجودها مسبقاً)"""
        try:
            photo_dir = 'downloaded_images'
            os.makedirs(photo_dir, exist_ok=True)

            filename = f"{photo_dir}/product_{message.chat_id}_{message.id}_{index}.jpg"

            # ✅ لو الصورة متحملة قبل كده، نتخطى التحميل
            if os.path.exists(filename):
                print(f"🟡 Skipping download (already exists): {filename}")
                return filename

            # تحميل الصورة من تليجرام
            await message.download_media(file=filename)
            print(f"📥 Downloaded new image: {filename}")
            return filename

        except Exception as e:
            print(f"Error downloading image: {e}")
            return None

    async def send_to_backend(self, product_data: Dict):
        """إرسال البيانات للـ Backend أو حفظها محليًا لو BACKEND_URL فاضي"""
        # ✅ لو الـ BACKEND_URL فاضي → نحفظ البيانات محليًا بدل الإرسال
        if not BACKEND_URL:
            print("⚠️ BACKEND_URL غير موجود في ملف .env — حفظ البيانات في offline_products.json بدل الإرسال.")
            try:
                offline_file = 'offline_products.json'

                # لو الملف موجود، نقرأ المحتوى الحالي
                if os.path.exists(offline_file):
                    with open(offline_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    data = []

                # 🧠 تحقق إن المنتج مش مكرر قبل الإضافة
                if any(p['unique_id'] == product_data['unique_id'] for p in data):
                    print(f"⏭️ Product already exists locally: {product_data['unique_id']}")
                else:
                    data.append(product_data)
                    with open(offline_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"💾 Product saved locally: {product_data['description'][:50]}...")

            except Exception as e:
                print(f"Error saving offline product: {e}")
            return

        # ✅ الحالة العادية: إرسال للـ Backend
        try:
            async with aiohttp.ClientSession() as session:
                # رفع الصور أولاً
                image_urls = []
                for image_path in product_data.get('images', []):
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as f:
                            form = aiohttp.FormData()
                            form.add_field('file', f, filename=os.path.basename(image_path))

                            async with session.post(f"{BACKEND_URL}/upload", data=form) as resp:
                                resp_text = await resp.text()
                                if resp.status == 200:
                                    result = await resp.json()
                                    image_urls.append(result.get('url'))
                                else:
                                    print(f"⚠️ Upload failed ({resp.status}) for {image_path}")
                                    print(f"🧾 Response: {resp_text}")

                # تجهيز بيانات المنتج للإرسال
                product_data['image_urls'] = image_urls
                del product_data['images']

                # 🟡 اطبع البيانات اللي هتتبعت للـ backend
                print("\n📤 Sending product to backend:")
                print(json.dumps(product_data, ensure_ascii=False, indent=2))

                # إرسال بيانات المنتج
                async with session.post(BACKEND_URL, json=product_data) as resp:
                    resp_text = await resp.text()
                    if resp.status == 201:
                        print(f"✅ Product sent successfully: {product_data['description'][:50]}...")
                    else:
                        print(f"❌ Failed to send product: {resp.status}")
                        print(f"🧾 Response: {resp_text}")

        except Exception as e:
            print(f"Error sending to backend: {e}")

    async def process_message(self, message, channel_name: str = None):
        """معالجة رسالة واحدة"""
        if not message.text or not message.media:
            return

        unique_id = f"{message.chat_id}_{message.id}"

        product = {
            'unique_id': unique_id,
            'channel_id': message.chat_id,
            'message_id': message.id,
            'timestamp': message.date.isoformat(),
            'channel_name': channel_name,  # 🟢 هنا بيتضاف اسم القناة
            'description': message.text or '',
            'images': [],
            'prices': {'current_price': None, 'old_price': None}
        }

        # استخراج الأسعار
        if message.text:
            product['prices'] = self.extract_price(message.text)

        # تحميل الصور
        if message.media:
            if isinstance(message.media, MessageMediaPhoto):
                image_path = await self.download_image(message, 0)
                if image_path:
                    product['images'].append(image_path)
            elif hasattr(message.media, 'photo'):
                image_path = await self.download_image(message, 0)
                if image_path:
                    product['images'].append(image_path)

        # حفظ البيانات محلياً
        self.products.append(product)

        # إرسال أو حفظ المنتج
        await self.send_to_backend(product)

        print(f"📦 Product processed: {product['description'][:50]}... | Price: {product['prices']['current_price']}")

    async def scrape_channel_history(self, channel_link: str):
        """سكرابينج تاريخ القناة حتى تاريخ محدد"""
        try:
            stop_date_str = os.getenv('STOP_DATE', '')
            stop_date = None
            if stop_date_str:
                try:
                    stop_date = datetime.strptime(stop_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    print(f"📅 Stop date set to: {stop_date.date()}")
                except ValueError:
                    print("⚠️ تنبيه: تنسيق STOP_DATE غير صحيح! استخدم YYYY-MM-DD.")

            # اسم القناة المخصص من الـ dict
            channel_name = CHANNELS.get(channel_link, 'قناة غير معروفة')

            # الانضمام للقناة
            entity = await self.client.get_entity(channel_link)
            print(f"🔍 Scraping channel: {entity.title} ({channel_name})")

            # جلب الرسائل
            async for message in self.client.iter_messages(entity):
                if stop_date and message.date < stop_date:
                    print(f"⏹️ Stopped at {message.date}")
                    break

                # نمرر اسم القناة للمنتج
                await self.process_message(message, channel_name)
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Error scraping channel {channel_link}: {e}")

    async def start_live_monitoring(self):
        """مراقبة الرسائل الجديدة مباشرة"""

        @self.client.on(events.NewMessage(chats=CHANNELS))
        async def handler(event):
            print(f"🆕 New message received!")
            await self.process_message(event.message)

        print("👀 Monitoring channels for new messages...")
        await self.client.run_until_disconnected()

    async def run(self, mode='history'):
        """تشغيل السكرابر"""
        await self.client.start(phone=PHONE)
        print("✅ Connected to Telegram")

        if mode == 'history':
            # سكرابينج التاريخ
            for channel in CHANNELS:
                await self.scrape_channel_history(channel)

            # حفظ البيانات في ملف JSON
            with open('products.json', 'w', encoding='utf-8') as f:
                json.dump(self.products, f, ensure_ascii=False, indent=2)

            print(f"\n✅ Scraped {len(self.products)} products")
            print("📁 Data saved to products.json")

        elif mode == 'live':
            # المراقبة المباشرة
            await self.start_live_monitoring()


# الاستخدام
if __name__ == '__main__':
    scraper = TelegramProductScraper()

    # اختر الوضع:
    # 'history' - لسكرابينج الرسائل القديمة
    # 'live' - للمراقبة المباشرة للرسائل الجديدة

    asyncio.run(scraper.run(mode='history'))
    # asyncio.run(scraper.run(mode='live'))
