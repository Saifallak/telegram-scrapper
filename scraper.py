import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, Optional

import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UserNotParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest

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
    'https://t.me/+VAkpot4taw_v9n2p': 'أدوات منزلية',
    'https://t.me/+UbRrLCJUETxcZmWJ': 'لعب أطفال',
    'https://t.me/+TQHOHpqeFZ4a2Lmp': 'مستحضرات التجميل',
    # 'https://t.me/+T1hjkvhugV4GxRYD': 'ملابس داخلية',
    'https://t.me/+Tx6OTiWMi6WS4Y2j': 'مفروشات',
    'https://t.me/+Sbbi6_lLOI2_wP41': 'شرابات',
    # 'https://t.me/+R5rjl2_-KV3GWYAr': 'ملابس البيت و اللانجيري',
    'https://t.me/+WQ-FJCIwbKrcw2qC': 'ملابس اطفال',
    'https://t.me/+SSyWF7Ya89yPm2_V': 'اكسسوارات',
    'https://t.me/+TsQpYNpBaoRkz-8h': 'تصفيات',
}


class TelegramProductScraper:
    def __init__(self):
        print("🛠️ Initializing TelegramClient...", flush=True)
        self.client = TelegramClient('scraper_session', API_ID, API_HASH)
        print("✅ Client initialized", flush=True)
        self.products = []

        # 🆕 للتعامل مع الميديا والرسائل
        self.processed_messages = set()
        self.pending_media = {}
        self.message_cache = {}
        self.channel_entities = {}  # للـ live mode

    def extract_price(self, text: str) -> Dict[str, Optional[float]]:
        """استخراج الأسعار من النص وتحديد الأقل كالسعر الحالي"""
        # 🆕 نظف النص من الإيموجي (أي حرف غير عربي/إنجليزي/رقم/مسافة/علامات ترقيم)
        clean_text = re.sub(r'[^\u0600-\u06FFa-zA-Z0-9\s\.\,\:\+\-\/]', ' ', text)

        price_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م|LE)',
            r'السعر[:\s]+(\d+(?:\.\d+)?)',
            r'بسعر[:\s]+(\d+(?:\.\d+)?)',
            r'بـ\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*ج(?!\w)',  # ج متبوعة بمسافة أو نهاية
        ]

        all_prices = set()

        # نبحث في النص الأصلي والنص المنظف
        for search_text in [text, clean_text]:
            for pattern in price_patterns:
                matches = re.findall(pattern, search_text)
                for match in matches:
                    try:
                        price = float(match)
                        # تجاهل الأرقام الغريبة (أكبر من 100000 أو أصغر من 1)
                        if 1 <= price <= 100000:
                            all_prices.add(price)
                    except (ValueError, TypeError):
                        pass

        prices = {'current_price': None, 'old_price': None}

        if all_prices:
            prices['current_price'] = min(all_prices)
            if len(all_prices) > 1:
                prices['old_price'] = max(all_prices)
        else:
            # fallback: نبحث عن أي رقم في النص المنظف بعد كلمة "السعر"
            price_context = re.search(r'السعر.*?(\d+(?:\.\d+)?)', clean_text)
            if price_context:
                try:
                    price = float(price_context.group(1))
                    if 1 <= price <= 100000:
                        prices['current_price'] = price
                except (ValueError, TypeError):
                    pass

            # لو لسه مفيش سعر، نجيب أول رقم معقول
            if not prices['current_price']:
                numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', clean_text)
                for num_str in numbers:
                    try:
                        num = float(num_str)
                        if 10 <= num <= 100000:  # نفترض إن السعر على الأقل 10 جنيه
                            prices['current_price'] = num
                            break
                    except (ValueError, TypeError):
                        pass

        return prices

    async def download_image(self, message, index: int) -> Optional[str]:
        """تحميل الصورة/الفيديو/المستند وحفظه بالامتداد الصحيح"""
        media_dir = 'downloaded_images'
        os.makedirs(media_dir, exist_ok=True)

        ext = 'unknown'

        if getattr(message.media, 'photo', None):
            ext = 'jpg'
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
                ext = mime.split('/')[-1]

        filename = f"{media_dir}/product_{message.chat_id}_{message.id}_{index}.{ext}"

        if os.path.exists(filename):
            print(f"🟡 Skipping download (already exists): {filename}", flush=True)
            return filename

        # 🆕 حماية من FloodWaitError
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await message.download_media(file=filename)
                print(f"📥 Downloaded new media: {filename}", flush=True)
                return filename
            except FloodWaitError as e:
                if attempt < max_retries - 1:
                    print(
                        f"⏳ FloodWait during download: waiting {e.seconds} seconds... (attempt {attempt + 1}/{max_retries})",
                        flush=True)
                    await asyncio.sleep(e.seconds)
                else:
                    print(f"❌ Failed to download after {max_retries} attempts due to FloodWait", flush=True)
                    return None
            except Exception as e:
                print(f"Error downloading media: {e}", flush=True)
                return None

        return None

    async def send_to_backend(self, product_data: Dict):
        """إرسال البيانات للـ Backend مع رفع الصور/الفيديوهات كملفات"""
        if not BACKEND_URL:
            print("⚠️ BACKEND_URL غير موجود، حفظ البيانات محليًا.", flush=True)
            offline_file = 'offline_products.json'
            data = []
            if os.path.exists(offline_file):
                with open(offline_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            if any(p['unique_id'] == product_data['unique_id'] for p in data):
                print(f"⏭️ Product already exists locally: {product_data['unique_id']}", flush=True)
            else:
                data.append(product_data)
                with open(offline_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"💾 Product saved locally: {product_data['name']}", flush=True)
            return

        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()

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

                prices = product_data.get('prices', {})
                if prices.get('old_price'):
                    form.add_field('variants[0][price]', str(prices['old_price']))
                    form.add_field('variants[0][discount]', str(prices['current_price']))
                else:
                    form.add_field('variants[0][price]', str(prices.get('current_price') or 0))

                for media_path in product_data.get('images', []):
                    if os.path.exists(media_path):
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

                        if content_type is None or content_type.startswith('video/'):
                            print(f"⚠️ Skipping media (unsupported type): {media_path}", flush=True)
                            continue

                        form.add_field(
                            'variants[0][images][]',
                            open(media_path, 'rb'),
                            filename=os.path.basename(media_path),
                            content_type=content_type
                        )

                headers = {
                    'Authorization': f"Bearer {os.getenv('BACKEND_TOKEN', '')}",
                    'Accept': "application/json",
                    'Accept-Language': "ar",
                    'Tenant-Id': "7",
                    'Referer': "https://rosyland.obranchy.com",
                }

                async with session.post(BACKEND_URL, data=form, headers=headers) as resp:
                    resp_text = await resp.text()
                    if resp.status in [200, 201]:
                        print(f"✅ Product sent successfully: {product_data['name']}", flush=True)
                    else:
                        print(f"❌ Failed to send product: {resp.status}", flush=True)
                        print(f"🧾 Response: {resp_text}", flush=True)

        except Exception as e:
            print(f"Error sending to backend: {e}", flush=True)

    async def collect_previous_media(self, entity, message, max_lookback=20):
        """جمع الصور/الفيديوهات من الرسائل السابقة اللي بدون نص"""
        media_list = []
        chat_id = message.chat_id

        try:
            if chat_id in self.message_cache:
                for msg_id in range(message.id - 1, max(message.id - max_lookback - 1, 0), -1):
                    if msg_id in self.message_cache[chat_id]:
                        prev_msg = self.message_cache[chat_id][msg_id]

                        if prev_msg.text and prev_msg.text.strip():
                            break

                        if (getattr(prev_msg.media, 'photo', None) or
                                getattr(prev_msg.media, 'document', None) or
                                getattr(prev_msg.media, 'video', None)):
                            media_list.append(prev_msg)
            else:
                # 🆕 حماية من FloodWaitError
                while True:
                    try:
                        async for prev_msg in self.client.iter_messages(
                                entity,
                                offset_id=message.id,
                                limit=max_lookback
                        ):
                            if chat_id not in self.message_cache:
                                self.message_cache[chat_id] = {}
                            self.message_cache[chat_id][prev_msg.id] = prev_msg

                            if prev_msg.text and prev_msg.text.strip():
                                break

                            if (getattr(prev_msg.media, 'photo', None) or
                                    getattr(prev_msg.media, 'document', None) or
                                    getattr(prev_msg.media, 'video', None)):
                                media_list.append(prev_msg)
                        break  # نجحت العملية
                    except FloodWaitError as e:
                        print(f"⏳ FloodWait in collect_previous_media: waiting {e.seconds} seconds...", flush=True)
                        await asyncio.sleep(e.seconds)

        except Exception as e:
            print(f"⚠️ Error collecting previous media: {e}", flush=True)

        return list(reversed(media_list))

    async def process_message(self, message, channel_name: str = None, entity=None):
        """معالجة رسالة واحدة"""
        chat_id = message.chat_id
        unique_id = f"{chat_id}_{message.id}"

        if unique_id in self.processed_messages:
            return

        if chat_id not in self.message_cache:
            self.message_cache[chat_id] = {}
        self.message_cache[chat_id][message.id] = message

        if not message.text or not message.text.strip():
            if chat_id not in self.pending_media:
                self.pending_media[chat_id] = []

            if (getattr(message.media, 'photo', None) or
                    getattr(message.media, 'document', None) or
                    getattr(message.media, 'video', None)):
                self.pending_media[chat_id].append(message)
                print(f"📸 Media buffered: {len(self.pending_media[chat_id])} pending", flush=True)
            return

        self.processed_messages.add(unique_id)

        product = {
            'unique_id': unique_id,
            'channel_id': chat_id,
            'message_id': message.id,
            'timestamp': message.date.isoformat(),
            'channel_name': channel_name,
            'description': message.text or '',
            'images': [],
            'prices': {'current_price': None, 'old_price': None}
        }

        text = message.text.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # تحديد الاسم والوصف القصير والكبير
        if len(lines) == 0:
            name = ""
            short_desc = ""
            long_desc = ""
        elif len(lines) == 1:
            name = lines[0]
            short_desc = ""
            long_desc = ""
        elif len(lines) == 2:
            name = lines[0]
            short_desc = lines[1]
            long_desc = ""
        else:
            name = lines[0]
            short_desc = lines[1]
            long_desc = "\n".join(lines[2:])

        product['name'] = re.sub(r'(?i)\bاسم المنتج\b', '', name).strip()
        product['description'] = long_desc  # الوصف الكبير
        product['short_description'] = short_desc

        product['prices'] = self.extract_price(message.text)

        if chat_id in self.pending_media and self.pending_media[chat_id]:
            print(f"🔗 Collecting {len(self.pending_media[chat_id])} buffered media", flush=True)
            for idx, pending_msg in enumerate(self.pending_media[chat_id]):
                media_path = await self.download_image(pending_msg, idx)
                if media_path:
                    product['images'].append(media_path)
                self.processed_messages.add(f"{chat_id}_{pending_msg.id}")

            self.pending_media[chat_id] = []

        if entity:
            prev_media_messages = await self.collect_previous_media(entity, message)
            if prev_media_messages:
                print(f"🔍 Found {len(prev_media_messages)} previous media messages", flush=True)

                for prev_msg in prev_media_messages:
                    prev_unique_id = f"{chat_id}_{prev_msg.id}"
                    if prev_unique_id not in self.processed_messages:
                        media_path = await self.download_image(prev_msg, len(product['images']))
                        if media_path:
                            product['images'].append(media_path)
                        self.processed_messages.add(prev_unique_id)

        if (getattr(message.media, 'photo', None) or
                getattr(message.media, 'document', None) or
                getattr(message.media, 'video', None)):
            media_path = await self.download_image(message, len(product['images']))
            if media_path:
                product['images'].append(media_path)

        if not product['images']:
            print(f"❌ Product skipped (no media): {product['name']}", flush=True)
            return

        self.products.append(product)
        await self.send_to_backend(product)

        print(
            f"📦 Product processed: {product['name'][:50]} | {len(product['images'])} images | Price: {product['prices']['current_price']}",
            flush=True)

    async def scrape_channel_history(self, channel_link: str):
        """سكرابينج تاريخ القناة مع batch processing"""
        try:
            stop_date_str = os.getenv('STOP_DATE', '')
            stop_date = None
            if stop_date_str:
                try:
                    stop_date = datetime.strptime(stop_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    print(f"📅 Stop date set to: {stop_date.date()}", flush=True)
                except ValueError:
                    print("⚠️ تنبيه: تنسيق STOP_DATE غير صحيح! استخدم YYYY-MM-DD.", flush=True)

            channel_name = CHANNELS.get(channel_link, 'قناة غير معروفة')

            while True:
                try:
                    entity = await self.client.get_entity(channel_link)

                    try:
                        me = await self.client.get_me()
                        await self.client(GetParticipantRequest(channel=entity, participant=me))
                        print(f"✅ Already a member of {entity.title} ({channel_name})", flush=True)
                    except UserNotParticipantError:
                        try:
                            await self.client(JoinChannelRequest(entity))
                            print(f"✅ Joined {entity.title} ({channel_name})", flush=True)
                        except UserAlreadyParticipantError:
                            print(f"✅ Already joined {entity.title}", flush=True)

                    break

                except FloodWaitError as e:
                    print(f"⏳ Flood wait: need to wait {e.seconds} seconds...", flush=True)
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"❌ Failed to get entity {channel_link}: {e}", flush=True)
                    return

            print(f"🔍 Scraping channel: {entity.title} ({channel_name})", flush=True)

            # حفظ الـ entity للـ live mode
            self.channel_entities[entity.id] = (entity, channel_name)

            chat_id = entity.id
            self.message_cache[chat_id] = {}
            self.pending_media[chat_id] = []

            batch_size = 100
            messages_batch = []

            async for message in self.client.iter_messages(entity):
                if stop_date and message.date < stop_date:
                    print(f"⏹️ Stopped at {message.date}", flush=True)
                    break

                self.message_cache[chat_id][message.id] = message
                messages_batch.append(message)

                if len(messages_batch) >= batch_size:
                    print(f"⚙️ Processing batch of {len(messages_batch)} messages...", flush=True)
                    for msg in reversed(messages_batch):
                        await self.process_message(msg, channel_name, entity)
                    messages_batch = []
                    await asyncio.sleep(1)

            if messages_batch:
                print(f"⚙️ Processing final batch of {len(messages_batch)} messages...", flush=True)
                for msg in reversed(messages_batch):
                    await self.process_message(msg, channel_name, entity)

        except Exception as e:
            print(f"Error scraping channel {channel_link}: {e}", flush=True)

    async def start_live_monitoring(self):
        """مراقبة الرسائل الجديدة مباشرة"""

        @self.client.on(events.NewMessage(chats=list(self.channel_entities.keys())))
        async def handler(event):
            print(f"🆕 New message received from chat_id: {event.chat_id}!", flush=True)
            try:
                chat_id = event.chat_id

                # نجيب الـ entity والاسم من الـ cache
                if chat_id in self.channel_entities:
                    entity, channel_name = self.channel_entities[chat_id]
                    print(f"📍 Channel identified: {channel_name}", flush=True)
                    await self.process_message(event.message, channel_name, entity)
                else:
                    # لو مش موجود في الـ cache، نحاول نجيبه
                    print(f"⚠️ Unknown channel: {chat_id}, attempting to identify...", flush=True)
                    try:
                        entity = await event.get_chat()
                        # نشوف لو القناة موجودة في الـ CHANNELS
                        found = False
                        for link, name in CHANNELS.items():
                            # نحاول نطابق بالـ ID أو الـ username
                            if str(entity.id) in link or (
                                    hasattr(entity, 'username') and entity.username and entity.username in link):
                                channel_name = name
                                self.channel_entities[chat_id] = (entity, channel_name)
                                print(f"✅ Channel identified and cached: {channel_name}", flush=True)
                                await self.process_message(event.message, channel_name, entity)
                                found = True
                                break

                        if not found:
                            print(f"❌ Channel not found in CHANNELS dict", flush=True)
                    except Exception as e:
                        print(f"❌ Failed to identify channel: {e}", flush=True)

            except Exception as e:
                print(f"❌ Error in live handler: {e}", flush=True)

        print("👀 Monitoring channels for new messages...", flush=True)
        print(f"📡 Monitoring {len(self.channel_entities)} channels: {list(self.channel_entities.keys())}", flush=True)
        await self.client.run_until_disconnected()

    async def run(self, mode='history'):
        """تشغيل السكرابر"""
        print("🔄 Connecting to Telegram...", flush=True)

        # 🆕 حماية الاتصال من FloodWaitError
        while True:
            try:
                await self.client.start(phone=PHONE)
                print("✅ Connected to Telegram", flush=True)
                break
            except FloodWaitError as e:
                print(f"⏳ FloodWait during connection: waiting {e.seconds} seconds...", flush=True)
                await asyncio.sleep(e.seconds)

        if mode == 'history':
            for channel in CHANNELS:
                await self.scrape_channel_history(channel)

            with open('products.json', 'w', encoding='utf-8') as f:
                json.dump(self.products, f, ensure_ascii=False, indent=2)

            print(f"\n✅ Scraped {len(self.products)} products", flush=True)
            print("📁 Data saved to products.json", flush=True)

        elif mode == 'live':
            # في الـ live mode، لازم نجيب الـ entities الأول
            for channel in CHANNELS:
                while True:
                    try:
                        entity = await self.client.get_entity(channel)
                        self.channel_entities[entity.id] = (entity, CHANNELS[channel])
                        break
                    except FloodWaitError as e:
                        print(f"⏳ FloodWait getting entity for live mode: waiting {e.seconds} seconds...", flush=True)
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        print(f"❌ Failed to get entity for {channel}: {e}", flush=True)
                        break

            await self.start_live_monitoring()

        elif mode == 'hybrid':
            print("🌀 Hybrid mode: Scraping history first, then monitoring live...", flush=True)

            for channel in CHANNELS:
                print(f"Start Fetching Channel ({channel})...", flush=True)
                await self.scrape_channel_history(channel)

            print(f"\n✅ Finished scraping history ({len(self.products)} products).", flush=True)
            print("👀 Now switching to live monitoring...\n", flush=True)

            await self.start_live_monitoring()


if __name__ == '__main__':
    scraper = TelegramProductScraper()
    asyncio.run(scraper.run(mode='hybrid'))
