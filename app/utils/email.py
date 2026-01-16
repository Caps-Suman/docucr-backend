import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_otp_email(to_email, otp_code):
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')
    sender_email = os.getenv('SENDER_EMAIL', smtp_username)

    if not smtp_username or not smtp_password:
        print("SMTP credentials not found. Skipping email send.")
        print(f"DEBUG OTP for {to_email}: {otp_code}")
        return False

    try:
        # Load template
        template_path = os.path.join(os.path.dirname(__file__), '../templates/email/otp.html')
        with open(template_path, 'r') as f:
            html_content = f.read()
        
        html_content = html_content.replace('{{ otp_code }}', otp_code)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = "DocuCR Password Reset OTP"
        msg['From'] = sender_email
        msg['To'] = to_email

        # Attach HTML content
        msg.attach(MIMEText(html_content, 'html'))

        # Send
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
