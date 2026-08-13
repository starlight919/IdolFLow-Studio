#!/usr/bin/env python3
"""生成提交密码的 HMAC 哈希。

用法：
    python3 scripts/gen_password.py <你的密码>

输出：
    VIDEO_SUBMIT_SECRET=<随机盐>
    VIDEO_SUBMIT_HASH=<HMAC-SHA256>

将这两行追加到 .env 文件即可。SECRET 是盐，HASH 是密码+盐的 HMAC。
即使 .env 泄露，也无法从 HASH 反推出原始密码。
"""
import hashlib
import hmac
import os
import sys


def main():
    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <密码>")
        sys.exit(1)
    password = sys.argv[1]
    secret = os.urandom(32).hex()
    hash_value = hmac.new(secret.encode(), password.encode(), hashlib.sha256).hexdigest()
    print("将以下两行添加到 .env 文件：\n")
    print(f"VIDEO_SUBMIT_SECRET={secret}")
    print(f"VIDEO_SUBMIT_HASH={hash_value}")


if __name__ == "__main__":
    main()
