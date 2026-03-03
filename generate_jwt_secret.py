#!/usr/bin/env python3
import secrets

def generate_jwt_secret(length=128):
    """Generate a secure JWT secret key"""
    return secrets.token_hex(length // 2)

if __name__ == "__main__":
    secret = generate_jwt_secret()
    print(f"JWT_SECRET_KEY={secret}")