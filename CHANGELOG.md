# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2025-10-25

### 🎉 Major Refactoring

Complete rewrite of the scraper with focus on code quality, maintainability, and extensibility.

### ✨ Added

#### Core Features
- **Gemini AI Integration**: Automatic product data extraction using Google Gemini API
- **Automatic Fallback**: Falls back to manual extraction if AI fails
- **Smart Validation**: Validates products before saving/sending
- **Better Logging**: Color-coded, informative logging system
- **Error Recovery**: Comprehensive error handling with retry logic

#### Code Architecture
- **Data Models**: Clean dataclasses for Product, Price, Config
- **Extractors**: Separate classes for Gemini, Text, and Price extraction
- **Handlers**: MediaHandler and BackendClient for specific responsibilities
- **Utilities**: Logger, FileManager for reusable operations

#### Developer Experience
- **Type Hints**: Full type annotations throughout
- **Docstrings**: Comprehensive documentation for all classes/methods
- **Configuration**: Centralized Config class
- **Enums**: Type-safe enums for constants

#### Tools & Scripts
- **test_gemini.py**: Test and validate Gemini API setup
- **setup.sh**: Automated setup for Linux/Mac
- **setup.bat**: Automated setup for Windows
- **.env.example**: Comprehensive configuration template

#### Documentation
- **README.md**: Complete rewrite with detailed sections
- **Architecture Diagram**: Visual representation of system design
- **Troubleshooting**: Common issues and solutions
- **Code Examples**: Usage examples for all features

### 🔧 Improved

#### Performance
- **Better Caching**: Improved message caching strategy
- **Batch Processing**: Optimized batch processing logic
- **Resource Management**: Better file handle management
- **Async Operations**: More efficient async/await usage

#### Reliability
- **FloodWait Handling**: Comprehensive FloodWait protection
- **Network Errors**: Better network error handling
- **Validation**: Product validation before processing
- **Retry Logic**: Configurable retry attempts

#### Code Quality
- **SOLID Principles**: Single Responsibility, Open/Closed, etc.
- **DRY**: No code duplication
- **Clean Code**: Readable, maintainable code
- **Separation of Concerns**: Clear boundaries between components

#### Configuration
- **Environment Variables**: All configs via .env
- **Validation**: Config validation on startup
- **Defaults**: Sensible default values
- **Flexibility**: Easy to customize behavior

### 🐛 Fixed

#### Gemini API
- **Model Name**: Fixed incorrect model name format
- **API Version**: Updated to correct API version (v1)
- **Error Messages**: Better error messages for API issues
- **Model Validation**: Validates model availability on startup

#### Price Extraction
- **Decimal Numbers**: Properly handles comma decimals (7,5 → 7.5)
- **Range Validation**: Only accepts prices in valid range (1-100000)
- **Context Aware**: Better context-aware price extraction
- **Multiple Prices**: Correctly identifies current vs old price

#### Media Handling
- **File Extensions**: Correct file extension detection
- **Duplicate Downloads**: Skips already downloaded files
- **Supported Formats**: Only downloads supported formats
- **Error Recovery**: Handles download failures gracefully

#### Message Processing
- **Media Buffering**: Fixed media buffering logic
- **Cache Management**: Better cache invalidation
- **Duplicate Prevention**: Prevents processing same message twice
- **Order Preservation**: Maintains correct message order

### 📝 Changed

#### Breaking Changes
- **File Structure**: New modular file structure
- **Class Names**: More descriptive class names
- **Configuration**: New configuration format in .env

#### Improvements
- **Print Statements**: Replaced with Logger class
- **Error Handling**: More specific exception handling
- **Variable Names**: More descriptive naming
- **Code Organization**: Better module organization

### 🗑️ Removed

- **Old Manual Logic**: Replaced with cleaner implementation
- **Duplicate Code**: Eliminated code duplication
- **Magic Numbers**: Replaced with named constants
- **Global State**: Reduced global variables

---

## [1.0.0] - 2024-XX-XX

### Initial Release

#### Features
- Basic Telegram channel scraping
- Manual price extraction
- Media download
- Backend integration
- History and live modes

---

## Migration Guide: v1.0 → v2.0

### Configuration Changes

**Old (.env):**
```env
TELEGRAM_API_ID=123
TELEGRAM_API_HASH=abc
```

**New (.env):**
```env
# More organized with comments
TELEGRAM_API_ID=123
TELEGRAM_API_HASH=abc
GEMINI_API_KEY=xyz  # New!
SCRAPER_MODE=hybrid  # New!
```

### Code Changes

**Old:**
```python
# Direct instantiation
scraper = TelegramProductScraper()
```

**New:**
```python
# With configuration
config = Config()
scraper = TelegramProductScraper(config)
```

### Running the Scraper

**Old:**
```bash
python scraper.py
# Mode hardcoded in file
```

**New:**
```bash
# Mode via environment variable
SCRAPER_MODE=history python scraper.py
# Or set in .env
python scraper.py
```

### API Changes

#### Extractors

**Old:**
```python
def extract_price(self, text: str) -> Dict
```

**New:**
```python
@classmethod
def extract(cls, text: str) -> ProductPrice
```

#### Data Models

**Old:**
```python
product = {
    'name': '...',
    'prices': {'current_price': 100}
}
```

**New:**
```python
product = ProductData(
    name='...',
    prices=ProductPrice(current_price=100)
)
```

---

## Upgrade Instructions

### Automatic Upgrade

```bash
# Backup old files
cp scraper.py scraper_old.py
cp .env .env.backup

# Pull new version
git pull

# Run setup
./setup.sh  # or setup.bat on Windows

# Migrate .env
# Compare .env.backup with .env.example
# Add any new variables
```

### Manual Upgrade

1. **Backup**: Save your current `.env` and `scraper.py`
2. **Replace**: Replace `scraper.py` with new version
3. **Update .env**: Add new variables from `.env.example`
4. **Test**: Run `python test_gemini.py`
5. **Run**: Run `python scraper.py`

---

## Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

---

## Roadmap

### v2.1.0 (Planned)
- [ ] Support for video extraction
- [ ] Parallel channel processing
- [ ] Web dashboard for monitoring
- [ ] Database support (PostgreSQL/MongoDB)
- [ ] Docker containerization

### v2.2.0 (Planned)
- [ ] Multi-language support
- [ ] Custom extraction rules
- [ ] Advanced filtering
- [ ] Scheduled scraping
- [ ] Webhook notifications

### v3.0.0 (Future)
- [ ] Machine learning for classification
- [ ] Image recognition
- [ ] Auto-translation
- [ ] Analytics dashboard
- [ ] REST API

---

## Contributing

See issues labeled `good-first-issue` or `help-wanted` on GitHub.

---

## Support

- **Bug Reports**: Open an issue with `bug` label
- **Feature Requests**: Open an issue with `enhancement` label
- **Questions**: Open an issue with `question` label

---

**Note**: This is a living document. Check back for updates!
