from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from .models import AuthToken, UserProfile, PasswordHistory
from .serializers import (
    SignupSerializer, OTPVerificationSerializer, ChangePasswordSerializer,
    ProfileSerializer, UpdateProfileSerializer,ResendVerificationSerializer, MyTokenObtainPairSerializer, LogoutSerializer,
    PasswordResetRequestSerializer, PasswordResetVerifyOTPSerializer, SetNewPasswordSerializer,DeleteAccountSerializer
)
import random
from dashboard.models import AdminNotification
from notifications.utils import create_and_send_notification

def generate_otp():
    return str(random.randint(100000, 999999))

def send_email(subject, message, recipient_list):
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipient_list, fail_silently=False)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_otp_email(user, otp, purpose="account verification"):
    subject = f'Your OTP for {purpose}'
    message = f'Hi {user.first_name},\n\nYour One-Time Password (OTP) is: {otp}\n\nIt is valid for 15 minutes.'
    return send_email(subject, message, [user.email])

class UserSignupAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            first_error = next(iter(serializer.errors.values()))[0]
            message = first_error if "This field" not in first_error else "Please fill in all required fields before signing up."
            return Response({"message": message, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = serializer.save()
            otp = generate_otp()
            AuthToken.objects.create(user=user, otp_code=otp, token_type='signup')
        
        send_otp_email(user, otp, purpose="email verification")
        return Response({"message": "User registered. An OTP has been sent to your email to verify your account."}, status=status.HTTP_201_CREATED)

class VerifySignupOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data['otp']
        
        user_to_notify = None
        should_send_email = False
        
        with transaction.atomic():
            try:
                token = AuthToken.objects.select_for_update().get(otp_code=otp, token_type='signup', is_used=False, expires_at__gt=timezone.now())
            except AuthToken.DoesNotExist:
                return Response({'error': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
            
            user = token.user
            profile = user.profile

            if profile.status == 'UNVERIFIED':
                profile.status = 'PENDING'
                profile.save()

                AdminNotification.objects.create(
                    notification_type=AdminNotification.NotificationType.NEW_USER,
                    message=f"New user '{user.get_full_name()}' has verified their email and requires approval."
                )
                user_to_notify = user
                should_send_email = True

            token.is_used = True
            token.save()

        if should_send_email and user_to_notify:
            approval_message = "Congratulations, you successfully signed up. You will receive an email notification as soon as your account is approved."
            send_email("Welcome! Your account is awaiting approval", approval_message, [user_to_notify.email])
            create_and_send_notification(
                user=user_to_notify,
                title="Account Pending Approval",
                message=approval_message
            )

        return Response({'message': 'Email verified successfully. Your account is now awaiting admin approval.'}, status=status.HTTP_200_OK)

class AcceptTermsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        profile = request.user.profile
        profile.has_accepted_terms = True
        profile.save()
        return Response({"message": "Terms and conditions accepted successfully."}, status=status.HTTP_200_OK)

class ResendSignupOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user_found = False
            otp = None
            user_obj = None

            with transaction.atomic():
                try:
                    user = User.objects.get(email__iexact=email)
                    if user.is_active:
                        return Response({'error': 'This account is already active.'}, status=status.HTTP_400_BAD_REQUEST)
                    if user.profile.status != 'UNVERIFIED':
                        return Response({'error': 'This account has already been verified and is pending approval.'}, status=status.HTTP_400_BAD_REQUEST)
                    
                    AuthToken.objects.filter(user=user, token_type='signup', is_used=False).update(is_used=True)
                    
                    otp = generate_otp()
                    AuthToken.objects.create(user=user, otp_code=otp, token_type='signup')
                    user_found = True
                    user_obj = user
                except User.DoesNotExist:
                    pass
            
            if user_found and otp:
                send_otp_email(user_obj, otp, purpose="account verification")
                return Response({'message': 'New OTP sent to your email.'}, status=status.HTTP_200_OK)
            elif not user_found and not otp:
                 return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MyTokenObtainPairView(APIView):
    permission_classes = [AllowAny]
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [AnonRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class UserLogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data["refresh"]
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logout successful.'}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'error': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)

class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        profile = request.user.profile
        serializer = ProfileSerializer(profile, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

class UpdateProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def put(self, request):
        user = request.user
        profile = user.profile
        serializer = UpdateProfileSerializer(
            instance=user,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            profile.refresh_from_db()
            create_and_send_notification(
                user=user,
                title="Profile Updated",
                message="Your profile details have been successfully updated."
            )
            return Response(ProfileSerializer(profile, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            with transaction.atomic():
                user = request.user
                new_password = serializer.validated_data['new_password']
                user.set_password(new_password)
                user.save()
                PasswordHistory.objects.create(user=user, hashed_password=user.password)
            
            create_and_send_notification(
                user=user,
                title="Security Alert: Password Changed",
                message="Your account password was successfully changed. If you did not make this change, please contact support immediately."
            )
            return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = None
            user_obj = None

            with transaction.atomic():
                try:
                    user = User.objects.get(email__iexact=email)
                    AuthToken.objects.filter(user=user, token_type='password_reset_otp').delete()
                    otp = generate_otp()
                    AuthToken.objects.create(user=user, otp_code=otp, token_type='password_reset_otp')
                    user_obj = user
                except User.DoesNotExist:
                    pass

            if user_obj and otp:
                send_otp_email(user_obj, otp, purpose="password reset")

            return Response(
                {'message': 'If an account with this email exists, an OTP has been sent.'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendPasswordResetOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = None
            user_obj = None

            with transaction.atomic():
                try:
                    user = User.objects.get(email__iexact=email)
                    AuthToken.objects.filter(user=user, token_type='password_reset_otp', is_used=False).update(is_used=True)
                    otp = generate_otp()
                    AuthToken.objects.create(user=user, otp_code=otp, token_type='password_reset_otp')
                    user_obj = user
                except User.DoesNotExist:
                    return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
            
            if user_obj and otp:
                send_otp_email(user_obj, otp, purpose="password reset")
                return Response({'message': 'New OTP for password reset has been sent to your email.'}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyPasswordResetOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = PasswordResetVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data['otp']
        
        with transaction.atomic():
            try:
                token = AuthToken.objects.select_for_update().get(
                    otp_code=otp, token_type='password_reset_otp',
                    is_used=False, expires_at__gt=timezone.now()
                )
            except AuthToken.DoesNotExist:
                return Response({'error': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
            token.is_used = True
            token.save()
            change_ticket = AuthToken.objects.create(user=token.user, token_type='password_change_ticket')
            
        return Response({
            'message': 'OTP verified successfully.',
            'password_change_ticket': change_ticket.token
        }, status=status.HTTP_200_OK)

class SetNewPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle] 

    def post(self, request):
        serializer = SetNewPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.validated_data['password_change_ticket']
        new_password = serializer.validated_data['new_password']
        
        with transaction.atomic():
            try:
                verified_token = AuthToken.objects.select_for_update().get(
                    token=ticket, token_type='password_change_ticket',
                    is_used=False, expires_at__gt=timezone.now()
                )
            except AuthToken.DoesNotExist:
                return Response({'error': 'Invalid or expired password change session. Please start over.'}, status=status.HTTP_400_BAD_REQUEST)
            user = verified_token.user
            for history in PasswordHistory.objects.filter(user=user).order_by('-created_at')[:10]:
                if check_password(new_password, history.hashed_password):
                    return Response({'error': 'Cannot reuse a recent password.'}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(new_password)
            user.save()
            PasswordHistory.objects.create(user=user, hashed_password=user.password)
            verified_token.is_used = True
            verified_token.save()

        return Response({'message': 'Your password has been reset successfully.'}, status=status.HTTP_200_OK)

class DeleteUserAccountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        serializer = DeleteAccountSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            user = request.user
            user.delete()
            
        return Response(
            {"message": "Your account has been permanently deleted."},
            status=status.HTTP_200_OK
        )