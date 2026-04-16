from rest_framework.generics import ListAPIView
from .models import Category
from .serializers import CategoryListSerializer,CategoryWriteSerializer
from drf_spectacular.utils import extend_schema
from rest_framework.viewsets import ModelViewSet


#-------------------------------
# Customer only view for category
#-------------------------------
@extend_schema(tags=["Category"])
class CategoryListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = CategoryListSerializer
    
    def get_queryset(self):
        # ⚡ FIX: Added .order_by('id')
        return Category.objects.all().order_by('public_id')


#-------------------------------
# Waiter only view for category
#-------------------------------
@extend_schema(tags=["Category"])
class WaiterCategoryListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = CategoryListSerializer
    
    def get_queryset(self):
        # ⚡ FIX: Added .order_by('id')
        return Category.objects.all().order_by('public_id')


#-------------------------------
# Admin only view for category
#-------------------------------
@extend_schema(tags=["AdminCategory Management"])
class AdminCategoryViewSet(ModelViewSet):
    authentication_classes = [] 
    permission_classes = []
    # ⚡ FIX: Added .order_by('id') to the class-level queryset
    queryset = Category.objects.all().order_by('public_id')
    lookup_field = "public_id"


    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CategoryWriteSerializer
        return CategoryListSerializer