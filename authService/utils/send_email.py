from django.core.mail import send_mail

def send_email_background(subject, message, from_email, recipient_list):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
    except Exception as e:
        # Since this runs in a thread, we can't return an HTTP 500 error to the user anymore.
        # You should log this error so you know if your SMTP server fails.
        print(f"Background email failed: {e}") 
        # logger.error(f"Background email failed: {e}")