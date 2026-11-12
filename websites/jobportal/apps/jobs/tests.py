from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Employer, JobSeeker
from apps.jobs.models import Application, Category, Job


class ApplyJobViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.employer_user = user_model.objects.create_user(
            username='employer1',
            password='password123',
            is_employer=True,
        )
        self.job_seeker_user = user_model.objects.create_user(
            username='jobseeker1',
            password='password123',
            is_job_seeker=True,
        )

        self.employer = Employer.objects.create(
            user=self.employer_user,
            company_name='Helix AI',
        )
        self.job_seeker = JobSeeker.objects.create(user=self.job_seeker_user)
        self.category = Category.objects.create(
            name='Operations',
            icon='fas fa-briefcase',
        )
        self.job = Job.objects.create(
            title='Sales Operations Manager',
            employer=self.employer,
            category=self.category,
            description='Run the sales operations process.',
            requirements='3+ years of experience.',
            location='San Francisco',
            salary='$110,000 - $135,000',
            job_type='full_time',
            deadline=date(2026, 12, 31),
        )

    def test_apply_job_redirects_to_jobseeker_dashboard(self):
        self.client.force_login(self.job_seeker_user)

        response = self.client.post(
            reverse('jobs:apply_job', args=[self.job.id]),
            {'cover_letter': 'I would love to apply.'},
        )

        self.assertRedirects(response, reverse('dashboard:jobseeker_dashboard'))
        self.assertTrue(
            Application.objects.filter(
                job=self.job,
                job_seeker=self.job_seeker,
            ).exists()
        )

    def test_job_seeker_dashboard_alias_resolves(self):
        self.assertEqual(
            reverse('dashboard:job_seeker_dashboard'),
            reverse('dashboard:jobseeker_dashboard'),
        )


class JobSearchTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        employer_user = user_model.objects.create_user(
            username='search-employer',
            password='password123',
            is_employer=True,
        )
        employer = Employer.objects.create(
            user=employer_user,
            company_name='Search Co',
        )
        category = Category.objects.create(
            name='Engineering',
            icon='fas fa-code',
        )
        self.intern_job = Job.objects.create(
            title='Software Intern',
            employer=employer,
            category=category,
            description='Intern role.',
            requirements='Curious and eager to learn.',
            location='Paris',
            salary='$30,000 - $40,000',
            job_type='internship',
            deadline=date(2026, 12, 31),
        )
        self.manager_job = Job.objects.create(
            title='Product Manager',
            employer=employer,
            category=category,
            description='Manager role.',
            requirements='Product experience.',
            location='Berlin',
            salary='$90,000 - $110,000',
            job_type='full_time',
            deadline=date(2026, 12, 31),
        )

    def test_home_search_fields_are_optional(self):
        response = self.client.get(reverse('jobs:home'))

        self.assertContains(response, 'name="search" placeholder="Job title or keyword"')
        self.assertContains(response, 'name="location" placeholder="Location"')
        self.assertNotContains(
            response,
            'name="search" placeholder="Job title or keyword" required',
        )
        self.assertNotContains(
            response,
            'name="location" placeholder="Location" required',
        )

    def test_job_list_allows_searching_by_title_only(self):
        response = self.client.get(reverse('jobs:job_list'), {'search': 'intern'})

        self.assertContains(response, self.intern_job.title)
        self.assertNotContains(response, self.manager_job.title)

    def test_job_list_allows_searching_by_location_only(self):
        response = self.client.get(reverse('jobs:job_list'), {'location': 'Paris'})

        self.assertContains(response, self.intern_job.title)
        self.assertNotContains(response, self.manager_job.title)
