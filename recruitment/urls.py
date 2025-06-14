from django.contrib import admin
from django.urls import path
from recruitment import views
from django.conf import settings
from django.conf.urls.static import static
from recruitment.views import CustomLoginView


app_name = 'recruitment'
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.upload, name='upload'),
    path('register/', views.register, name='register'),
    path('login/', CustomLoginView.as_view(template_name='recruitment/login.html'), name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('shortlisted/', views.shortlisted_candidates, name='shortlisted_candidates'),
    path('send-email/', views.send_custom_email, name='send_custom_email'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)