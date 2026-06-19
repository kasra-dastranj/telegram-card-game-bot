#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اجرای ربات تست با .env.test
"""

import os
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# تنظیم environment variable قبل از import
os.environ['ENV_FILE'] = '.env.test'

# حالا telegram_bot رو import کن
from telegram_bot import main

if __name__ == "__main__":
    print("Starting TEST bot with .env.test configuration...")
    print("=" * 60)
    main()
