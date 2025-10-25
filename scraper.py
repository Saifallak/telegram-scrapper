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

    # AI - Support multiple API keys separated by comma
    GEMINI_API_KEYS = [
        key.strip() for key in os.getenv('GEMINI_API_KEY', '').split(',') if key.strip()
    ]
    # Models will be fetched dynamically from Google API

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


class QuotaType(Enum):
    """Types of quota limits"""
    RATE_LIMIT = "rate_limit"  # Per minute - wait and retry
    DAILY_LIMIT = "daily_limit"  # Per day - skip to next model


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

    @staticmethod
    def append_product_to_json(product: ProductData, file_path: Path):
        """Append or update single product in JSON file"""
        try:
            existing_data = FileManager.load_json(file_path, default=[])
            product_dict = product.to_dict()

            # ✅ Replace existing if found, otherwise append
            for i, p in enumerate(existing_data):
                if p.get('unique_id') == product.unique_id:
                    existing_data[i] = product_dict
                    Logger.debug(f"Product updated in {file_path}: {product.name[:30]}...")
                    break
            else:
                existing_data.append(product_dict)
                Logger.debug(f"Product added to {file_path}: {product.name[:30]}...")

            # Save file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            Logger.error(f"Failed to append/update product to {file_path}: {e}")


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
    """Extract product data using Gemini AI with automatic model rotation and multi-key support"""

    BASE_URL = "https://generativelanguage.googleapis.com/v1/models"

    # Preferred model order (fastest to slowest)
    MODEL_PRIORITY = [
        'gemini-1.5-flash-8b',
        'gemini-2.0-flash-exp',
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
        'gemini-exp-1206',
        'gemini-1.5-pro',
        'gemini-1.5-pro-latest',
        'gemini-pro',
    ]

    def __init__(self, api_keys: List[str], models: List[str] = None):
        self.api_keys = api_keys  # List of API keys
        self.current_key_index = 0
        self.models = []
        self.current_model_index = 0
        self.exhausted_models = set()  # Models exhausted for current key
        self.exhausted_keys = set()  # Keys that are fully exhausted
        self.enabled = bool(self.api_keys)

        # Models will be loaded later using fetch_available_models
        if models:
            self.models = [f"models/{m}" if not m.startswith('models/') else m for m in models if m]

        if not self.enabled:
            Logger.warning("No Gemini API keys provided")
        else:
            Logger.info(f"Initialized with {len(self.api_keys)} API key(s)")

    def get_current_api_key(self) -> Optional[str]:
        """Get current active API key"""
        if not self.enabled or not self.api_keys:
            return None

        # All keys exhausted
        if len(self.exhausted_keys) >= len(self.api_keys):
            Logger.error("All API keys exhausted!")
            self.enabled = False
            return None

        # Skip exhausted keys
        while self.current_key_index in self.exhausted_keys:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

        return self.api_keys[self.current_key_index]

    def rotate_api_key(self):
        """Rotate to next API key and reset model exhaustion"""
        if not self.enabled or not self.api_keys:
            return

        current_key_num = self.current_key_index + 1
        Logger.warning(f"API Key #{current_key_num} exhausted all models")
        self.exhausted_keys.add(self.current_key_index)

        # Reset model exhaustion for new key
        self.exhausted_models.clear()
        self.current_model_index = 0

        # Try next key
        next_index = (self.current_key_index + 1) % len(self.api_keys)

        # Find next available key
        while next_index in self.exhausted_keys and len(self.exhausted_keys) < len(self.api_keys):
            next_index = (next_index + 1) % len(self.api_keys)

        if next_index not in self.exhausted_keys:
            self.current_key_index = next_index
            next_key_num = next_index + 1
            Logger.info(f"Switched to API Key #{next_key_num} ({next_key_num}/{len(self.api_keys)})")
        else:
            Logger.error("All API keys exhausted - switching to manual extraction!")
            self.enabled = False

    async def fetch_available_models(self) -> bool:
        """Fetch available models from Google API and sort by priority"""
        api_key = self.get_current_api_key()
        if not api_key:
            return False

        try:
            Logger.info("Fetching available models from Google...")
            available = await self.list_available_models(api_key)

            if not available:
                Logger.error("No models available from Google API")
                return False

            # Sort models by priority
            sorted_models = []
            for priority_model in self.MODEL_PRIORITY:
                if priority_model in available:
                    sorted_models.append(f"models/{priority_model}")

            # Add remaining models not in priority list
            for model in available:
                model_with_prefix = f"models/{model}"
                if model_with_prefix not in sorted_models:
                    sorted_models.append(model_with_prefix)

            self.models = sorted_models

            Logger.success(f"Loaded {len(self.models)} models from Google:")
            for i, model in enumerate(self.models[:5], 1):  # Show first 5
                Logger.info(f"  {i}. {model.replace('models/', '')}")
            if len(self.models) > 5:
                Logger.info(f"  ... and {len(self.models) - 5} more")

            return True

        except Exception as e:
            Logger.error(f"Failed to fetch models: {e}")
            return False

    @staticmethod
    async def list_available_models(api_key: str) -> List[str]:
        """List all available Gemini models that support generateContent"""
        url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = []
                        for model in data.get('models', []):
                            name = model.get('name', '').replace('models/', '')
                            # Only include models that support generateContent
                            if 'generateContent' in model.get('supportedGenerationMethods', []):
                                models.append(name)
                        return models
        except Exception as e:
            Logger.error(f"Failed to list models: {e}")

        return []

    def get_current_model(self) -> Optional[str]:
        """Get current active model"""
        if not self.enabled or not self.models:
            return None

        # All models exhausted
        if len(self.exhausted_models) >= len(self.models):
            Logger.error("All Gemini models exhausted!")
            self.enabled = False
            return None

        # Skip exhausted models
        while self.current_model_index in self.exhausted_models:
            self.current_model_index = (self.current_model_index + 1) % len(self.models)

        return self.models[self.current_model_index]

    def rotate_model(self):
        """Rotate to next model (for daily quota exhaustion)"""
        if not self.enabled or not self.models:
            return

        current_model = self.models[self.current_model_index].replace('models/', '')
        Logger.warning(f"Model '{current_model}' daily quota exhausted")
        self.exhausted_models.add(self.current_model_index)

        # Try next model
        next_index = (self.current_model_index + 1) % len(self.models)

        # Find next available model
        while next_index in self.exhausted_models and len(self.exhausted_models) < len(self.models):
            next_index = (next_index + 1) % len(self.models)

        if next_index not in self.exhausted_models:
            self.current_model_index = next_index
            next_model = self.models[next_index].replace('models/', '')
            Logger.info(f"Switched to model: {next_model} ({self.current_model_index + 1}/{len(self.models)})")
        else:
            # All models exhausted for this key
            Logger.warning("All models exhausted for current API key")
            self.rotate_api_key()

    @staticmethod
    def _parse_quota_error(error_text: str) -> Tuple[QuotaType, Optional[float]]:
        """
        Parse quota error to determine type and retry delay
        Returns: (quota_type, retry_seconds)
        """
        error_lower = error_text.lower()

        # Check for daily quota exhaustion
        if 'per day' in error_lower or 'perdayperprojectpermodel' in error_lower:
            return QuotaType.DAILY_LIMIT, None

        # Check for rate limit with retry delay
        retry_match = re.search(r'retry in ([0-9.]+)s', error_lower)
        if retry_match:
            retry_seconds = float(retry_match.group(1))
            return QuotaType.RATE_LIMIT, retry_seconds

        # Check for explicit rate limit messages
        if any(keyword in error_lower for keyword in ['per minute', 'rate limit', 'requests per minute']):
            # Default to 60 seconds if no retry time specified
            return QuotaType.RATE_LIMIT, 60.0

        # Default: treat as daily limit
        return QuotaType.DAILY_LIMIT, None

    async def extract(self, text: str, channel_name: str) -> Optional[Dict]:
        """Extract product data using Gemini AI with intelligent quota handling"""
        if not self.enabled:
            return None

        max_attempts = len(self.models) * len(self.api_keys)
        attempt = 0

        while attempt < max_attempts:
            model = self.get_current_model()
            api_key = self.get_current_api_key()

            if not model or not api_key:
                return None

            try:
                prompt = self._build_prompt(text, channel_name)
                response = await self._call_api(prompt, model, api_key)
                return self._parse_response(response)

            except Exception as e:
                error_msg = str(e)
                error_lower = error_msg.lower()

                # Check if quota error (429)
                if any(keyword in error_lower for keyword in
                       ['quota', 'rate', 'limit', '429', 'resource_exhausted', 'resource has been exhausted']):

                    # Parse error to determine quota type
                    quota_type, retry_seconds = self._parse_quota_error(error_msg)

                    if quota_type == QuotaType.RATE_LIMIT and retry_seconds:
                        # Rate limit - wait and retry with same model
                        Logger.warning(f"⏱️ Rate limit hit - waiting {retry_seconds:.1f}s before retry...")
                        await asyncio.sleep(retry_seconds + 1)  # Add 1 second buffer
                        Logger.info("Retrying with same model after rate limit wait...")
                        # Don't increment attempt or change model, just retry
                        continue

                    elif quota_type == QuotaType.DAILY_LIMIT:
                        # Daily limit - switch model immediately
                        Logger.warning(f"📅 Daily quota exhausted for current model")
                        self.rotate_model()
                        attempt += 1

                        if self.enabled:
                            Logger.info(f"Trying next model (attempt {attempt + 1}/{max_attempts})...")
                            await asyncio.sleep(0.5)  # Small delay
                            continue
                        else:
                            Logger.error("All models and keys exhausted - switching to manual extraction")
                            return None

                    else:
                        # Unknown quota error - treat as daily limit
                        Logger.warning(f"Unknown quota error: {e}")
                        self.rotate_model()
                        attempt += 1
                        if self.enabled:
                            continue
                        else:
                            return None

                # Handle 503 errors (service overloaded)
                elif "unavailable" in error_lower or "503" in error_lower or "overloaded" in error_lower:
                    Logger.warning(f"🔄 Model overloaded (503) - rotating to next model")
                    self.rotate_model()
                    attempt += 1

                    if self.enabled:
                        Logger.info(f"Retrying with next model (attempt {attempt + 1}/{max_attempts})...")
                        await asyncio.sleep(2)
                        continue
                    else:
                        Logger.error("All models exhausted - switching to manual extraction")
                        return None

                else:
                    # Other errors (parsing, network, etc.)
                    Logger.warning(f"Gemini extraction failed: {e}")
                    return None

        Logger.error("All retry attempts failed")
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
    "name": "اسم المنتج (السطر الأول عادة) مع حذف الاسعار منه",
    "short_description": "وصف قصير (السطر الثاني عادة) مع حذف الاسعار منه لو مش موجود وصف قصير انشئه بحد اقصي ١٦٠ حرف",
    "description": "الوصف الكامل (باقي النص عادة) مع حذف الاسعار منه لو مش موجود وصف انشئه بدون حد اقصي",
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

    async def _call_api(self, prompt: str, model: str, api_key: str) -> Dict:
        """Call Gemini API with specified model and API key"""
        # Remove 'models/' prefix if present for URL construction
        model_name = model.replace('models/', '')
        url = f"{self.BASE_URL}/{model_name}:generateContent?key={api_key}"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
                "topP": 0.8,
                "topK": 10
            },
            # Add safety settings to be more permissive
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as resp:
                response_text = await resp.text()

                if resp.status != 200:
                    raise Exception(f"API error {resp.status}: {response_text}")

                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as e:
                    Logger.error(f"Failed to parse API response: {e}")
                    Logger.debug(f"Response text: {response_text[:500]}...")
                    raise Exception(f"Invalid JSON response from API")

    def _parse_response(self, response: Dict) -> Optional[Dict]:
        """Parse Gemini response"""
        try:
            # Check if response has candidates
            if 'candidates' not in response or not response['candidates']:
                Logger.warning("No candidates in Gemini response")
                Logger.debug(f"Full response: {json.dumps(response, indent=2, ensure_ascii=False)[:500]}")
                return None

            candidate = response['candidates'][0]

            # Check finish reason (safety filters, etc.)
            finish_reason = candidate.get('finishReason', 'UNKNOWN')
            if finish_reason != 'STOP':
                Logger.warning(f"Gemini stopped with reason: {finish_reason}")

                if finish_reason == 'MAX_TOKENS':
                    Logger.warning("Response truncated due to MAX_TOKENS — retrying with next model...")
                    self.rotate_model()
                    return None

                # Check for safety ratings
                if 'safetyRatings' in candidate:
                    Logger.debug(f"Safety ratings: {candidate['safetyRatings']}")

                # If blocked by safety, try to continue anyway
                if finish_reason in ['SAFETY', 'RECITATION', 'OTHER']:
                    Logger.warning(f"Content filtered by Gemini ({finish_reason}), falling back to manual extraction")
                    return None

            # Check if candidate has content
            if 'content' not in candidate:
                Logger.warning("No content in Gemini candidate")
                Logger.debug(f"Candidate structure: {json.dumps(candidate, indent=2, ensure_ascii=False)[:500]}")
                return None

            content = candidate['content']

            # Check if content has parts
            if 'parts' not in content or not content['parts']:
                Logger.warning("No parts in Gemini content")
                Logger.debug(f"Content structure: {json.dumps(content, indent=2, ensure_ascii=False)[:500]}")
                Logger.debug(f"Full candidate: {json.dumps(candidate, indent=2, ensure_ascii=False)[:1000]}")
                return None

            # Get text from first part
            text = content['parts'][0].get('text', '')

            if not text:
                Logger.warning("Empty text in Gemini response")
                return None

            # Extract JSON from response
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if not json_match:
                Logger.warning(f"No JSON found in response: {text[:100]}...")
                return None

            return json.loads(json_match.group(0))

        except KeyError as e:
            Logger.warning(f"Missing key in Gemini response: {e}")
            return None
        except json.JSONDecodeError as e:
            Logger.warning(f"Failed to parse JSON from Gemini: {e}")
            return None
        except Exception as e:
            Logger.warning(f"Unexpected error parsing Gemini response: {e}")
            return None


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

        def safe_str(value):
            """Convert None → empty string safely"""
            return '' if value is None else str(value)

        form = aiohttp.FormData()

        # 🧱 Basic fields
        form.add_field('variants[0][sku]', safe_str(product.unique_id))
        form.add_field('variants[0][barcode]', safe_str(product.unique_id))
        form.add_field('variants[0][stock]', '10')
        form.add_field('name[ar]', safe_str(product.name))
        form.add_field('name[en]', safe_str(product.name))
        form.add_field('description[ar]', safe_str(product.description))
        form.add_field('description[en]', safe_str(product.description))
        form.add_field('short_description[ar]', safe_str(product.short_description))
        form.add_field('short_description[en]', safe_str(product.short_description))
        form.add_field('category_name', safe_str(product.channel_name))

        # 💰 Pricing
        price = product.prices.current_price
        old_price = product.prices.old_price

        if old_price is not None and price is not None:
            form.add_field('variants[0][price]', safe_str(old_price))
            form.add_field('variants[0][discount]', safe_str(price))
        else:
            form.add_field(
                'variants[0][price]',
                safe_str(price or old_price or 0)
            )

        # 🖼️ Images
        for media_path in product.images:
            if media_path and Path(media_path).exists():
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
        FileManager.append_product_to_json(product, Path(self.config.OFFLINE_FILE))

    def _save_failed(self, product: ProductData):
        """Save failed product"""
        FileManager.append_product_to_json(product, Path(self.config.FAILED_FILE))


# ============================================
# Main Scraper
# ============================================

class TelegramProductScraper:
    """Main scraper class"""

    def __init__(self, config: Config):
        self.config = config
        self.client = TelegramClient(config.SESSION_FILE, config.API_ID, config.API_HASH)

        # Components
        self.gemini = GeminiExtractor(config.GEMINI_API_KEYS)
        self.media_handler = MediaHandler(config.MEDIA_DIR, config.MAX_RETRIES)
        self.backend = BackendClient(config)

        # State
        self.products: List[ProductData] = []
        self.processed_messages = set()
        self.pending_media = defaultdict(list)
        self.message_cache = defaultdict(dict)
        self.channel_entities = {}

        # Statistics
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'offline': 0,
            'gemini_used': 0,
            'manual_used': 0
        }

        Logger.info("Scraper initialized")
        # Gemini status will be confirmed after fetching models

    async def extract_product_info(
            self,
            text: str,
            channel_name: str
    ) -> Tuple[Dict[str, str], ProductPrice, ExtractionMethod]:
        """Extract product information with AI fallback"""
        # Try Gemini first
        gemini_result = await self.gemini.extract(text, channel_name)

        if gemini_result:
            self.stats['gemini_used'] += 1
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
        self.stats['manual_used'] += 1
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

        # ✅ Check if product already exists in products.json
        products_path = Path(self.config.PRODUCTS_FILE)
        existing_products = FileManager.load_json(products_path, default=[])

        existing_product_data = next((p for p in existing_products if p.get('unique_id') == unique_id), None)

        if existing_product_data:
            # لو نوع الاستخراج مانيوال، نعيد المحاولة
            if existing_product_data.get('extraction_method') == ExtractionMethod.MANUAL.value:
                Logger.info(f"Product {unique_id} exists but extracted manually — reprocessing with AI...")
            else:
                Logger.info(f"Product {unique_id} already exists — sending to backend only")

                product = ProductData(
                    unique_id=existing_product_data['unique_id'],
                    channel_id=existing_product_data['channel_id'],
                    message_id=existing_product_data['message_id'],
                    timestamp=existing_product_data['timestamp'],
                    channel_name=existing_product_data['channel_name'],
                    name=existing_product_data['name'],
                    short_description=existing_product_data['short_description'],
                    description=existing_product_data['description'],
                    images=existing_product_data.get('images', []),
                    prices=ProductPrice(**existing_product_data['prices']),
                    extraction_method=existing_product_data.get('extraction_method', ExtractionMethod.MANUAL.value)
                )

                success = await self.backend.send_product(product)
                if success:
                    self.stats['success'] += 1
                else:
                    if self.backend.enabled:
                        self.stats['failed'] += 1
                    else:
                        self.stats['offline'] += 1
                return

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

        # Add to memory list
        self.products.append(product)
        self.stats['total'] += 1

        # Save immediately to products.json
        FileManager.append_product_to_json(product, Path(self.config.PRODUCTS_FILE))

        # Try to send to backend
        success = await self.backend.send_product(product)

        if success:
            self.stats['success'] += 1
        else:
            if self.backend.enabled:
                self.stats['failed'] += 1
            else:
                self.stats['offline'] += 1

        # Log with statistics
        Logger.info(
            f"[{method.value}] {product.name[:50]} | "
            f"{len(product.images)} images | "
            f"Price: {product.prices.current_price} | "
            f"Stats: ✅{self.stats['success']} ❌{self.stats['failed']} 💾{self.stats['offline']}"
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

        # Fetch Gemini models from Google API
        if self.gemini.api_keys:
            models_loaded = await self.gemini.fetch_available_models()
            if models_loaded:
                Logger.success(f"Gemini AI enabled with {len(self.gemini.models)} model(s) and {len(self.gemini.api_keys)} API key(s)")
            else:
                Logger.warning("Failed to load Gemini models - using manual extraction")
                self.gemini.enabled = False
        else:
            Logger.warning("No Gemini API keys - using manual extraction")

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

        # Print final statistics
        Logger.success("=" * 50)
        Logger.success(f"Scraping Complete!")
        Logger.success(f"Total products: {self.stats['total']}")
        Logger.success(f"Sent to backend: {self.stats['success']}")
        Logger.success(f"Failed to send: {self.stats['failed']}")
        Logger.success(f"Saved offline: {self.stats['offline']}")
        Logger.success(f"Gemini extractions: {self.stats['gemini_used']}")
        Logger.success(f"Manual extractions: {self.stats['manual_used']}")
        Logger.success("=" * 50)

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

        # Print statistics
        Logger.success("=" * 50)
        Logger.success(f"History Complete!")
        Logger.success(f"Total products: {self.stats['total']}")
        Logger.success(f"Sent to backend: {self.stats['success']}")
        Logger.success(f"Gemini extractions: {self.stats['gemini_used']}")
        Logger.success(f"Manual extractions: {self.stats['manual_used']}")
        Logger.success("=" * 50)

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

    # No need to validate Gemini here - will be done in scraper.run()

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
