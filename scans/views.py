from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db import transaction # Import transaction
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend
from .models import Scan
from .serializers import ScanCreateSerializer, ScanDetailSerializer
from .tasks import process_scan_and_save 
from .pagination import ScanListPagination
from .filters import ScanDateFilter
from dashboard.pagination import CustomDashboardPagination
from .pdf_generator import generate_scan_pdf 
import time


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

    def retrieve(self, request, *args, **kwargs):
        scan = self.get_object()
        
        max_wait = 30
        waited = 0
        
        while scan.status == Scan.Status.PROCESSING and waited < max_wait:
            time.sleep(1)
            scan.refresh_from_db()
            waited += 1
        
        serializer = self.get_serializer(scan)
        return Response(serializer.data)
    @transaction.atomic # BEST PRACTICE FIX: Ensure Scan creation is atomic before task is deferred
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        scan = serializer.instance
        
        # Defer task until after the transaction is committed
        transaction.on_commit(lambda: process_scan_and_save.delay(str(scan.id)))
        
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