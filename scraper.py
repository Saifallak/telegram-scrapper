import os
import re
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Telegram API credentials
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE = os.getenv('TELEGRAM_PHONE')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000/api/products')

# قنوات التليجرام
CHANNELS = [
    'https://t.me/+VAkpot4taw_v9n2p',  # ادوات منزلية
    'https://t.me/+UbRrLCJUETxcZmWJ',  # لعب اطفال
    'https://t.me/+TQHOHpqeFZ4a2Lmp',  # مستحضرات تجميل
    'https://t.me/+T1hjkvhugV4GxRYD',  # ملابس داخلية
    'https://t.me/+Tx6OTiWMi6WS4Y2j',  # مفروشات
    'https://t.me/+Sbbi6_lLOI2_wP41',  # شرابات
    'https://t.me/+R5rjl2_-KV3GWYAr',  # هوم وير ولانجيري
    'https://t.me/+WQ-FJCIwbKrcw2qC',  # ملابس اطفال
    'https://t.me/+SSyWF7Ya89yPm2_V',  # اكسسوارات
    'https://t.me/+TsQpYNpBaoRkz-8h',  # تصفيات
]

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
        """تحميل الصورة وحفظها محلياً"""
        try:
            photo_dir = 'downloaded_images'
            os.makedirs(photo_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{photo_dir}/product_{message.id}_{index}_{timestamp}.jpg"
            
            await message.download_media(file=filename)
            return filename
        except Exception as e:
            print(f"Error downloading image: {e}")
            return None

    async def send_to_backend(self, product_data: Dict):
        """إرسال البيانات للـ Backend"""
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
    
    async def process_message(self, message):
        """معالجة رسالة واحدة"""
        if not message.text and not message.media:
            return
        
        product = {
            'channel_id': message.chat_id,
            'message_id': message.id,
            'timestamp': message.date.isoformat(),
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
        
        # إرسال للـ Backend
        await self.send_to_backend(product)
        
        print(f"📦 Product processed: {product['description'][:50]}... | Price: {product['prices']['current_price']}")
    
    async def scrape_channel_history(self, channel_link: str, limit: int = 100):
        """سكرابينج تاريخ القناة"""
        try:
            # الانضمام للقناة
            entity = await self.client.get_entity(channel_link)
            print(f"🔍 Scraping channel: {entity.title}")
            
            # جلب آخر الرسائل
            async for message in self.client.iter_messages(entity, limit=limit):
                await self.process_message(message)
                await asyncio.sleep(0.5)  # تجنب Rate limiting
                
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
    
    async def run(self, mode='history', limit=100):
        """تشغيل السكرابر"""
        await self.client.start(phone=PHONE)
        print("✅ Connected to Telegram")
        
        if mode == 'history':
            # سكرابينج التاريخ
            for channel in CHANNELS:
                await self.scrape_channel_history(channel, limit)
            
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
    
    asyncio.run(scraper.run(mode='history', limit=100))
    # asyncio.run(scraper.run(mode='live'))
