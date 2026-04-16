import os
import sys
import smtplib
from email.mime.text import MIMEText
from openai import OpenAI
from dotenv import load_dotenv

# 尝试加载当前目录下的 .env
load_dotenv()

def test_openrouter():
    print("\n--- Testing OpenRouter API ---")
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")

    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in environment.")
        return False

    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 8 else ''}")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'Connection Successful'"}],
            max_tokens=10
        )
        result = response.choices[0].message.content.strip()
        print(f"✅ OpenAI Response: {result}")
        return True
    except Exception as e:
        print(f"❌ OpenAI Error: {str(e)}")
        return False

def test_smtp():
    print("\n--- Testing SMTP Configuration ---")
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT", 587)
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    to_email = os.getenv("NOTIFICATION_TO")

    if not all([host, user, password]):
        print("⚠️  SMTP credentials incomplete. Skipping full test.")
        print(f"Host: {host}, User: {user}, Password: {'set' if password else 'not set'}")
        return False

    print(f"Host: {host}:{port}")
    print(f"User: {user}")
    
    try:
        # 尝试连接
        server = smtplib.SMTP(host, int(port), timeout=10)
        server.starttls()
        server.login(user, password)
        print("✅ SMTP Login Successful")
        
        if to_email:
            print(f"Sending test email to {to_email}...")
            msg = MIMEText("This is a test email from your tech-news-daily environment check.")
            msg['Subject'] = 'API Key Test'
            msg['From'] = user
            msg['To'] = to_email
            server.send_message(msg)
            print("✅ Test Email Sent")
        
        server.quit()
        return True
    except Exception as e:
        print(f"❌ SMTP Error: {str(e)}")
        return False

def test_firefly():
    print("\n--- Testing Firefly API (Optional) ---")
    api_key = os.getenv("FIREFLY_API_KEY")
    if not api_key:
        print("ℹ️  FIREFLY_API_KEY not set. (Optional feature)")
        return True
    
    print(f"API Key: {api_key[:8]}...")
    # 这里只检查 key 是否存在，因为 Firefly 通常是简单的 POST 请求
    print("✅ Firefly API Key found.")
    return True

def main():
    print("🚀 Starting Environment API Key Test...")
    
    results = {
        "OpenRouter": test_openrouter(),
        "SMTP": test_smtp(),
        "Firefly": test_firefly()
    }
    
    print("\n" + "="*30)
    print("Summary:")
    for service, status in results.items():
        icon = "✅" if status else "❌"
        print(f"{icon} {service}")
    print("="*30)

if __name__ == "__main__":
    main()
