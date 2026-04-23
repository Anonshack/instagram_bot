"""
split_cookie.py - cookies.txt ni Railway uchun qismlarga bo'ladi

Ishlatish:
    python split_cookie.py www.instagram.com_cookies.txt
"""
import base64
import sys
import os
import math

def split_cookie(filepath: str):
    if not os.path.exists(filepath):
        print(f"❌ Fayl topilmadi: {filepath}")
        sys.exit(1)

    with open(filepath, "rb") as f:
        data = f.read()

    b64 = base64.b64encode(data).decode()
    total_chars = len(b64)

    # Railway limiti 32768, xavfsiz chegarani 20000 qilamiz
    CHUNK = 20000
    parts = [b64[i:i+CHUNK] for i in range(0, total_chars, CHUNK)]

    print(f"\n📁 Fayl: {filepath}")
    print(f"📦 Hajmi: {len(data):,} bytes")
    print(f"🔤 Base64: {total_chars:,} belgi")
    print(f"✂️  {len(parts)} ta qismga bo'lindi\n")
    print("=" * 70)
    print("Railway → Variables ga QUYIDAGILARNI qo'shing:")
    print("(Har birini alohida variable sifatida kiriting)")
    print("=" * 70)

    for i, part in enumerate(parts, 1):
        print(f"\n--- COOKIE_PART_{i} ---")
        print(part)

    print("\n" + "=" * 70)
    print(f"✅ Jami {len(parts)} ta variable: COOKIE_PART_1 ... COOKIE_PART_{len(parts)}")
    print("=" * 70)
    print("\n⚠️  IG_USERNAME va IG_PASSWORD ni Railway Variables dan O'CHIRING!")
    print("   Cookie bilan ishlanganda login kerak emas.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Ishlatish: python split_cookie.py www.instagram.com_cookies.txt")
        sys.exit(1)
    split_cookie(sys.argv[1])