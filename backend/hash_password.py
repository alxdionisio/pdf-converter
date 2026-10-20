"""Generate an AUTH_USERS entry.

Usage: python hash_password.py [login]
Prints "login:salt:hash" to paste into AUTH_USERS (comma-separated for several accounts).
"""
import getpass
import hashlib
import os
import sys


def scrypt_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


if __name__ == "__main__":
    login = (sys.argv[1] if len(sys.argv) > 1 else input("Login: ")).strip()
    if not login or ":" in login or "," in login:
        sys.exit("Login must be non-empty and contain neither ':' nor ','")
    password = getpass.getpass("Password: ")
    if not password or password != getpass.getpass("Confirm: "):
        sys.exit("Passwords are empty or do not match")
    salt = os.urandom(16)
    print(f"{login}:{salt.hex()}:{scrypt_hash(password, salt).hex()}")
