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
        msg['Subject'] = "docucr Password Reset OTP"
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

def send_external_share_email(to_email, shared_by, documents):
    """
    documents: List[Dict] with keys: filename, token, expires_at
    """
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')
    sender_email = os.getenv('SENDER_EMAIL', smtp_username)
    site_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')

    if not smtp_username or not smtp_password:
        print("SMTP credentials not found. Skipping external share email send.")
        for doc in documents:
            print(f"DEBUG: Link for {to_email} ({doc['filename']}): {site_url}/public/share/{doc['token']}")
        return False

    try:
        # Load template
        template_path = os.path.join(os.path.dirname(__file__), '../templates/email/external_share.html')
        with open(template_path, 'r') as f:
            html_content = f.read()
        
        documents_html = ""
        for doc in documents:
            share_link = f"{site_url}/public/share/{doc['token']}"
            documents_html += f"""
            <div class="info-box">
                <div style="margin-bottom: 5px;">
                    <strong>Document:</strong> {doc['filename']}<br>
                    <strong>Expires:</strong> {doc['expires_at']}
                </div>
                <a href="{share_link}" class="button">View Document</a>
            </div>
            """

        html_content = html_content.replace('{{ shared_by }}', shared_by)
        html_content = html_content.replace('{{ site_url }}', site_url)
        html_content = html_content.replace('{{ documents_html }}', documents_html)

        msg = MIMEMultipart('alternative')
        subject = f"Documents Shared with you" if len(documents) > 1 else f"Document Shared with you: {documents[0]['filename']}"
        msg['Subject'] = subject
        msg['From'] = f"docucr <{sender_email}>"
        msg['To'] = to_email

        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Failed to send external share email: {e}")
        return False
