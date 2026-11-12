from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('employer/', views.employer_dashboard, name='employer_dashboard'),
    path('employer/applications/', views.employer_applications, name='employer_applications'),
    path('employer/jobs/', views.employer_jobs, name='employer_jobs'),
    path('employer/pending/', views.pending_reviews, name='pending_reviews'),
    path('jobseeker/', views.job_seeker_dashboard, name='jobseeker_dashboard'),
    path('jobseeker/', views.job_seeker_dashboard, name='job_seeker_dashboard'),
    path('application/<int:application_id>/manage/', views.manage_application, name='manage_application'),
    path('application/<int:application_id>/review/', views.review_application, name='review_application'),
    path('application/<int:application_id>/edit/', views.edit_application, name='edit_application'),
    path('application/<int:application_id>/withdraw/', views.withdraw_application, name='withdraw_application'),
]
