def get_tenant_context(request):
    restaurant_id = request.headers.get("X-Restaurant-Id")
    user_id = request.headers.get("X-User-Id")

    if not restaurant_id or not user_id:
        raise ValueError("Missing tenant context")

    return restaurant_id, user_id