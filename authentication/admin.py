from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, AuthToken, PasswordHistory

if admin.site.is_registered(User):
    admin.site.unregister(User)

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff')
    list_select_related = ('profile',)
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super().get_inline_instances(request, obj)

@admin.register(AuthToken)
class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token_type', 'short_token', 'created_at', 'expires_at', 'is_valid')
    list_filter = ('token_type', 'is_used')
    search_fields = ('user__username', 'token')
    readonly_fields = ('token', 'created_at', 'expires_at')
    
    def short_token(self, obj):
        return str(obj.token)[:8]
    short_token.short_description = 'Token'
    
    def is_valid(self, obj):
        return obj.is_valid()
    is_valid.boolean = True

@admin.register(PasswordHistory)
class PasswordHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)