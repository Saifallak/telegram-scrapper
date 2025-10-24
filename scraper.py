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
        """استخراج الأسعار من النص وتحديد الأقل كالسعر الحالي"""
        # جميع الأنماط الممكنة لاستخراج السعر
        price_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م|LE)',
            r'السعر[:\s]+(\d+(?:\.\d+)?)',
            r'بسعر[:\s]+(\d+(?:\.\d+)?)',
            r'بـ(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*ج',  # زي 199ج أو 220ج
        ]

        all_prices = set()

        for pattern in price_patterns:
            for match in re.findall(pattern, text):
                try:
                    all_prices.add(float(match))
                except ValueError:
                    pass

        prices = {
            'current_price': None,
            'old_price': None
        }

        if all_prices:
            prices['current_price'] = min(all_prices)
            if len(all_prices) > 1:
                prices['old_price'] = max(all_prices)

        # fallback بسيط لو مفيش أي نمط معروف
        if not prices['current_price']:
            match = re.search(r'(\d+(?:\.\d+)?)', text)
            if match:
                prices['current_price'] = float(match.group(1))

        return prices

    async def download_image(self, message, index: int) -> Optional[str]:
        """تحميل الصورة/الفيديو/المستند وحفظه بالامتداد الصحيح"""
        try:
            media_dir = 'downloaded_images'
            os.makedirs(media_dir, exist_ok=True)

            ext = 'unknown'

            # الصور
            if getattr(message.media, 'photo', None):
                ext = 'jpg'
            # المستندات أو الفيديوهات
            elif getattr(message.media, 'document', None) and hasattr(message.media.document, 'mime_type'):
                mime = message.media.document.mime_type
                if 'png' in mime:
                    ext = 'png'
                elif 'gif' in mime:
                    ext = 'gif'
                elif 'jpeg' in mime:
                    ext = 'jpg'
                elif 'mp4' in mime:
                    ext = 'mp4'
                elif 'webp' in mime:
                    ext = 'webp'
                else:
                    ext = mime.split('/')[-1]  # fallback لأي نوع آخر

            filename = f"{media_dir}/product_{message.chat_id}_{message.id}_{index}.{ext}"

            if os.path.exists(filename):
                print(f"🟡 Skipping download (already exists): {filename}")
                return filename

            await message.download_media(file=filename)
            print(f"📥 Downloaded new media: {filename}")
            return filename

        except Exception as e:
            print(f"Error downloading media: {e}")
            return None

    async def send_to_backend(self, product_data: Dict):
        """إرسال البيانات للـ Backend مع رفع الصور/الفيديوهات كملفات"""
        if not BACKEND_URL:
            print("⚠️ BACKEND_URL غير موجود، حفظ البيانات محليًا.")
            offline_file = 'offline_products.json'
            data = []
            if os.path.exists(offline_file):
                with open(offline_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            if any(p['unique_id'] == product_data['unique_id'] for p in data):
                print(f"⏭️ Product already exists locally: {product_data['unique_id']}")
            else:
                data.append(product_data)
                with open(offline_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"💾 Product saved locally: {product_data['name']}")
            return

        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()

                # الحقول النصية
                form.add_field('variants[0][sku]', product_data.get('unique_id', ''))
                form.add_field('variants[0][barcode]', product_data.get('unique_id', ''))
                form.add_field('variants[0][stock]', '10')
                form.add_field('name[ar]', product_data.get('name', ''))
                form.add_field('name[en]', product_data.get('name', ''))
                form.add_field('description[ar]', product_data.get('description', ''))
                form.add_field('description[en]', product_data.get('description', ''))
                form.add_field('short_description[ar]', product_data.get('description', ''))
                form.add_field('short_description[en]', product_data.get('description', ''))
                form.add_field('category_name', product_data.get('channel_name', ''))

                # الأسعار
                prices = product_data.get('prices', {})
                if prices.get('old_price'):
                    form.add_field('variants[0][price]', str(prices['old_price']))
                    form.add_field('variants[0][discount]', str(prices['current_price']))
                else:
                    form.add_field('variants[0][price]', str(prices.get('current_price') or 0))

                # رفع الصور/الفيديوهات كملفات
                for media_path in product_data.get('images', []):
                    if os.path.exists(media_path):
                        # تحديد نوع الميديا بناءً على امتداد الملف
                        ext = os.path.splitext(media_path)[1].lower()
                        if ext in ['.jpg', '.jpeg']:
                            content_type = 'image/jpeg'
                        elif ext == '.png':
                            content_type = 'image/png'
                        elif ext == '.gif':
                            content_type = 'image/gif'
                        elif ext == '.webp':
                            content_type = 'image/webp'
                        elif ext == '.mp4':
                            content_type = 'video/mp4'
                        else:
                            content_type = None

                        # إذا عايز تتخطى الفيديوهات
                        if content_type is None or content_type.startswith('video/'):
                            print(f"⚠️ Skipping media (unsupported type): {media_path}")
                            continue

                        form.add_field(
                            'variants[0][images][]',
                            open(media_path, 'rb'),
                            filename=os.path.basename(media_path),
                            content_type=content_type
                        )

                headers = {
                    'Authorization': f"Bearer {os.getenv('BACKEND_TOKEN', '')}",  # هنا تحط التوكن
                    'Accept': "application/json",
                    'Tenant-Id': "7",  # "https://www.bepucepehutozy.me"
                    'Referer': "https://rosyland.obranchy.com",
                }

                # إرسال البيانات
                async with session.post(BACKEND_URL, data=form, headers=headers) as resp:
                    resp_text = await resp.text()
                    if resp.status in [200, 201]:
                        print(f"✅ Product sent successfully: {product_data['name']}")
                    else:
                        print(f"❌ Failed to send product: {resp.status}")
                        print(f"🧾 Response: {resp_text}")

        except Exception as e:
            print(f"Error sending to backend: {e}")

    async def process_message(self, message, channel_name: str = None):
        """معالجة رسالة واحدة"""
        if not message.text:
            return  # لازم يكون فيه نص

        # نتأكد من وجود أي ميديا (صورة أو فيديو أو document)
        if not (getattr(message.media, 'photo', None) or
                getattr(message.media, 'document', None) or
                getattr(message.media, 'video', None)):
            print(f"⚠️ Skipping message without media: {message.text[:50]}...")
            return

        unique_id = f"{message.chat_id}_{message.id}"

        product = {
            'unique_id': unique_id,
            'channel_id': message.chat_id,
            'message_id': message.id,
            'timestamp': message.date.isoformat(),
            'channel_name': channel_name,
            'description': message.text or '',
            'images': [],
            'prices': {'current_price': None, 'old_price': None}
        }

        # استخراج الاسم
        text = message.text.strip()
        lines = text.splitlines()
        if lines:
            first_line = lines[0].strip()
            if re.search(r'\bوصل\b', first_line):
                name = lines[1].strip() if len(lines) > 1 else first_line
            else:
                name = first_line
        else:
            name = ""
        product['name'] = name

        # استخراج الأسعار
        product['prices'] = self.extract_price(message.text)

        # تحميل الميديا (صورة أو فيديو أو document)
        media_path = await self.download_image(message, 0)
        if media_path:
            product['images'].append(media_path)

        # تجاهل المنتج لو مافيش ميديا فعلياً
        if not product['images']:
            print(f"❌ Product skipped (no media downloaded): {product['name']}")
            return

        # حفظ البيانات محلياً
        self.products.append(product)

        # إرسال المنتج للـ backend
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
            # سكرابينج التاريخ فقط
            for channel in CHANNELS:
                await self.scrape_channel_history(channel)

            with open('products.json', 'w', encoding='utf-8') as f:
                json.dump(self.products, f, ensure_ascii=False, indent=2)

            print(f"\n✅ Scraped {len(self.products)} products")
            print("📁 Data saved to products.json")

        elif mode == 'live':
            # المراقبة المباشرة فقط
            await self.start_live_monitoring()

        elif mode == 'hybrid':
            # 🌀 الوضع الهجين: التاريخ ثم المراقبة المباشرة
            print("🌀 Hybrid mode: Scraping history first, then monitoring live...")

            for channel in CHANNELS:
                await self.scrape_channel_history(channel)

            print(f"\n✅ Finished scraping history ({len(self.products)} products).")
            print("👀 Now switching to live monitoring...\n")

            await self.start_live_monitoring()


# الاستخدام
if __name__ == '__main__':
    scraper = TelegramProductScraper()

    # اختر الوضع:
    # 'history' - لسكرابينج الرسائل القديمة
    # 'live' - للمراقبة المباشرة للرسائل الجديدة

    asyncio.run(scraper.run(mode='hybrid'))
