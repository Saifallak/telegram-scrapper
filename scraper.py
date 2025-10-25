"""
Telegram Product Scraper with AI Integration
============================================
A robust scraper for extracting product data from Telegram channels
with support for Gemini AI extraction and fallback to manual parsing.
"""

import asyncio
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UserNotParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest

# ============================================
# Configuration
# ============================================

load_dotenv()


class Config:
    """Application configuration"""
    # Telegram
    API_ID = os.getenv('TELEGRAM_API_ID')
    API_HASH = os.getenv('TELEGRAM_API_HASH')
    PHONE = os.getenv('TELEGRAM_PHONE')

    # Backend
    BACKEND_URL = os.getenv('BACKEND_URL', '')
    BACKEND_TOKEN = os.getenv('BACKEND_TOKEN', '')
    TENANT_ID = os.getenv('TENANT_ID', '7')

    # AI
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash-latest')

    # Scraping
    STOP_DATE = os.getenv('STOP_DATE', '')
    BATCH_SIZE = int(os.getenv('BATCH_SIZE', '100'))
    MAX_LOOKBACK = int(os.getenv('MAX_LOOKBACK', '20'))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))

    # Paths
    MEDIA_DIR = Path('downloaded_images')
    SESSION_FILE = 'scraper_session'
    PRODUCTS_FILE = 'products.json'
    OFFLINE_FILE = 'offline_products.json'
    FAILED_FILE = 'failed_products.json'


class ExtractionMethod(Enum):
    """Extraction method types"""
    GEMINI = "✨ Gemini AI"
    MANUAL = "🔧 Manual"


# Telegram Channels Configuration
CHANNELS = {
    'https://t.me/+VAkpot4taw_v9n2p': 'أدوات منزلية',
    'https://t.me/+UbRrLCJUETxcZmWJ': 'لعب أطفال',
    'https://t.me/+TQHOHpqeFZ4a2Lmp': 'مستحضرات التجميل',
    'https://t.me/+Tx6OTiWMi6WS4Y2j': 'مفروشات',
    'https://t.me/+Sbbi6_lLOI2_wP41': 'شرابات',
    'https://t.me/+WQ-FJCIwbKrcw2qC': 'ملابس اطفال',
    'https://t.me/+SSyWF7Ya89yPm2_V': 'اكسسوارات',
    'https://t.me/+TsQpYNpBaoRkz-8h': 'تصفيات',
}


# ============================================
# Data Models
# ============================================

@dataclass
class ProductPrice:
    """Product pricing information"""
    current_price: Optional[float] = None
    old_price: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    def is_valid(self) -> bool:
        """Check if price data is valid"""
        return self.current_price is not None and self.current_price > 0


@dataclass
class ProductData:
    """Product data model"""
    unique_id: str
    channel_id: int
    message_id: int
    timestamp: str
    channel_name: str
    name: str
    description: str
    short_description: str
    images: List[str]
    prices: ProductPrice
    extraction_method: str = ExtractionMethod.MANUAL.value

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['prices'] = self.prices.to_dict()
        return data

    def is_valid(self) -> bool:
        """Validate product data"""
        return (
                bool(self.name) and
                bool(self.images) and
                self.prices.is_valid()
        )


# ============================================
# Utilities
# ============================================

class Logger:
    """Simple logging utility"""

    @staticmethod
    def info(message: str):
        print(f"ℹ️  {message}", flush=True)

    @staticmethod
    def success(message: str):
        print(f"✅ {message}", flush=True)

    @staticmethod
    def warning(message: str):
        print(f"⚠️  {message}", flush=True)

    @staticmethod
    def error(message: str):
        print(f"❌ {message}", flush=True)

    @staticmethod
    def debug(message: str):
        print(f"🔍 {message}", flush=True)


class FileManager:
    """Handle file operations"""

    @staticmethod
    def ensure_dir(path: Path):
        """Create directory if it doesn't exist"""
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_json(file_path: Path, default=None) -> any:
        """Load JSON file with error handling"""
        if default is None:
            default = []

        if not file_path.exists():
            return default

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            Logger.error(f"Failed to parse {file_path}: {e}")
            return default

    @staticmethod
    def save_json(data: any, file_path: Path):
        """Save data to JSON file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            Logger.success(f"Saved to {file_path}")
        except Exception as e:
            Logger.error(f"Failed to save {file_path}: {e}")


# ============================================
# Extractors
# ============================================

class PriceExtractor:
    """Extract prices from Arabic text"""

    PRICE_PATTERNS = [
        r'(\d+(?:\.\d+)?)\s*(?:جنيه|ج\.م|LE)',
        r'السعر[:\s]+(\d+(?:\.\d+)?)',
        r'بسعر[:\s]+(\d+(?:\.\d+)?)',
        r'بـ\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*ج(?!\w)',
    ]

    MIN_PRICE = 1
    MAX_PRICE = 100000

    @classmethod
    def extract(cls, text: str) -> ProductPrice:
        """Extract price information from text"""
        # Normalize text: replace comma decimals with dots
        text_normalized = re.sub(r'(\d+),(\d+)', r'\1.\2', text)

        # Clean text from emojis
        clean_text = re.sub(
            r'[^\u0600-\u06FFa-zA-Z0-9\s\.\,\:\+\-\/]',
            ' ',
            text_normalized
        )

        all_prices = cls._find_all_prices(text_normalized, clean_text)

        if all_prices:
            return ProductPrice(
                current_price=min(all_prices),
                old_price=max(all_prices) if len(all_prices) > 1 else None
            )

        # Fallback: contextual search
        price = cls._contextual_search(clean_text)
        if price:
            return ProductPrice(current_price=price)

        # Last resort: first valid number
        return ProductPrice(current_price=cls._first_valid_number(clean_text))

    @classmethod
    def _find_all_prices(cls, *texts) -> set:
        """Find all prices in given texts"""
        all_prices = set()

        for text in texts:
            for pattern in cls.PRICE_PATTERNS:
                matches = re.findall(pattern, text)
                for match in matches:
                    try:
                        price = float(match)
                        if cls.MIN_PRICE <= price <= cls.MAX_PRICE:
                            all_prices.add(price)
                    except (ValueError, TypeError):
                        continue

        return all_prices

    @classmethod
    def _contextual_search(cls, text: str) -> Optional[float]:
        """Search for price after 'السعر' keyword"""
        price_context = re.search(r'السعر.*?(\d+(?:\.\d+)?)', text)
        if price_context:
            try:
                price = float(price_context.group(1))
                if cls.MIN_PRICE <= price <= cls.MAX_PRICE:
                    return price
            except (ValueError, TypeError):
                pass
        return None

    @classmethod
    def _first_valid_number(cls, text: str) -> Optional[float]:
        """Get first valid number from text"""
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', text)
        for num_str in numbers:
            try:
                num = float(num_str)
                if cls.MIN_PRICE <= num <= cls.MAX_PRICE:
                    return num
            except (ValueError, TypeError):
                continue
        return None


class TextExtractor:
    """Extract product information from text"""

    @staticmethod
    def extract(text: str) -> Dict[str, str]:
        """Extract name, short description, and full description"""
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if not lines:
            return {
                'name': '',
                'short_description': '',
                'description': ''
            }

        if len(lines) == 1:
            return {
                'name': TextExtractor._clean_name(lines[0]),
                'short_description': '',
                'description': ''
            }

        if len(lines) == 2:
            return {
                'name': TextExtractor._clean_name(lines[0]),
                'short_description': lines[1],
                'description': ''
            }

        return {
            'name': TextExtractor._clean_name(lines[0]),
            'short_description': lines[1],
            'description': '\n'.join(lines[2:])
        }

    @staticmethod
    def _clean_name(name: str) -> str:
        """Clean product name"""
        return re.sub(r'(?i)\bاسم المنتج\b', '', name).strip()


class GeminiExtractor:
    """Extract product data using Gemini AI"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1/models"

    # Available models (as of 2024)
    AVAILABLE_MODELS = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
        'gemini-1.5-pro',
        'gemini-1.5-pro-latest',
        'gemini-pro',
    ]

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash-latest"):
        self.api_key = api_key
        # Use correct model name format
        if not model.startswith('models/'):
            model = f"models/{model}"
        self.model = model
        self.enabled = bool(api_key)

        if self.enabled:
            Logger.info(f"Gemini model: {model}")

    @staticmethod
    async def list_available_models(api_key: str) -> List[str]:
        """List all available Gemini models"""
        url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = []
                        for model in data.get('models', []):
                            name = model.get('name', '').replace('models/', '')
                            if 'generateContent' in model.get('supportedGenerationMethods', []):
                                models.append(name)
                        return models
        except Exception as e:
            Logger.error(f"Failed to list models: {e}")

        return []

    async def extract(self, text: str, channel_name: str) -> Optional[Dict]:
        """Extract product data using Gemini AI"""
        if not self.enabled:
            return None

        try:
            prompt = self._build_prompt(text, channel_name)
            response = await self._call_api(prompt)
            return self._parse_response(response)
        except Exception as e:
            Logger.warning(f"Gemini extraction failed: {e}")
            return None

    def _build_prompt(self, text: str, channel_name: str) -> str:
        """Build extraction prompt"""
        return f"""أنت خبير في استخراج بيانات المنتجات من رسائل التليجرام.
استخرج المعلومات التالية من النص بدقة:

النص:
{text}

القناة: {channel_name}

استخرج التالي بصيغة JSON:
{{
    "name": "اسم المنتج (السطر الأول عادة)",
    "short_description": "وصف قصير (السطر الثاني إذا وُجد)",
    "description": "الوصف الكامل (باقي النص)",
    "current_price": رقم السعر الحالي أو null,
    "old_price": السعر القديم إذا وُجد أو null
}}

ملاحظات مهمة:
- السعر يكون بصيغة رقمية فقط (مثال: 150 أو 150.5)
- تجاهل الإيموجي والرموز
- إذا كان هناك سعرين، الأقل هو current_price والأعلى old_price
- إذا كان سعر واحد فقط، ضعه في current_price واترك old_price null
- قد يكون السعر مكتوب: "150 جنيه" أو "بسعر 150" أو "السعر: 150 ج"
- امسح أي ذكر لكلمة "اسم المنتج" من الاسم

أرجع JSON فقط بدون أي نص إضافي."""

    async def _call_api(self, prompt: str) -> Dict:
        """Call Gemini API"""
        # Remove 'models/' prefix if present for URL construction
        model_name = self.model.replace('models/', '')
        url = f"{self.BASE_URL}/{model_name}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1000,
                "topP": 0.8,
                "topK": 10
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API error {resp.status}: {error_text}")

                return await resp.json()

    def _parse_response(self, response: Dict) -> Optional[Dict]:
        """Parse Gemini response"""
        if 'candidates' not in response or not response['candidates']:
            return None

        content = response['candidates'][0]['content']['parts'][0]['text']

        # Extract JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            return None

        return json.loads(json_match.group(0))


# ============================================
# Media Handler
# ============================================

class MediaHandler:
    """Handle media download and management"""

    SUPPORTED_EXTENSIONS = {
        'image/jpeg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp',
        'video/mp4': 'mp4'
    }

    def __init__(self, media_dir: Path, max_retries: int = 3):
        self.media_dir = media_dir
        self.max_retries = max_retries
        FileManager.ensure_dir(media_dir)

    async def download(self, message, index: int) -> Optional[str]:
        """Download media from message"""
        ext = self._get_extension(message)
        if not ext:
            return None

        filename = self._build_filename(message, index, ext)

        if filename.exists():
            Logger.debug(f"Media already exists: {filename.name}")
            return str(filename)

        return await self._download_with_retry(message, filename)

    def _get_extension(self, message) -> Optional[str]:
        """Determine file extension from message"""
        if getattr(message.media, 'photo', None):
            return 'jpg'

        if getattr(message.media, 'document', None):
            mime = getattr(message.media.document, 'mime_type', '')
            return self.SUPPORTED_EXTENSIONS.get(mime)

        return None

    def _build_filename(self, message, index: int, ext: str) -> Path:
        """Build filename for media"""
        return self.media_dir / f"product_{message.chat_id}_{message.id}_{index}.{ext}"

    async def _download_with_retry(self, message, filename: Path) -> Optional[str]:
        """Download with retry on FloodWait"""
        for attempt in range(self.max_retries):
            try:
                await message.download_media(file=str(filename))
                Logger.success(f"Downloaded: {filename.name}")
                return str(filename)
            except FloodWaitError as e:
                if attempt < self.max_retries - 1:
                    Logger.warning(
                        f"FloodWait: {e.seconds}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(e.seconds)
                else:
                    Logger.error(f"Download failed after {self.max_retries} attempts")
                    return None
            except Exception as e:
                Logger.error(f"Download error: {e}")
                return None

        return None


# ============================================
# Backend Integration
# ============================================

class BackendClient:
    """Handle backend API communication"""

    def __init__(self, config: Config):
        self.config = config
        self.enabled = bool(config.BACKEND_URL)

    async def send_product(self, product: ProductData) -> bool:
        """Send product to backend"""
        if not self.enabled:
            self._save_offline(product)
            return False

        try:
            async with aiohttp.ClientSession() as session:
                form = self._build_form_data(product)
                headers = self._build_headers()

                async with session.post(
                        self.config.BACKEND_URL,
                        data=form,
                        headers=headers,
                        timeout=60
                ) as resp:
                    if resp.status in [200, 201]:
                        Logger.success(f"Product sent: {product.name[:50]}")
                        return True
                    else:
                        error_text = await resp.text()
                        Logger.error(f"Backend error {resp.status}: {error_text}")
                        self._save_failed(product)
                        return False

        except Exception as e:
            Logger.error(f"Failed to send product: {e}")
            self._save_failed(product)
            return False

    def _build_form_data(self, product: ProductData) -> aiohttp.FormData:
        """Build form data for backend"""
        form = aiohttp.FormData()

        # Basic fields
        form.add_field('variants[0][sku]', product.unique_id)
        form.add_field('variants[0][barcode]', product.unique_id)
        form.add_field('variants[0][stock]', '10')
        form.add_field('name[ar]', product.name)
        form.add_field('name[en]', product.name)
        form.add_field('description[ar]', product.description)
        form.add_field('description[en]', product.description)
        form.add_field('short_description[ar]', product.short_description)
        form.add_field('short_description[en]', product.short_description)
        form.add_field('category_name', product.channel_name)

        # Pricing
        if product.prices.old_price:
            form.add_field('variants[0][price]', str(product.prices.old_price))
            form.add_field('variants[0][discount]', str(product.prices.current_price))
        else:
            form.add_field('variants[0][price]', str(product.prices.current_price or 0))

        # Images
        for media_path in product.images:
            if Path(media_path).exists():
                self._add_image_field(form, media_path)

        return form

    def _add_image_field(self, form: aiohttp.FormData, media_path: str):
        """Add image field to form"""
        ext = Path(media_path).suffix.lower()
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }

        content_type = content_type_map.get(ext)
        if content_type:
            form.add_field(
                'variants[0][images][]',
                open(media_path, 'rb'),
                filename=Path(media_path).name,
                content_type=content_type
            )

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        return {
            'Authorization': f"Bearer {self.config.BACKEND_TOKEN}",
            'Accept': "application/json",
            'Accept-Language': "ar",
            'Tenant-Id': self.config.TENANT_ID,
        }

    def _save_offline(self, product: ProductData):
        """Save product offline"""
        data = FileManager.load_json(Path(self.config.OFFLINE_FILE))

        if not any(p.get('unique_id') == product.unique_id for p in data):
            data.append(product.to_dict())
            FileManager.save_json(data, Path(self.config.OFFLINE_FILE))

    def _save_failed(self, product: ProductData):
        """Save failed product"""
        data = FileManager.load_json(Path(self.config.FAILED_FILE))
        data.append(product.to_dict())
        FileManager.save_json(data, Path(self.config.FAILED_FILE))


# ============================================
# Main Scraper
# ============================================

class TelegramProductScraper:
    """Main scraper class"""

    def __init__(self, config: Config):
        self.config = config
        self.client = TelegramClient(config.SESSION_FILE, config.API_ID, config.API_HASH)

        # Components
        self.gemini = GeminiExtractor(config.GEMINI_API_KEY, config.GEMINI_MODEL)
        self.media_handler = MediaHandler(config.MEDIA_DIR, config.MAX_RETRIES)
        self.backend = BackendClient(config)

        # State
        self.products: List[ProductData] = []
        self.processed_messages = set()
        self.pending_media = defaultdict(list)
        self.message_cache = defaultdict(dict)
        self.channel_entities = {}

        Logger.info("Scraper initialized")
        if self.gemini.enabled:
            Logger.success("Gemini AI enabled")
        else:
            Logger.warning("Gemini AI disabled - using manual extraction")

    async def extract_product_info(
            self,
            text: str,
            channel_name: str
    ) -> Tuple[Dict[str, str], ProductPrice, ExtractionMethod]:
        """Extract product information with AI fallback"""
        # Try Gemini first
        gemini_result = await self.gemini.extract(text, channel_name)

        if gemini_result:
            text_data = {
                'name': gemini_result.get('name', ''),
                'short_description': gemini_result.get('short_description', ''),
                'description': gemini_result.get('description', '')
            }
            price_data = ProductPrice(
                current_price=gemini_result.get('current_price'),
                old_price=gemini_result.get('old_price')
            )
            return text_data, price_data, ExtractionMethod.GEMINI

        # Fallback to manual
        text_data = TextExtractor.extract(text)
        price_data = PriceExtractor.extract(text)
        return text_data, price_data, ExtractionMethod.MANUAL

    async def collect_previous_media(
            self,
            entity,
            message,
            max_lookback: int = None
    ) -> List:
        """Collect media from previous messages without text"""
        if max_lookback is None:
            max_lookback = self.config.MAX_LOOKBACK

        media_list = []
        chat_id = message.chat_id

        try:
            # Check cache first
            if chat_id in self.message_cache:
                media_list = self._collect_from_cache(chat_id, message.id, max_lookback)
            else:
                media_list = await self._collect_from_telegram(
                    entity, message, max_lookback
                )
        except Exception as e:
            Logger.warning(f"Error collecting previous media: {e}")

        return list(reversed(media_list))

    def _collect_from_cache(
            self,
            chat_id: int,
            message_id: int,
            max_lookback: int
    ) -> List:
        """Collect media from cached messages"""
        media_list = []

        for msg_id in range(message_id - 1, max(message_id - max_lookback - 1, 0), -1):
            if msg_id in self.message_cache[chat_id]:
                prev_msg = self.message_cache[chat_id][msg_id]

                if prev_msg.text and prev_msg.text.strip():
                    break

                if self._has_media(prev_msg):
                    media_list.append(prev_msg)

        return media_list

    async def _collect_from_telegram(
            self,
            entity,
            message,
            max_lookback: int
    ) -> List:
        """Collect media from Telegram with FloodWait handling"""
        media_list = []
        chat_id = message.chat_id

        while True:
            try:
                async for prev_msg in self.client.iter_messages(
                        entity,
                        offset_id=message.id,
                        limit=max_lookback
                ):
                    # Cache message
                    self.message_cache[chat_id][prev_msg.id] = prev_msg

                    if prev_msg.text and prev_msg.text.strip():
                        break

                    if self._has_media(prev_msg):
                        media_list.append(prev_msg)

                break
            except FloodWaitError as e:
                Logger.warning(f"FloodWait: waiting {e.seconds}s...")
                await asyncio.sleep(e.seconds)

        return media_list

    @staticmethod
    def _has_media(message) -> bool:
        """Check if message has media"""
        return bool(
            getattr(message.media, 'photo', None) or
            getattr(message.media, 'document', None) or
            getattr(message.media, 'video', None)
        )

    async def process_message(
            self,
            message,
            channel_name: str,
            entity=None
    ):
        """Process a single message"""
        chat_id = message.chat_id
        unique_id = f"{chat_id}_{message.id}"

        # Skip if already processed
        if unique_id in self.processed_messages:
            return

        # Cache message
        self.message_cache[chat_id][message.id] = message

        # Handle media-only messages
        if not message.text or not message.text.strip():
            if self._has_media(message):
                self.pending_media[chat_id].append(message)
                Logger.debug(f"Buffered media: {len(self.pending_media[chat_id])} pending")
            return

        # Mark as processed
        self.processed_messages.add(unique_id)

        # Extract product information
        text_data, price_data, method = await self.extract_product_info(
            message.text,
            channel_name
        )

        # Create product
        product = ProductData(
            unique_id=unique_id,
            channel_id=chat_id,
            message_id=message.id,
            timestamp=message.date.isoformat(),
            channel_name=channel_name,
            name=text_data['name'],
            short_description=text_data['short_description'],
            description=text_data['description'],
            images=[],
            prices=price_data,
            extraction_method=method.value
        )

        # Collect all media
        await self._collect_all_media(product, message, entity, chat_id)

        # Validate and save
        if not product.is_valid():
            Logger.warning(f"Invalid product skipped: {product.name}")
            return

        self.products.append(product)
        await self.backend.send_product(product)

        Logger.info(
            f"[{method.value}] {product.name[:50]} | "
            f"{len(product.images)} images | "
            f"Price: {product.prices.current_price}"
        )

    async def _collect_all_media(
            self,
            product: ProductData,
            message,
            entity,
            chat_id: int
    ):
        """Collect all media for product"""
        # 1. Buffered media
        if self.pending_media[chat_id]:
            Logger.debug(f"Collecting {len(self.pending_media[chat_id])} buffered media")
            for pending_msg in self.pending_media[chat_id]:
                await self._add_media_to_product(product, pending_msg)
            self.pending_media[chat_id].clear()

        # 2. Previous media (if entity available)
        if entity:
            prev_media = await self.collect_previous_media(entity, message)
            if prev_media:
                Logger.debug(f"Found {len(prev_media)} previous media")
                for prev_msg in prev_media:
                    prev_id = f"{chat_id}_{prev_msg.id}"
                    if prev_id not in self.processed_messages:
                        await self._add_media_to_product(product, prev_msg)

        # 3. Current message media
        if self._has_media(message):
            await self._add_media_to_product(product, message)

    async def _add_media_to_product(self, product: ProductData, message):
        """Add media from message to product"""
        media_path = await self.media_handler.download(message, len(product.images))
        if media_path:
            product.images.append(media_path)

        # Mark message as processed
        unique_id = f"{message.chat_id}_{message.id}"
        self.processed_messages.add(unique_id)

    async def join_channel(self, channel_link: str) -> Optional[Tuple]:
        """Join channel and return entity with name"""
        channel_name = CHANNELS.get(channel_link, 'Unknown Channel')

        while True:
            try:
                entity = await self.client.get_entity(channel_link)

                # Check if already a member
                try:
                    me = await self.client.get_me()
                    await self.client(GetParticipantRequest(channel=entity, participant=me))
                    Logger.success(f"Already member of {entity.title}")
                except UserNotParticipantError:
                    try:
                        await self.client(JoinChannelRequest(entity))
                        Logger.success(f"Joined {entity.title}")
                    except UserAlreadyParticipantError:
                        Logger.success(f"Already joined {entity.title}")

                return entity, channel_name

            except FloodWaitError as e:
                Logger.warning(f"FloodWait: {e.seconds}s...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                Logger.error(f"Failed to join {channel_link}: {e}")
                return None

    async def scrape_channel_history(self, channel_link: str):
        """Scrape channel history with batch processing"""
        result = await self.join_channel(channel_link)
        if not result:
            return

        entity, channel_name = result
        Logger.info(f"Scraping: {entity.title} ({channel_name})")

        # Cache entity for live mode
        self.channel_entities[entity.id] = (entity, channel_name)

        # Initialize caches
        chat_id = entity.id
        self.message_cache[chat_id] = {}
        self.pending_media[chat_id] = []

        # Parse stop date
        stop_date = None
        if self.config.STOP_DATE:
            try:
                stop_date = datetime.strptime(
                    self.config.STOP_DATE,
                    '%Y-%m-%d'
                ).replace(tzinfo=timezone.utc)
                Logger.info(f"Stop date: {stop_date.date()}")
            except ValueError:
                Logger.warning("Invalid STOP_DATE format (use YYYY-MM-DD)")

        # Process messages in batches
        messages_batch = []

        try:
            async for message in self.client.iter_messages(entity):
                # Check stop date
                if stop_date and message.date < stop_date:
                    Logger.info(f"Stopped at {message.date}")
                    break

                # Cache and batch
                self.message_cache[chat_id][message.id] = message
                messages_batch.append(message)

                # Process batch
                if len(messages_batch) >= self.config.BATCH_SIZE:
                    await self._process_batch(messages_batch, channel_name, entity)
                    messages_batch = []
                    await asyncio.sleep(1)  # Rate limiting

            # Process remaining messages
            if messages_batch:
                await self._process_batch(messages_batch, channel_name, entity)

        except Exception as e:
            Logger.error(f"Error scraping {channel_link}: {e}")

    async def _process_batch(
            self,
            messages: List,
            channel_name: str,
            entity
    ):
        """Process a batch of messages"""
        Logger.info(f"Processing batch of {len(messages)} messages...")
        for msg in reversed(messages):
            await self.process_message(msg, channel_name, entity)

    async def start_live_monitoring(self):
        """Monitor channels for new messages"""

        @self.client.on(events.NewMessage(chats=list(self.channel_entities.keys())))
        async def handler(event):
            Logger.info(f"New message from chat_id: {event.chat_id}")

            try:
                chat_id = event.chat_id

                # Get channel info from cache
                if chat_id in self.channel_entities:
                    entity, channel_name = self.channel_entities[chat_id]
                    Logger.debug(f"Channel: {channel_name}")
                    await self.process_message(event.message, channel_name, entity)
                else:
                    # Try to identify unknown channel
                    await self._identify_and_process_unknown(event)

            except Exception as e:
                Logger.error(f"Error in live handler: {e}")

        Logger.success("Live monitoring started")
        Logger.info(f"Monitoring {len(self.channel_entities)} channels")
        await self.client.run_until_disconnected()

    async def _identify_and_process_unknown(self, event):
        """Identify and process message from unknown channel"""
        Logger.warning(f"Unknown channel: {event.chat_id}")

        try:
            entity = await event.get_chat()

            # Try to match with known channels
            for link, name in CHANNELS.items():
                if self._is_channel_match(entity, link):
                    self.channel_entities[event.chat_id] = (entity, name)
                    Logger.success(f"Channel identified: {name}")
                    await self.process_message(event.message, name, entity)
                    return

            Logger.error("Channel not found in CHANNELS")

        except Exception as e:
            Logger.error(f"Failed to identify channel: {e}")

    @staticmethod
    def _is_channel_match(entity, link: str) -> bool:
        """Check if entity matches channel link"""
        return (
                str(entity.id) in link or
                (hasattr(entity, 'username') and entity.username and entity.username in link)
        )

    async def connect(self):
        """Connect to Telegram with retry"""
        Logger.info("Connecting to Telegram...")

        while True:
            try:
                await self.client.start(phone=self.config.PHONE)
                Logger.success("Connected to Telegram")
                return
            except FloodWaitError as e:
                Logger.warning(f"FloodWait during connection: {e.seconds}s...")
                await asyncio.sleep(e.seconds)

    async def run(self, mode: str = 'history'):
        """Run scraper in specified mode"""
        await self.connect()

        if mode == 'history':
            await self._run_history_mode()
        elif mode == 'live':
            await self._run_live_mode()
        elif mode == 'hybrid':
            await self._run_hybrid_mode()
        else:
            Logger.error(f"Unknown mode: {mode}")

    async def _run_history_mode(self):
        """Run in history mode"""
        Logger.info("Mode: History")

        for channel in CHANNELS:
            await self.scrape_channel_history(channel)

        # Save results
        FileManager.save_json(
            [p.to_dict() for p in self.products],
            Path(self.config.PRODUCTS_FILE)
        )

        Logger.success(f"Scraped {len(self.products)} products")

    async def _run_live_mode(self):
        """Run in live mode"""
        Logger.info("Mode: Live")

        # Get entities for all channels
        for channel in CHANNELS:
            result = await self.join_channel(channel)
            if result:
                entity, channel_name = result
                self.channel_entities[entity.id] = (entity, channel_name)

        await self.start_live_monitoring()

    async def _run_hybrid_mode(self):
        """Run in hybrid mode (history + live)"""
        Logger.info("Mode: Hybrid")

        # Scrape history first
        for channel in CHANNELS:
            Logger.info(f"Fetching channel: {channel}")
            await self.scrape_channel_history(channel)

        Logger.success(f"History done: {len(self.products)} products")
        Logger.info("Switching to live monitoring...")

        # Start live monitoring
        await self.start_live_monitoring()


# ============================================
# Entry Point
# ============================================

async def main():
    """Main entry point"""
    config = Config()

    # Validate configuration
    if not all([config.API_ID, config.API_HASH, config.PHONE]):
        Logger.error("Missing Telegram credentials in .env file")
        return

    Logger.info("=== Telegram Product Scraper ===")
    Logger.info(f"Batch size: {config.BATCH_SIZE}")
    Logger.info(f"Max retries: {config.MAX_RETRIES}")

    # Validate Gemini API if provided
    if config.GEMINI_API_KEY:
        Logger.info("Checking Gemini API...")
        available_models = await GeminiExtractor.list_available_models(config.GEMINI_API_KEY)

        if available_models:
            Logger.success(f"Gemini API valid. Available models: {len(available_models)}")

            # Check if selected model is available
            model_name = config.GEMINI_MODEL.replace('models/', '')
            if model_name not in available_models:
                Logger.warning(f"Model '{model_name}' not found. Available:")
                for model in available_models[:5]:  # Show first 5
                    Logger.info(f"  - {model}")
                Logger.warning("Will try anyway, but might fail")
        else:
            Logger.warning("Could not verify Gemini API key")

    # Create and run scraper
    scraper = TelegramProductScraper(config)

    # Get mode from environment or default to hybrid
    mode = os.getenv('SCRAPER_MODE', 'hybrid')

    try:
        await scraper.run(mode=mode)
    except KeyboardInterrupt:
        Logger.info("Scraper stopped by user")
    except Exception as e:
        Logger.error(f"Fatal error: {e}")
        raise


if __name__ == '__main__':
    asyncio.run(main())
