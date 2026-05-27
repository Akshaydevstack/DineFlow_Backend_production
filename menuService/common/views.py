import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from common.services.tenant import provision_tenant, deprovision_tenant

logger = logging.getLogger(__name__)

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
            # 🟢 FIX 1: This will print the exact database error to your pod logs
            logger.exception(f"🔥 Failed to provision tenant {tenant_id}: {str(e)}")
            
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            # 🟢 FIX 2: Updated the success message from "menu" to "notification"
            {"status": "notification tenant provisioned successfully"}, 
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
            logger.exception(f"🔥 Failed to deprovision tenant {tenant_id}: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {"status": "notification tenant deprovisioned successfully"},
            status=status.HTTP_200_OK
        )