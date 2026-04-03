from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings

class JWTCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 1. Try to get token from header (original way)
        header = self.get_header(request)
        
        if header is None:
            # 2. If no header, try to get token from the COOKIE
            raw_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
        else:
            raw_token = self.get_raw_token(header)

        if raw_token is None:
            return None

        # 3. Validate the token as usual
        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token