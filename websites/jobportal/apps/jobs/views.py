import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from .models import Job, Application, Category
from .forms import JobForm, JobApplicationForm, JobSearchForm
from .models import Category
from apps.accounts.models import Employer


def _parse_salary_lower_bound(salary_str):
    """Extract the first integer found in a salary string (the lower bound)."""
    digits = re.sub(r'[^\d]', '', salary_str.split('-')[0].split('/')[0])
    return int(digits) if digits else None

def companies(request):
    companies = Employer.objects.annotate(
        active_job_count=Count('jobs', filter=Q(jobs__is_active=True))
    ).order_by('company_name')
    page_obj = Paginator(companies, 24).get_page(request.GET.get('page'))
    return render(request, 'jobs/companies.html', {'companies': page_obj, 'page_obj': page_obj})
def home(request):
    featured_jobs = Job.objects.filter(is_active=True)[:6]
    categories = Category.objects.all()
    context = {
        'featured_jobs': featured_jobs,
        'categories': categories,
    }
    return render(request, 'jobs/home.html', context)

def job_list(request):
    form = JobSearchForm(request.GET)
    jobs = Job.objects.filter(is_active=True).select_related('employer').annotate(
        application_count=Count('applications')
    )

    company = request.GET.get('company')
    if company:
        jobs = jobs.filter(employer_id=company)

    if form.is_valid():
        search = form.cleaned_data.get('search')
        location = form.cleaned_data.get('location')
        category = form.cleaned_data.get('category')
        job_type = form.cleaned_data.get('job_type')

        if search:
            jobs = jobs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        if location:
            jobs = jobs.filter(location__icontains=location)
        if category:
            jobs = jobs.filter(category=category)
        if job_type:
            jobs = jobs.filter(job_type=job_type)

    experience = request.GET.get('experience')
    if experience:
        jobs = jobs.filter(experience_level=experience)

    salary_range = request.GET.get('salary')
    if salary_range:
        RANGES = {
            '0-50000':      (0,      50000),
            '50000-90000':  (50000,  90000),
            '90000-130000': (90000,  130000),
            '130000+':      (130000, None),
        }
        bounds = RANGES.get(salary_range)
        if bounds:
            lo, hi = bounds
            matched_ids = []
            for job in jobs:
                val = _parse_salary_lower_bound(job.salary)
                if val is not None:
                    if hi is None and val >= lo:
                        matched_ids.append(job.pk)
                    elif hi is not None and lo <= val < hi:
                        matched_ids.append(job.pk)
            jobs = jobs.filter(pk__in=matched_ids)

    paginator = Paginator(jobs.order_by('-posted_date', '-id'), 9)  # 9 jobs per page
    page = request.GET.get('page')
    jobs = paginator.get_page(page)

    context = {
        'jobs': jobs,
        'form': form,
    }
    return render(request, 'jobs/job_list.html', context)

def job_detail(request, job_id):
    job = get_object_or_404(Job, id=job_id, is_active=True)
    application_form = JobApplicationForm() if request.user.is_authenticated else None
    has_applied = False

    if request.user.is_authenticated and hasattr(request.user, 'jobseeker'):
        has_applied = Application.objects.filter(
            job=job, job_seeker=request.user.jobseeker
        ).exists()

    context = {
        'job': job,
        'application_form': application_form,
        'has_applied': has_applied,
    }
    return render(request, 'jobs/job_detail.html', context)

@login_required
def post_job(request):
    if not hasattr(request.user, 'employer'):
        return redirect('home')
        
    if request.method == 'POST':
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.employer = request.user.employer
            job.save()
            messages.success(request, "Job posted successfully!")
            return redirect('jobs:job_detail', job_id=job.id)
        messages.error(request, "Could not post job. Please fix the highlighted fields.")
    else:
        form = JobForm()

    return render(request, 'jobs/post_job.html', {'form': form})

@login_required
def apply_job(request, job_id):
    if not request.user.is_job_seeker:
        messages.error(request, "Only job seekers can apply for jobs.")
        return redirect('jobs:job_detail', job_id=job_id)

    job = get_object_or_404(Job, id=job_id, is_active=True)
    
    if Application.objects.filter(job=job, job_seeker=request.user.jobseeker).exists():
        messages.info(request, "You have already applied for this job.")
        return redirect('jobs:job_detail', job_id=job_id)

    if request.method == 'POST':
        form = JobApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.job = job
            application.job_seeker = request.user.jobseeker
            application.save()
            messages.success(request, "Application submitted successfully!")
            return redirect('dashboard:jobseeker_dashboard')

    return redirect('jobs:job_detail', job_id=job_id)

def search_jobs(request):
    form = JobSearchForm(request.GET)
    jobs = Job.objects.filter(is_active=True)

    if form.is_valid():
        search = form.cleaned_data.get('search')
        location = form.cleaned_data.get('location')
        category = form.cleaned_data.get('category')
        job_type = form.cleaned_data.get('job_type')

        if search:
            jobs = jobs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        if location:
            jobs = jobs.filter(location__icontains=location)
        if category:
            jobs = jobs.filter(category=category)
        if job_type:
            jobs = jobs.filter(job_type=job_type)

    paginator = Paginator(jobs.order_by('-posted_date', '-id'), 9)  # 9 jobs per page
    page = request.GET.get('page')
    jobs = paginator.get_page(page)

    context = {
        'jobs': jobs,
        'form': form,
    }
    return render(request, 'jobs/search_results.html', context)

def categories(request):
    categories = Category.objects.all()
    context = {
        'categories': categories,
    }
    return render(request, 'jobs/categories.html', context)

@login_required
def edit_job(request, job_id):
    if not hasattr(request.user, 'employer'):
        return redirect('jobs:home')

    job = get_object_or_404(Job, id=job_id, employer=request.user.employer)

    if request.method == 'POST':
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, "Job updated successfully.")
            return redirect('dashboard:employer_jobs')
        messages.error(request, "Could not update job. Please fix the highlighted fields.")
    else:
        form = JobForm(instance=job)

    return render(request, 'jobs/post_job.html', {'form': form, 'editing': True, 'job': job})

@login_required
def delete_job(request, job_id):
    if not hasattr(request.user, 'employer'):
        return redirect('jobs:home')

    job = get_object_or_404(Job, id=job_id, employer=request.user.employer)

    if request.method == 'POST':
        job.delete()
        messages.success(request, "Job offer deleted successfully.")
        return redirect('dashboard:employer_jobs')

    return redirect('dashboard:employer_jobs')

def company_detail(request, pk):
    company = get_object_or_404(Employer, pk=pk)
    active_jobs = Job.objects.filter(employer=company, is_active=True)
    
    context = {
        'company': company,
        'active_jobs': active_jobs,
    }
    return render(request, 'jobs/company_detail.html', context)
