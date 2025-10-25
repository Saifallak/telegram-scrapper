#!/usr/bin/env python3
"""
Test script for Gemini API
Run this to verify your API key and see available models
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
import aiohttp

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

async def list_models(api_key: str):
    """List all available Gemini models"""
    url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"

    print("🔍 Checking Gemini API...\n")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    print("✅ API Key is valid!\n")
                    print("📋 Available models that support generateContent:\n")

                    models = []
                    for model in data.get('models', []):
                        name = model.get('name', '').replace('models/', '')
                        methods = model.get('supportedGenerationMethods', [])

                        if 'generateContent' in methods:
                            models.append(name)
                            display_name = model.get('displayName', name)
                            description = model.get('description', 'No description')

                            print(f"  📦 {name}")
                            print(f"     Display: {display_name}")
                            print(f"     Description: {description[:80]}...")
                            print()

                    print(f"\n✨ Total: {len(models)} models available\n")

                    # Recommendations
                    print("💡 Recommendations:")
                    print("  • For speed: gemini-1.5-flash-latest")
                    print("  • For quality: gemini-1.5-pro-latest")
                    print("  • For balance: gemini-1.5-flash-latest (recommended)")
                    print()

                    # Current config
                    current_model = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash-latest')
                    print(f"📌 Your current .env setting: {current_model}")

                    if current_model.replace('models/', '') in models:
                        print("   ✅ This model is available!")
                    else:
                        print("   ⚠️  This model is NOT available. Update your .env")

                    return models

                elif resp.status == 400:
                    error = await resp.json()
                    print(f"❌ API Error: {error.get('error', {}).get('message', 'Unknown error')}")
                    print("\n💡 Possible issues:")
                    print("  • Invalid API key format")
                    print("  • API key doesn't have access to Gemini")

                elif resp.status == 403:
                    print("❌ Access Denied (403)")
                    print("\n💡 Possible issues:")
                    print("  • API key is invalid or expired")
                    print("  • Gemini API is not enabled for your project")
                    print("  • Go to: https://makersuite.google.com/app/apikey")

                else:
                    error_text = await resp.text()
                    print(f"❌ HTTP Error {resp.status}")
                    print(f"Response: {error_text}")

    except asyncio.TimeoutError:
        print("❌ Request timed out")
        print("💡 Check your internet connection")

    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"💡 Type: {type(e).__name__}")

    return []


async def test_extraction(api_key: str, model: str):
    """Test actual extraction with a sample"""
    print(f"\n🧪 Testing extraction with {model}...\n")

    sample_text = """
    سيت استانلس 12 قطعه
    جميع الاحجام الصغير والكبير
    السعر 175 جنيه بدل 250 جنيه
    """

    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{
                "text": f"""استخرج بيانات المنتج من النص التالي بصيغة JSON:

{sample_text}

الصيغة المطلوبة:
{{
    "name": "اسم المنتج",
    "current_price": السعر الحالي كرقم,
    "old_price": السعر القديم كرقم أو null
}}"""
            }]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    if 'candidates' in data and data['candidates']:
                        response_text = data['candidates'][0]['content']['parts'][0]['text']

                        print("✅ Extraction successful!\n")
                        print("📄 Sample text:")
                        print(sample_text)
                        print("\n🤖 Gemini response:")
                        print(response_text)
                        print()

                        return True
                    else:
                        print("⚠️  No response generated")
                        print(f"Response: {data}")
                else:
                    error_text = await resp.text()
                    print(f"❌ Extraction failed ({resp.status})")
                    print(f"Error: {error_text}")

    except Exception as e:
        print(f"❌ Test failed: {e}")

    return False


async def main():
    """Main test function"""
    print("=" * 60)
    print("🤖 Gemini API Test Script")
    print("=" * 60)
    print()

    if not GEMINI_API_KEY:
        print("❌ No GEMINI_API_KEY found in .env file")
        print()
        print("📝 Steps to get API key:")
        print("  1. Go to https://makersuite.google.com/app/apikey")
        print("  2. Click 'Create API Key'")
        print("  3. Copy the key")
        print("  4. Add to .env file:")
        print("     GEMINI_API_KEY=your_key_here")
        print()
        sys.exit(1)

    # Mask API key for display
    masked_key = GEMINI_API_KEY[:8] + "..." + GEMINI_API_KEY[-4:]
    print(f"🔑 Using API Key: {masked_key}\n")

    # List models
    models = await list_models(GEMINI_API_KEY)

    if not models:
        print("\n❌ Could not retrieve models. Check error above.")
        sys.exit(1)

    # Test extraction
    model = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash-latest').replace('models/', '')

    if model not in models:
        print(f"\n⚠️  Model '{model}' not available, using first available model")
        model = models[0]

    success = await test_extraction(GEMINI_API_KEY, model)

    if success:
        print("\n" + "=" * 60)
        print("✅ All tests passed! Your Gemini API is ready.")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("⚠️  Some tests failed. Check errors above.")
        print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
