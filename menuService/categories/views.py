from rest_framework.generics import ListAPIView
from .models import Category
from .serializers import CategoryListSerializer,CategoryWriteSerializer
from drf_spectacular.utils import extend_schema
from rest_framework.viewsets import ModelViewSet


#-------------------------------
# Coustamer only view for catogery
#-------------------------------
@extend_schema(tags=["Category"])
class CategoryListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = CategoryListSerializer
    
    def get_queryset(self):
        return (
            Category.objects.all()
        )


#-------------------------------
# Coustamer only view for catogery
#-------------------------------

@extend_schema(tags=["Category"])
class WaiterCategoryListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = CategoryListSerializer
    
    def get_queryset(self):
        return (
            Category.objects.all()
        )

#-------------------------------
# admin only view for catogery
#-------------------------------

@extend_schema(tags=["AdminCategory Management"])
class AdminCategoryViewSet(ModelViewSet):
    authentication_classes = [] 
    permission_classes = []
    queryset = Category.objects.all()
    lookup_field = "public_id"


    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CategoryWriteSerializer
        return CategoryListSerializer

    