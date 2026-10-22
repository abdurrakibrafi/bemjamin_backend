from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db import transaction # Import transaction
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend
from .models import Scan
from .serializers import ScanCreateSerializer, ScanDetailSerializer
from .tasks import process_scan_and_save, send_quota_exceeded_admin_email 
from .pagination import ScanListPagination
from .filters import ScanDateFilter
from dashboard.pagination import CustomDashboardPagination
from .pdf_generator import generate_scan_pdf 

class ScanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomDashboardPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ScanDateFilter

    def get_queryset(self):
        return Scan.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return ScanCreateSerializer
        return ScanDetailSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @transaction.atomic # BEST PRACTICE FIX: Ensure Scan creation is atomic before task is deferred
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        scan = serializer.instance
        from .models import KeenToolsQuota
        quota = KeenToolsQuota.get_singleton()

        if quota.is_quota_available():
            KeenToolsQuota.increment_used()
            # Defer task until after the transaction is committed
            transaction.on_commit(lambda: process_scan_and_save.delay(str(scan.id)))
        else:
            scan.status = Scan.Status.PENDING_APPROVAL
            scan.failure_reason = f"KeenTools maximum scan limit ({quota.max_scans}) reached. Awaiting admin approval or quota reset."
            scan.save(update_fields=['status', 'failure_reason'])

            from dashboard.models import AdminNotification
            AdminNotification.objects.create(
                notification_type=AdminNotification.NotificationType.NEW_SCAN,
                title="KeenTools Quota Reached",
                message=f"Scan '{scan.name}' from user {scan.user.email} was placed on hold because KeenTools limit ({quota.used_scans}/{quota.max_scans}) is reached."
            )

            transaction.on_commit(lambda: send_quota_exceeded_admin_email.delay(str(scan.id)))
        
        # NOTE: The response structure is preserved as requested
        detail_serializer = ScanDetailSerializer(scan, context={'request': request})
        
        response_data = {
            "scan_id": detail_serializer.data.get('scan_id'),
            "status": detail_serializer.data.get('status'),
            "scan_images": detail_serializer.data.get('scan_images'), 
        }

        headers = self.get_success_headers(detail_serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        scan = self.get_object()
        pdf_buffer = generate_scan_pdf(scan)
        response = FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=f'scan_report_{scan.id}.pdf',
            content_type='application/pdf'
        )
        return response

    @action(detail=True, methods=['get'], url_path='view-pdf')
    def view_pdf(self, request, pk=None):
        scan = self.get_object()
        pdf_buffer = generate_scan_pdf(scan)
        response = FileResponse(
            pdf_buffer,
            as_attachment=False,
            filename=f'scan_report_{scan.id}.pdf',
            content_type='application/pdf'
        )
        return response

    @action(detail=True, methods=['post'], url_path='recalculate')
    def recalculate(self, request, pk=None):
        scan = self.get_object()
        if not scan.processed_3d_model:
            return Response({'error': 'No 3D model available for this scan.'}, status=status.HTTP_400_BAD_REQUEST)

        from scans.management.commands.recalculate_measurements import load_mesh_from_scan
        from scans.mesh_measurements import perform_all_measurements
        import math
        import os
        import tempfile
        from decimal import Decimal

        mesh = load_mesh_from_scan(scan)
        if mesh is None:
            return Response({'error': 'Failed to load 3D model.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        front_img_path = None
        temp_img_path = None
        if scan.image_front:
            try:
                if hasattr(scan.image_front, 'path') and os.path.exists(scan.image_front.path):
                    front_img_path = scan.image_front.path
                else:
                    temp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    scan.image_front.seek(0)
                    temp_f.write(scan.image_front.read())
                    temp_f.close()
                    temp_img_path = temp_f.name
                    front_img_path = temp_img_path
            except Exception:
                pass

        try:
            cal_val = float(scan.calibration_value) if scan.calibration_value else None
            new_measurements = perform_all_measurements(
                mesh,
                front_image_path=front_img_path,
                calibration_type=scan.calibration_type,
                calibration_value=cal_val
            )
            if not new_measurements:
                return Response({'error': 'Measurement computation produced empty results.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            fields_to_update = []
            for key, val in new_measurements.items():
                if hasattr(scan, key) and val is not None:
                    try:
                        fval = float(val)
                        if math.isfinite(fval) and fval > 0:
                            setattr(scan, key, Decimal(f"{fval:.2f}"))
                            fields_to_update.append(key)
                    except Exception:
                        continue

            if fields_to_update:
                scan.save(update_fields=fields_to_update)

            serializer = ScanDetailSerializer(scan, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Failed to recalculate: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if temp_img_path and os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except Exception:
                    pass