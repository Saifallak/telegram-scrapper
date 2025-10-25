# ❓ Frequently Asked Questions (FAQ)

Quick answers to common questions about the Telegram Product Scraper.

---

## 🚀 Getting Started

### Q: Do I need programming knowledge to use this?

**A:** Basic command-line knowledge is helpful, but the setup scripts automate most of the process. If you can:
- Open a terminal
- Edit a text file (.env)
- Run commands like `python scraper.py`

Then you can use this scraper!

---

### Q: What are the system requirements?

**A:** Minimal:
- **Python**: 3.8 or higher
- **RAM**: 512MB minimum
- **Storage**: 1GB for code + downloaded media
- **Internet**: Stable connection required

---

### Q: Is this free to use?

**A:** Yes! The scraper is free and open-source. However:
- **Telegram API**: Free
- **Gemini API**: Free tier (60 req/min, 1500 req/day)
- **Backend**: Depends on your backend service

---

## 🔑 API & Authentication

### Q: How do I get Telegram API credentials?

**A:**
1. Go to https://my.telegram.org
2. Login with your phone number
3. Go to "API Development Tools"
4. Create a new application
5. Copy `API_ID` and `API_HASH`

See [detailed guide in README](README.md#getting-api-keys).

---

### Q: Do I need a Gemini API key?

**A:** No, it's **optional**.
- **With Gemini**: More accurate extraction, understands context better
- **Without Gemini**: Uses manual regex-based extraction (still works!)

The scraper automatically falls back to manual extraction if Gemini fails or isn't configured.

---

### Q: How many requests does scraping use?

**A:** Depends on mode:
- **History mode**: 1 request per message + media downloads
- **Live mode**: 1 request per new message
- **Gemini**: 1 request per product (if enabled)

Example: Scraping 1000 messages ≈ 1000 Telegram requests + 1000 Gemini requests

---

## 🔧 Configuration

### Q: What's the difference between the three modes?

**A:**
| Mode | What it does | Best for |
|------|-------------|----------|
| **history** | Scrapes all past messages | Initial data collection |
| **live** | Monitors new messages only | Real-time updates |
| **hybrid** | Scrapes history, then monitors live | Most common use case |

---

### Q: How do I stop scraping at a specific date?

**A:** Set `STOP_DATE` in `.env`:
```env
STOP_DATE=2024-01-01
```

This will stop when it reaches messages from before this date.

---

### Q: Can I scrape multiple channels?

**A:** Yes! Edit the `CHANNELS` dictionary in `scraper.py`:

```python
CHANNELS = {
    'https://t.me/+YOUR_CHANNEL_1': 'Category 1',
    'https://t.me/+YOUR_CHANNEL_2': 'Category 2',
    # Add as many as you want
}
```

The scraper processes them sequentially (one at a time).

---

## 🐛 Troubleshooting

### Q: I'm getting "FloodWait" errors constantly

**A:** This is normal! Telegram rate-limits requests. The scraper:
- ✅ Automatically waits the required time
- ✅ Resumes after waiting
- ✅ No data is lost

**Tips to reduce FloodWait:**
- Decrease `BATCH_SIZE` (default: 100)
- Add delays between batches
- Scrape during off-peak hours

---

### Q: Why are some products skipped?

**A:** Products are skipped if they're missing:
- ❌ No product name extracted
- ❌ No images/media found
- ❌ No valid price detected

**Solutions:**
1. Enable Gemini API for better extraction
2. Check message format in channels
3. Review `failed_products.json` for details

---

### Q: Gemini API returns "Model not found" error

**A:** The model name might be wrong. Run:
```bash
python test_gemini.py
```

This will:
- List all available models
- Test your API key
- Show recommended models

Update `.env` with a working model:
```env
GEMINI_MODEL=gemini-1.5-flash-latest
```

---

### Q: Session expired error

**A:**
```bash
# Delete the session file
rm scraper_session.session

# Run again (you'll need to re-authenticate)
python scraper.py
```

You'll receive a code via Telegram to log in again.

---

### Q: Backend connection fails

**A:** Check these:
1. Is `BACKEND_URL` correct in `.env`?
2. Is `BACKEND_TOKEN` valid?
3. Is the backend server running?
4. Check network/firewall

**Meanwhile**: Products are saved to `failed_products.json` and can be retried later.

---

## 📊 Data & Output

### Q: Where is the scraped data saved?

**A:** Depends on configuration:
- **With backend**: Sent to your API endpoint
- **Without backend**: Saved to `offline_products.json`
- **Failed sends**: Saved to `failed_products.json`
- **History mode**: Also saved to `products.json`

---

### Q: What format is the data?

**A:** JSON format:
```json
{
  "unique_id": "123456_789",
  "name": "Product Name",
  "prices": {
    "current_price": 150.0,
    "old_price": 200.0
  },
  "images": ["path/to/image.jpg"],
  "description": "Full description",
  "short_description": "Short desc",
  "channel_name": "Category",
  "extraction_method": "✨ Gemini AI"
}
```

---

### Q: Can I export to CSV/Excel?

**A:** Yes! Convert JSON to CSV using Python:

```python
import json
import csv

# Read JSON
with open('products.json', 'r', encoding='utf-8') as f:
    products = json.load(f)

# Write CSV
with open('products.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['name', 'current_price', 'channel_name'])
    writer.writeheader()
    for p in products:
        writer.writerow({
            'name': p['name'],
            'current_price': p['prices']['current_price'],
            'channel_name': p['channel_name']
        })
```

Or use online converters like https://www.convertcsv.com/json-to-csv.htm

---

### Q: How are prices extracted?

**A:** Two methods:

**1. With Gemini (AI):**
- Understands context
- Handles complex formats
- More accurate

**2. Without Gemini (Regex):**
- Pattern matching: "السعر 150 جنيه"
- Detects multiple prices (old vs new)
- Works for simple formats

---

### Q: What if a product has multiple prices?

**A:** The scraper:
- Takes the **lowest** as `current_price`
- Takes the **highest** as `old_price` (if multiple found)

Example: "السعر 150 بدل 200" → current: 150, old: 200

---

## 🖼️ Media & Images

### Q: What media formats are supported?

**A:**
- ✅ Images: JPG, PNG, GIF, WEBP
- ❌ Videos: Skipped (not sent to backend)
- ❌ Audio: Not supported

---

### Q: Where are images saved?

**A:** `downloaded_images/` folder

Format: `product_{chat_id}_{message_id}_{index}.{ext}`

Example: `product_123456_789_0.jpg`

---

### Q: How to avoid re-downloading images?

**A:** The scraper automatically:
- Checks if file exists before downloading
- Skips if already present
- Only downloads new images

---

### Q: Images are too large, how to compress?

**A:** Add compression after download. Example using PIL:

```python
from PIL import Image

def compress_image(path):
    img = Image.open(path)
    img.save(path, optimize=True, quality=85)
```

Or use external tools like `imagemagick`.

---

## 🔒 Security & Privacy

### Q: Is my data secure?

**A:**
- ✅ API keys stored in `.env` (not committed to git)
- ✅ Session files are local
- ✅ No data sent to third parties (except your backend)
- ⚠️ Gemini API: Sends text for processing (check Google's privacy policy)

**Best practices:**
- Don't share `.env` file
- Keep `scraper_session.session` private
- Use environment variables in production

---

### Q: Can others see what I'm scraping?

**A:** No, unless:
- You share your session file
- Someone has access to your computer
- You commit sensitive files to public repos

Always add `.env` and `*.session` to `.gitignore`!

---

### Q: Is scraping Telegram channels legal?

**A:**
- ✅ Scraping **public** channels: Generally allowed
- ❌ Scraping **private** channels: Check terms
- ⚠️ Check Telegram's Terms of Service
- ⚠️ Respect rate limits
- ⚠️ Use responsibly

**Disclaimer**: This tool is for educational purposes. Users are responsible for compliance with local laws.

---

## ⚡ Performance

### Q: How fast is the scraper?

**A:** Depends on:
- Telegram rate limits (FloodWait)
- Network speed
- Number of messages
- Gemini API response time

Typical: **50-100 messages per minute** (with rate limits)

---

### Q: Can I speed it up?

**A:** Limited by Telegram's rate limits, but you can:
- ✅ Increase `BATCH_SIZE` (careful with FloodWait)
- ✅ Disable Gemini for faster processing
- ✅ Use faster internet connection
- ❌ Can't bypass Telegram rate limits

---

### Q: How much storage do I need?

**A:** Rough estimate:
- **Images**: ~100KB per image
- **1000 products**: ~100MB
- **10,000 products**: ~1GB

Plus JSON files (minimal: few MB).

---

## 🔄 Updates & Maintenance

### Q: How do I update to latest version?

**A:**
```bash
# Backup your .env
cp .env .env.backup

# Pull latest changes
git pull

# Update dependencies
pip install -r requirements.txt

# Check CHANGELOG.md for breaking changes
```

---

### Q: How do I know if there's a new version?

**A:**
- ⭐ Star the repo on GitHub for notifications
- 📧 Watch releases
- 🔔 Check CHANGELOG.md

---

### Q: Will my .env be overwritten on update?

**A:** No! `.env` is in `.gitignore` and won't be touched by `git pull`.

---

## 🆘 Getting Help

### Q: Where can I get help?

**A:** Multiple options:

1. **Documentation**: Check README.md, FAQ.md
2. **Issues**: Search existing issues on GitHub
3. **New Issue**: Open issue with `question` label
4. **Logs**: Check error messages for clues

---

### Q: How to report a bug?

**A:**
1. Check if already reported
2. Create new issue with:
    - Clear title
    - Steps to reproduce
    - Expected vs actual behavior
    - Environment (OS, Python version)
    - Logs/error messages (without sensitive data!)

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

### Q: Can I request features?

**A:** Yes! Open an issue with:
- Clear description
- Use case (why it's needed)
- Proposed solution (if any)

Label it as `enhancement`.

---

## 💡 Tips & Tricks

### Q: Best practices for first-time use?

**A:**
1. **Start small**: Test with `STOP_DATE` set to recent date
2. **Test Gemini**: Run `test_gemini.py` first
3. **Use hybrid mode**: Best for most cases
4. **Monitor logs**: Watch for errors
5. **Check output**: Verify data quality

---

### Q: How to scrape only new products?

**A:** Use **live mode**:
```env
SCRAPER_MODE=live
```

This monitors channels for new messages only.

---

### Q: How to re-scrape a channel?

**A:**
1. Remove `STOP_DATE` from `.env` (or set to older date)
2. Clear message cache (optional)
3. Run in history mode

Note: Duplicate detection prevents re-sending same products.

---

### Q: Can I run this on a server 24/7?

**A:** Yes! Recommended for live mode:

**Using screen (Linux):**
```bash
screen -S scraper
python scraper.py
# Press Ctrl+A, then D to detach
```

**Using systemd service:**
```bash
# Create service file
sudo nano /etc/systemd/system/scraper.service

# Enable and start
sudo systemctl enable scraper
sudo systemctl start scraper
```

**Using Docker** (v2.1+ planned feature).

---

### Q: How to scrape in the background?

**A:**
```bash
# Unix/Linux/Mac
nohup python scraper.py > scraper.log 2>&1 &

# Check if running
ps aux | grep scraper.py

# View logs
tail -f scraper.log
```

---

## 🎯 Advanced

### Q: Can I modify extraction logic?

**A:** Yes! The code is modular:

```python
# Add custom pattern to PriceExtractor
class PriceExtractor:
    PRICE_PATTERNS = [
        r'your_custom_pattern',  # Add here
        # existing patterns...
    ]
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

### Q: How to add support for new languages?

**A:**
1. Update price patterns in `PriceExtractor`
2. Update Gemini prompt for your language
3. Test with sample data

Example for English:
```python
PRICE_PATTERNS = [
    r'(\d+(?:\.\d+)?)\s*(?:USD|dollars)',  # English
    r'(\d+(?:\.\d+)?)\s*(?:جنيه|ج)',       # Arabic
]
```

---

### Q: Can I use a different AI instead of Gemini?

**A:** Yes! Create a new extractor class:

```python
class CustomAIExtractor:
    async def extract(self, text: str) -> Optional[Dict]:
        # Your AI logic here
        pass
```

Then replace `GeminiExtractor` in `TelegramProductScraper.__init__`.

---

### Q: How to integrate with my own database?

**A:** Replace `BackendClient` with your DB logic:

```python
class DatabaseClient:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def save_product(self, product: ProductData):
        # Your database logic
        pass
```

---

## 📈 Scaling

### Q: Can this handle thousands of products?

**A:** Yes, but consider:
- Storage for images
- Rate limits (FloodWait)
- Processing time
- Backend capacity

For large scale:
- Use database instead of JSON
- Implement queuing system
- Run on dedicated server
- Monitor resource usage

---

### Q: How to process channels in parallel?

**A:** Currently sequential. For parallel:

```python
import asyncio

async def scrape_all_channels():
    tasks = [
        scraper.scrape_channel_history(ch) 
        for ch in CHANNELS
    ]
    await asyncio.gather(*tasks)
```

⚠️ Careful with rate limits!

---

## 🎓 Learning Resources

### Q: I want to understand the code better

**A:**
1. Read [Architecture section](README.md#architecture) in README
2. Check inline comments in code
3. Review [CONTRIBUTING.md](CONTRIBUTING.md)
4. Study `test_gemini.py` for API examples

**Python concepts used:**
- Async/await
- Type hints
- Dataclasses
- Context managers
- Error handling

---

### Q: Recommended resources to learn Python async?

**A:**
- [Python asyncio docs](https://docs.python.org/3/library/asyncio.html)
- [Real Python: Async IO](https://realpython.com/async-io-python/)
- Study Telethon examples

---

## Still have questions?

**📧 Open an issue**: [GitHub Issues](https://github.com/YOUR_REPO/issues)

**💬 Discussion**: [GitHub Discussions](https://github.com/YOUR_REPO/discussions)

---

**Last updated**: 2025-10-25
