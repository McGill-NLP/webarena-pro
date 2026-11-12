from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.jobs.models import Job, Application
from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Count

def home(request):
    return render(request, 'dashboard/home.html')

@login_required
def employer_dashboard(request):
    if not request.user.is_employer:
        messages.error(request, "Access denied. Employer account required.")
        return redirect('jobs:home')

    posted_jobs = Job.objects.filter(employer=request.user.employer)
    recent_applications = Application.objects.filter(
        job__employer=request.user.employer
    ).order_by('-applied_date')[:5]
    pending_count = Application.objects.filter(
        job__employer=request.user.employer,
        status='pending'
    ).count()

    context = {
        'posted_jobs': posted_jobs,
        'recent_applications': recent_applications,
        'total_jobs': posted_jobs.count(),
        'total_applications': Application.objects.filter(
            job__employer=request.user.employer
        ).count(),
        'pending_count': pending_count,
    }
    return render(request, 'dashboard/employer_dashboard.html', context)

@login_required
def employer_applications(request):
    if not request.user.is_employer:
        messages.error(request, "Access denied. Employer account required.")
        return redirect('jobs:home')

    applications = Application.objects.filter(
        job__employer=request.user.employer
    ).select_related('job', 'job_seeker__user').order_by('-applied_date')
    page_obj = Paginator(applications, 50).get_page(request.GET.get('page'))
    return render(request, 'dashboard/employer_applications.html', {
        'applications': page_obj,
        'page_obj': page_obj,
    })

@login_required
def employer_jobs(request):
    if not request.user.is_employer:
        messages.error(request, "Access denied. Employer account required.")
        return redirect('jobs:home')

    jobs = Job.objects.filter(employer=request.user.employer).annotate(
        application_count=Count('applications')
    ).order_by('-posted_date')
    page_obj = Paginator(jobs, 50).get_page(request.GET.get('page'))
    return render(request, 'dashboard/employer_jobs.html', {
        'jobs': page_obj,
        'page_obj': page_obj,
    })

@login_required
def pending_reviews(request):
    if not request.user.is_employer:
        messages.error(request, "Access denied. Employer account required.")
        return redirect('jobs:home')

    applications = Application.objects.filter(
        job__employer=request.user.employer,
        status='pending'
    ).select_related('job', 'job_seeker__user').order_by('-applied_date')
    page_obj = Paginator(applications, 30).get_page(request.GET.get('page'))
    return render(request, 'dashboard/pending_reviews.html', {
        'applications': page_obj,
        'page_obj': page_obj,
    })

@login_required
def review_application(request, application_id):
    if not request.user.is_employer:
        messages.error(request, "Access denied. Employer account required.")
        return redirect('jobs:home')

    application = get_object_or_404(
        Application,
        id=application_id,
        job__employer=request.user.employer
    )

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Application.STATUS_CHOICES):
            application.status = new_status
            application.save()
            action = 'accepted' if new_status == 'accepted' else 'rejected'
            messages.success(request, f"Application has been {action}.")
        return redirect('dashboard:pending_reviews')

    applicant_name = (
        application.job_seeker.user.get_full_name()
        or application.job_seeker.user.username
    )
    job_title = application.job.title
    company_name = request.user.employer.company_name

    acceptance_email = (
        f"Dear {applicant_name},\n\n"
        f"We are pleased to inform you that your application for the {job_title} "
        f"position at {company_name} has been accepted.\n\n"
        f"We were impressed by your profile and would like to move forward with your application. "
        f"Please reply to this email to confirm your interest and we will provide further details "
        f"about the next steps.\n\n"
        f"Best regards,\n{company_name} Hiring Team"
    )

    rejection_email = (
        f"Dear {applicant_name},\n\n"
        f"Thank you for your interest in the {job_title} position at {company_name} "
        f"and for taking the time to apply.\n\n"
        f"After careful consideration, we regret to inform you that we will not be moving "
        f"forward with your application at this time.\n\n"
        f"We appreciate your interest in our company and encourage you to apply for future "
        f"openings that match your qualifications.\n\n"
        f"Best regards,\n{company_name} Hiring Team"
    )

    return render(request, 'dashboard/review_application.html', {
        'application': application,
        'acceptance_email': acceptance_email,
        'rejection_email': rejection_email,
    })

@login_required
def job_seeker_dashboard(request):
    if not request.user.is_job_seeker:
        messages.error(request, "Access denied. Job seeker account required.")
        return redirect('jobs:home')
    
    applications = Application.objects.filter(
        job_seeker=request.user.jobseeker
    ).order_by('-applied_date')
    
    context = {
        'applications': applications,
        'total_applications': applications.count(),
        'pending_applications': applications.filter(status='pending').count(),
        'accepted_applications': applications.filter(status='accepted').count(),
    }
    return render(request, 'dashboard/job_seeker_dashboard.html', context)

@login_required
def manage_application(request, application_id):
    if not request.user.is_employer:
        messages.error(request, "Access denied.")
        return redirect('home')
    
    application = Application.objects.get(
        id=application_id,
        job__employer=request.user.employer
    )
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Application.STATUS_CHOICES):
            application.status = new_status
            application.save()
            messages.success(request, "Application status updated successfully!")
    
    return redirect('dashboard:employer_dashboard')

@login_required
def edit_application(request, application_id):
    application = get_object_or_404(Application, id=application_id, job_seeker=request.user.jobseeker)
    
    if application.status != 'pending':
        messages.error(request, "You can only edit pending applications.")
        return redirect('dashboard:jobseeker_dashboard')
    
    if request.method == 'POST':
        application.cover_letter = request.POST.get('cover_letter')
        application.save()
        messages.success(request, "Application updated successfully!")
        return redirect('dashboard:jobseeker_dashboard')
    
    return redirect('dashboard:jobseeker_dashboard')

@login_required
def withdraw_application(request, application_id):
    if request.method == 'POST':
        application = get_object_or_404(Application, id=application_id, job_seeker=request.user.jobseeker)
        
        if application.status not in ('pending', 'reviewing'):
            messages.error(request, "You can only withdraw active applications.")
            return redirect('dashboard:jobseeker_dashboard')
        
        application.delete()
        messages.success(request, "Application withdrawn successfully!")
    
    return redirect('dashboard:jobseeker_dashboard')
