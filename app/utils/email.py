import secrets
import string
from datetime import datetime, timedelta
from .timezone import now_kampala, kampala_to_utc
from typing import Optional
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from ..config.settings import settings
from ..config.database import get_database
from bson import ObjectId


# Email configuration
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_TLS,
    MAIL_SSL_TLS=settings.MAIL_SSL,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=True
)

# Initialize FastMail
fastmail = FastMail(conf)


def generate_reset_token() -> str:
    """Generate a secure random token for password reset"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(32))


async def store_reset_token(user_id: str, token: str, expires_in_minutes: int = 30) -> bool:
    """Store password reset token in database"""
    try:
        db = await get_database()
        
        # Calculate expiration time in Kampala timezone, then convert to UTC for storage
        kampala_now = now_kampala()
        kampala_expires = kampala_now + timedelta(minutes=expires_in_minutes)
        expires_at = kampala_to_utc(kampala_expires)
        
        # Store token in password_reset_tokens collection
        reset_data = {
            "user_id": ObjectId(user_id),
            "token": token,
            "expires_at": expires_at,
            "used": False,
            "created_at": kampala_to_utc(now_kampala())
        }
        
        # Remove any existing tokens for this user
        await db.password_reset_tokens.delete_many({"user_id": ObjectId(user_id)})
        
        # Insert new token
        await db.password_reset_tokens.insert_one(reset_data)
        
        return True
    except Exception as e:
        print(f"Error storing reset token: {e}")
        return False


async def verify_reset_token(token: str) -> Optional[str]:
    """Verify password reset token and return user_id if valid"""
    try:
        db = await get_database()
        
        # Find token in database
        token_data = await db.password_reset_tokens.find_one({
            "token": token,
            "used": False,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if token_data:
            return str(token_data["user_id"])
        
        return None
    except Exception as e:
        print(f"Error verifying reset token: {e}")
        return None


async def mark_token_as_used(token: str) -> bool:
    """Mark password reset token as used"""
    try:
        db = await get_database()
        
        result = await db.password_reset_tokens.update_one(
            {"token": token},
            {"$set": {"used": True, "used_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    except Exception as e:
        print(f"Error marking token as used: {e}")
        return False


async def send_password_reset_email(email: EmailStr, reset_token: str, user_name: str, base_url: str = None) -> bool:
    """Send password reset email"""
    try:
        # Use provided base_url or fall back to settings
        if base_url:
            # Remove trailing slash if present
            base_url = base_url.rstrip('/')
            reset_url = f"{base_url}/auth/reset-password?token={reset_token}"
        else:
            reset_url = f"{settings.BASE_URL}/auth/reset-password?token={reset_token}"
        
        # HTML email template with Tailwind-inspired inline styles
        html_content = f"""
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml" lang="en">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <title>Password Reset - {settings.MAIL_FROM_NAME}</title>
            <!--[if mso]>
            <noscript>
                <xml>
                    <o:OfficeDocumentSettings>
                        <o:PixelsPerInch>96</o:PixelsPerInch>
                    </o:OfficeDocumentSettings>
                </xml>
            </noscript>
            <![endif]-->

        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f3f4f6; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;">
            <!-- Outer table for full background -->
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f3f4f6; margin: 0; padding: 0;">
                <tr>
                    <td style="padding: 20px 0;">
                        <!-- Main container -->
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1); overflow: hidden;">

                            <!-- Header with gradient background -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%); padding: 40px 30px; text-align: center; color: #ffffff;">
                                    <!-- Logo -->
                                    <div style="margin-bottom: 20px;">
                                        <div style="width: 80px; height: 80px; background: rgba(255, 255, 255, 0.2); border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; border: 2px solid rgba(255, 255, 255, 0.3); margin: 0 auto;">
                                            <span style="font-size: 32px;">🔐</span>
                                        </div>
                                    </div>
                                    <!-- Title -->
                                    <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #ffffff; text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">Password Reset</h1>
                                    <p style="margin: 10px 0 0 0; font-size: 16px; color: rgba(255, 255, 255, 0.9);">Secure access to your account</p>
                                </td>
                            </tr>

                            <!-- Main content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <!-- Greeting -->
                                    <h2 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 600; color: #1f2937;">Hello {user_name},</h2>

                                    <!-- Message -->
                                    <p style="margin: 0 0 30px 0; font-size: 16px; line-height: 1.7; color: #4b5563;">
                                        We received a request to reset your password for your <strong style="color: #1f2937;">{settings.MAIL_FROM_NAME}</strong> Inventory Management System account.
                                    </p>

                                    <p style="margin: 0 0 30px 0; font-size: 16px; line-height: 1.7; color: #4b5563;">
                                        If you made this request, click the button below to create a new password:
                                    </p>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 40px 0;">
                                        <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%); color: #ffffff !important; padding: 16px 40px; text-decoration: none; border-radius: 50px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4); border: none; cursor: pointer;">
                                            🔑 Reset My Password
                                        </a>
                                    </div>

                                    <!-- Warning box -->
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 30px 0;">
                                        <tr>
                                            <td style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border: 1px solid #f59e0b; border-radius: 12px; padding: 20px;">
                                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                                    <tr>
                                                        <td style="width: 30px; vertical-align: top; padding-right: 12px;">
                                                            <span style="font-size: 20px;">⏰</span>
                                                        </td>
                                                        <td style="font-size: 14px; color: #92400e; font-weight: 500; line-height: 1.5;">
                                                            <strong>Security Notice:</strong> This reset link will expire in 30 minutes for your protection. If you need a new link, please request another password reset.
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- Additional message -->
                                    <p style="margin: 30px 0; font-size: 16px; line-height: 1.7; color: #4b5563;">
                                        If you didn't request this password reset, you can safely ignore this email. Your password will remain unchanged and your account stays secure.
                                    </p>

                                    <!-- URL fallback -->
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                                        <tr>
                                            <td style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
                                                <p style="margin: 0 0 10px 0; font-size: 14px; color: #64748b;">If the button above doesn't work, copy and paste this link into your browser:</p>
                                                <p style="margin: 0; font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace; font-size: 12px; color: #475569; word-break: break-all; background-color: #ffffff; padding: 12px; border-radius: 6px; border: 1px solid #e2e8f0;">{reset_url}</p>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f8fafc; padding: 30px; text-align: center; border-top: 1px solid #e2e8f0;">
                                    <p style="margin: 0 0 8px 0; font-size: 14px; font-weight: 600; color: #374151;">{settings.MAIL_FROM_NAME}</p>
                                    <p style="margin: 0 0 12px 0; font-size: 14px; color: #64748b;">Inventory Management System</p>
                                    <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.6;">
                                        This is an automated message. Please do not reply to this email.<br>
                                        If you need assistance, contact your system administrator.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
═══════════════════════════════════════════════════════════════
                    PASSWORD RESET REQUEST
                    {settings.MAIL_FROM_NAME}
                 Inventory Management System
═══════════════════════════════════════════════════════════════

Hello {user_name},

We received a request to reset your password for your {settings.MAIL_FROM_NAME}
Inventory Management System account.

🔐 RESET YOUR PASSWORD
To create a new password, please visit the following link:

{reset_url}

⏰ IMPORTANT SECURITY NOTICE
• This reset link will expire in 30 minutes for your protection
• If you need a new link, please request another password reset
• If you didn't request this reset, you can safely ignore this email

Your account remains secure and your current password is unchanged
unless you complete the reset process.

═══════════════════════════════════════════════════════════════
{settings.MAIL_FROM_NAME} - Inventory Management System

This is an automated message. Please do not reply to this email.
If you need assistance, contact your system administrator.
═══════════════════════════════════════════════════════════════
        """
        
        # Create message with proper HTML priority
        message = MessageSchema(
            subject=f"Password Reset - {settings.MAIL_FROM_NAME}",
            recipients=[email],
            body=html_content,  # Use HTML as primary body
            html=html_content,
            subtype="html",
            charset="utf-8"
        )
        
        # Send email
        await fastmail.send_message(message)
        return True
        
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False


async def send_password_changed_notification(email: EmailStr, user_name: str) -> bool:
    """Send notification email when password is successfully changed"""
    try:
        # HTML email template with improved design
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <title>Password Changed - {settings.MAIL_FROM_NAME}</title>
            <style>
                /* Reset styles */
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}

                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #374151;
                    background-color: #f9fafb;
                    margin: 0;
                    padding: 0;
                    -webkit-text-size-adjust: 100%;
                    -ms-text-size-adjust: 100%;
                }}

                table {{
                    border-collapse: collapse;
                    mso-table-lspace: 0pt;
                    mso-table-rspace: 0pt;
                }}

                /* Main container */
                .email-container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
                }}

                /* Header with success gradient */
                .header {{
                    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                    padding: 40px 30px;
                    text-align: center;
                    color: white;
                }}

                .logo-container {{
                    margin-bottom: 20px;
                }}

                .logo {{
                    width: 80px;
                    height: 80px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 50%;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    backdrop-filter: blur(10px);
                    border: 2px solid rgba(255, 255, 255, 0.3);
                }}

                .header h1 {{
                    font-size: 28px;
                    font-weight: 700;
                    margin: 0;
                    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }}

                .header p {{
                    font-size: 16px;
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                }}

                /* Content area */
                .content {{
                    padding: 40px 30px;
                }}

                .greeting {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #1f2937;
                    margin-bottom: 20px;
                }}

                .message {{
                    font-size: 16px;
                    line-height: 1.7;
                    color: #4b5563;
                    margin-bottom: 30px;
                }}

                /* Success box */
                .success-box {{
                    background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
                    border: 1px solid #10b981;
                    border-radius: 12px;
                    padding: 24px;
                    margin: 30px 0;
                    text-align: center;
                }}

                .success-icon {{
                    font-size: 48px;
                    margin-bottom: 16px;
                    display: block;
                }}

                .success-text {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #065f46;
                    margin: 0;
                }}

                /* Info box */
                .info-box {{
                    background-color: #f0f9ff;
                    border: 1px solid #0ea5e9;
                    border-radius: 12px;
                    padding: 20px;
                    margin: 30px 0;
                    display: flex;
                    align-items: flex-start;
                }}

                .info-icon {{
                    font-size: 20px;
                    margin-right: 12px;
                    margin-top: 2px;
                    color: #0ea5e9;
                }}

                .info-text {{
                    flex: 1;
                    font-size: 14px;
                    color: #0c4a6e;
                    font-weight: 500;
                }}

                .timestamp {{
                    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                    background-color: #f1f5f9;
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-size: 13px;
                    color: #475569;
                    margin-top: 8px;
                    display: inline-block;
                }}

                /* Footer */
                .footer {{
                    background-color: #f8fafc;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}

                .footer-content {{
                    font-size: 14px;
                    color: #64748b;
                    line-height: 1.6;
                }}

                .company-info {{
                    font-weight: 600;
                    color: #374151;
                    margin-bottom: 8px;
                }}

                /* Responsive */
                @media only screen and (max-width: 600px) {{
                    .email-container {{
                        margin: 10px;
                        border-radius: 12px;
                    }}

                    .header {{
                        padding: 30px 20px;
                    }}

                    .content {{
                        padding: 30px 20px;
                    }}

                    .footer {{
                        padding: 20px;
                    }}

                    .header h1 {{
                        font-size: 24px;
                    }}

                    .success-icon {{
                        font-size: 40px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div style="background-color: #f9fafb; padding: 20px 0; min-height: 100vh;">
                <div class="email-container">
                    <!-- Header -->
                    <div class="header">
                        <div class="logo-container">
                            <div class="logo">
                                <span style="font-size: 32px;">✅</span>
                            </div>
                        </div>
                        <h1>Password Changed</h1>
                        <p>Your account is now secure</p>
                    </div>

                    <!-- Content -->
                    <div class="content">
                        <div class="greeting">Hello {user_name},</div>

                        <div class="success-box">
                            <span class="success-icon">🎉</span>
                            <p class="success-text">Your password has been successfully changed!</p>
                        </div>

                        <div class="message">
                            This email confirms that your password for your <strong>{settings.MAIL_FROM_NAME}</strong> Inventory Management System account has been updated.
                        </div>

                        <div class="info-box">
                            <div class="info-icon">📅</div>
                            <div class="info-text">
                                <strong>Change completed on:</strong>
                                <div class="timestamp">{datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}</div>
                            </div>
                        </div>

                        <div class="message">
                            If you did not make this change, please contact your system administrator immediately to secure your account.
                        </div>

                        <div class="info-box" style="background-color: #fef2f2; border-color: #f87171;">
                            <div class="info-icon" style="color: #dc2626;">🛡️</div>
                            <div class="info-text" style="color: #7f1d1d;">
                                <strong>Security Tip:</strong> Keep your password safe and don't share it with anyone. Consider using a password manager for better security.
                            </div>
                        </div>
                    </div>

                    <!-- Footer -->
                    <div class="footer">
                        <div class="footer-content">
                            <div class="company-info">{settings.MAIL_FROM_NAME}</div>
                            <div>Inventory Management System</div>
                            <div style="margin-top: 12px; font-size: 13px;">
                                This is an automated security notification. Please do not reply to this email.
                                <br>
                                If you need assistance, contact your system administrator.
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
═══════════════════════════════════════════════════════════════
                    PASSWORD SUCCESSFULLY CHANGED
                    {settings.MAIL_FROM_NAME}
                 Inventory Management System
═══════════════════════════════════════════════════════════════

Hello {user_name},

🎉 SUCCESS! Your password has been successfully changed.

📅 CHANGE DETAILS
Your password for your {settings.MAIL_FROM_NAME} Inventory Management
System account has been updated on:

{datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}

🛡️ SECURITY NOTICE
If you did not make this change, please contact your system
administrator immediately to secure your account.

💡 SECURITY TIP
Keep your password safe and don't share it with anyone. Consider
using a password manager for better security.

═══════════════════════════════════════════════════════════════
{settings.MAIL_FROM_NAME} - Inventory Management System

This is an automated security notification. Please do not reply.
If you need assistance, contact your system administrator.
═══════════════════════════════════════════════════════════════
        """

        # Create message with proper HTML priority
        message = MessageSchema(
            subject=f"Password Changed - {settings.MAIL_FROM_NAME}",
            recipients=[email],
            body=html_content,  # Use HTML as primary body
            html=html_content,
            subtype="html",
            charset="utf-8"
        )
        
        # Send email
        await fastmail.send_message(message)
        return True
        
    except Exception as e:
        print(f"Error sending password changed notification: {e}")
        return False
