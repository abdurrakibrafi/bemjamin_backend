from django.contrib import admin
from .models import AdminNotification, SiteContent

@admin.register(AdminNotification)
class AdminNotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_type', 'title', 'message', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    readonly_fields = ('notification_type', 'title', 'message', 'created_at')

@admin.register(SiteContent)
class SiteContentAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'updated_at')
    prepopulated_fields = {'slug': ('title',)}

    list_display_links = ('title',)