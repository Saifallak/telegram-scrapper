# Contributing to Telegram Product Scraper

Thank you for your interest in contributing! 🎉

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)

---

## 📜 Code of Conduct

### Our Standards

- Be respectful and inclusive
- Accept constructive criticism gracefully
- Focus on what's best for the community
- Show empathy towards others

---

## 🤝 How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues. When creating a bug report, include:

- **Clear title**: Descriptive and specific
- **Description**: Detailed description of the issue
- **Steps to reproduce**: Step-by-step instructions
- **Expected behavior**: What you expected to happen
- **Actual behavior**: What actually happened
- **Environment**: OS, Python version, etc.
- **Logs**: Relevant error messages or logs

**Example:**
```markdown
### Bug: Gemini API returns 404

**Environment:**
- OS: Ubuntu 22.04
- Python: 3.10.5
- Version: 2.0.0

**Steps:**
1. Set GEMINI_API_KEY in .env
2. Run `python test_gemini.py`
3. See error

**Expected:** List of available models
**Actual:** 404 Not Found error

**Logs:**
```
❌ API Error 404: Not found
```
```

### Suggesting Features

Feature suggestions are welcome! Please include:

- **Clear title**: What feature you want
- **Use case**: Why it's needed
- **Proposed solution**: How it could work
- **Alternatives**: Other approaches considered

**Example:**
```markdown
### Feature: Support for video descriptions

**Use Case:**
Many products are posted with video descriptions only.

**Proposed Solution:**
- Use speech-to-text API to extract audio
- Parse text for product info

**Alternatives:**
- Manual video processing
- OCR on video frames
```

### Improving Documentation

Documentation improvements are always welcome:

- Fix typos or grammatical errors
- Clarify confusing sections
- Add examples
- Improve formatting
- Translate to other languages

---

## 💻 Development Setup

### 1. Fork & Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/telegram-scraper.git
cd telegram-scraper
```

### 2. Create Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 3. Setup Environment

```bash
# Run setup script
./setup.sh  # or setup.bat on Windows

# Install dev dependencies
pip install -r requirements-dev.txt  # If exists
```

### 4. Make Changes

Follow the [Coding Standards](#coding-standards) below.

### 5. Test Changes

```bash
# Run tests (if available)
python -m pytest

# Test manually
python scraper.py

# Test Gemini
python test_gemini.py
```

### 6. Commit Changes

Follow the [Commit Guidelines](#commit-guidelines) below.

### 7. Push & PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

---

## 🎨 Coding Standards

### Python Style

We follow **PEP 8** with some modifications:

```python
# ✅ Good
class ProductExtractor:
    """Extract product information from text"""
    
    def extract(self, text: str) -> ProductData:
        """
        Extract product data from message text
        
        Args:
            text: Message text to parse
            
        Returns:
            ProductData object with extracted information
        """
        # Implementation
        pass


# ❌ Bad
class productExtractor:
    def extract(self,text):
        pass  # No docstring, no type hints
```

### Type Hints

Always use type hints:

```python
# ✅ Good
def process_message(
    self,
    message: Message,
    channel_name: str
) -> Optional[ProductData]:
    pass


# ❌ Bad
def process_message(self, message, channel_name):
    pass
```

### Docstrings

All classes and public methods must have docstrings:

```python
# ✅ Good
def download_media(self, message: Message) -> Optional[str]:
    """
    Download media from Telegram message
    
    Args:
        message: Telegram message object
        
    Returns:
        Path to downloaded file, or None if failed
        
    Raises:
        FloodWaitError: If rate limited by Telegram
    """
    pass


# ❌ Bad
def download_media(self, message):
    pass  # No documentation
```

### Error Handling

Always use specific exceptions:

```python
# ✅ Good
try:
    price = float(text)
except (ValueError, TypeError) as e:
    Logger.error(f"Invalid price: {e}")
    return None


# ❌ Bad
try:
    price = float(text)
except:  # Too broad
    return None
```

### Logging

Use the Logger class:

```python
# ✅ Good
Logger.info("Processing message")
Logger.success("Download complete")
Logger.warning("No price found")
Logger.error("Failed to connect")


# ❌ Bad
print("Processing message")
print("ERROR: Failed")  # Unclear
```

### Constants

Use UPPER_CASE for constants:

```python
# ✅ Good
MAX_RETRIES = 3
DEFAULT_BATCH_SIZE = 100
SUPPORTED_FORMATS = ['jpg', 'png', 'gif']


# ❌ Bad
max_retries = 3
defaultBatchSize = 100
```

### Class Organization

Organize class methods logically:

```python
class MyClass:
    """Class docstring"""
    
    # 1. Class variables
    CONSTANT = "value"
    
    # 2. __init__
    def __init__(self):
        pass
    
    # 3. Public methods
    def public_method(self):
        pass
    
    # 4. Private methods (start with _)
    def _private_method(self):
        pass
    
    # 5. Static methods
    @staticmethod
    def utility_method():
        pass
    
    # 6. Class methods
    @classmethod
    def from_config(cls, config):
        pass
```

---

## 📝 Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation only
- **style**: Code style (formatting, no logic change)
- **refactor**: Code refactoring
- **test**: Adding tests
- **chore**: Maintenance tasks

### Examples

```bash
# Feature
git commit -m "feat(gemini): add model validation on startup"

# Bug fix
git commit -m "fix(price): handle comma decimal separator"

# Documentation
git commit -m "docs(readme): add troubleshooting section"

# Refactor
git commit -m "refactor(extractor): extract price logic to separate class"

# With body
git commit -m "feat(media): add video download support

- Support MP4 format
- Add mime type detection
- Update media handler tests

Closes #123"
```

### Commit Best Practices

- **Small commits**: One logical change per commit
- **Descriptive**: Clear what changed and why
- **Present tense**: "Add feature" not "Added feature"
- **No WIP**: Don't commit work in progress
- **Test**: Ensure code works before committing

---

## 🔄 Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] Tests pass (if applicable)
- [ ] No merge conflicts

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
How was this tested?

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or documented)

## Screenshots (if applicable)

## Related Issues
Closes #123
```

### Review Process

1. **Submit PR**: Create pull request with clear description
2. **CI Checks**: Automated checks must pass
3. **Code Review**: Maintainer reviews code
4. **Address Feedback**: Make requested changes
5. **Approval**: PR is approved
6. **Merge**: Maintainer merges PR

### After Merge

- Delete your branch
- Pull latest changes
- Update your fork

---

## 🏗️ Project Structure

Understanding the project structure helps with contributions:

```
scraper.py
├── Configuration (Config class)
├── Data Models (ProductData, ProductPrice)
├── Extractors (Gemini, Text, Price)
├── Handlers (Media, Backend)
├── Utilities (Logger, FileManager)
└── Main Scraper (TelegramProductScraper)
```

### Adding New Features

#### New Extractor

```python
class CustomExtractor:
    """Your extractor description"""
    
    @staticmethod
    def extract(text: str) -> CustomData:
        """Extract custom data"""
        # Implementation
        pass
```

#### New Handler

```python
class CustomHandler:
    """Your handler description"""
    
    def __init__(self, config: Config):
        self.config = config
    
    async def handle(self, data: any) -> bool:
        """Handle data"""
        # Implementation
        pass
```

---

## 🧪 Testing

### Manual Testing

```bash
# Test with small dataset
BATCH_SIZE=10 python scraper.py

# Test Gemini
python test_gemini.py

# Test specific mode
SCRAPER_MODE=history python scraper.py
```

### Adding Tests

```python
# tests/test_extractor.py
import pytest
from scraper import PriceExtractor

def test_price_extraction():
    """Test basic price extraction"""
    text = "السعر 150 جنيه"
    result = PriceExtractor.extract(text)
    
    assert result.current_price == 150
    assert result.old_price is None

def test_multiple_prices():
    """Test extraction with old price"""
    text = "السعر 150 جنيه بدل 200 جنيه"
    result = PriceExtractor.extract(text)
    
    assert result.current_price == 150
    assert result.old_price == 200
```

---

## 📞 Getting Help

- **Questions**: Open an issue with `question` label
- **Discussion**: Use GitHub Discussions
- **Email**: [maintainer email]

---

## 🙏 Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in relevant documentation

---

**Thank you for contributing! 🎉**
