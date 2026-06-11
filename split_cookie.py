"""
split_cookie.py - Splits cookies.txt into parts for Railway deployment

Usage:
    python split_cookie.py www.instagram.com_cookies.txt
"""
import base64
import sys
import os

def split_cookie(filepath: str):
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    with open(filepath, "rb") as f:
        data = f.read()

    b64 = base64.b64encode(data).decode()
    total_chars = len(b64)

    # Railway limit is 32768; use 20000 to stay safe
    CHUNK = 20000
    parts = [b64[i:i+CHUNK] for i in range(0, total_chars, CHUNK)]

    print(f"\n📁 File: {filepath}")
    print(f"📦 Size: {len(data):,} bytes")
    print(f"🔤 Base64: {total_chars:,} characters")
    print(f"✂️  Split into {len(parts)} part(s)\n")
    print("=" * 70)
    print("Railway → Add the following to Variables:")
    print("(Enter each one as a separate variable)")
    print("=" * 70)

    for i, part in enumerate(parts, 1):
        print(f"\n--- COOKIE_PART_{i} ---")
        print(part)

    print("\n" + "=" * 70)
    print(f"✅ Total {len(parts)} variable(s): COOKIE_PART_1 ... COOKIE_PART_{len(parts)}")
    print("=" * 70)
    print("\n⚠️  Remove IG_USERNAME and IG_PASSWORD from Railway Variables!")
    print("   Login is not needed when using a cookie file.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_cookie.py www.instagram.com_cookies.txt")
        sys.exit(1)
    split_cookie(sys.argv[1])
