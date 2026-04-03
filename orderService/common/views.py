from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from common.services.tenant import provision_tenant, deprovision_tenant

class TenantProvisionView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        tenant_id = request.data.get("tenant_id")

        if not tenant_id:
            return Response(
                {"error": "tenant_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            provision_tenant(tenant_id)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"status": "menu tenant provisioned"},
            status=status.HTTP_201_CREATED
        )


    def delete(self, request):
     
        tenant_id = request.data.get("tenant_id")

        if not tenant_id:
            return Response(
                {"error": "tenant_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            deprovision_tenant(tenant_id)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"status": "tenant deprovisioned successfully"},
            status=status.HTTP_200_OK
        )