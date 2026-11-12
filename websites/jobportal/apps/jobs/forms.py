from django import forms
from .models import Application, Category, Job

class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = [
            'title', 'category', 'description', 'requirements',
            'location', 'salary', 'job_type', 'deadline'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Senior Backend Engineer'}),
            'category': forms.Select(),
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe the role and responsibilities...'}),
            'requirements': forms.Textarea(attrs={'rows': 4, 'placeholder': 'List required skills and qualifications...'}),
            'location': forms.TextInput(attrs={'placeholder': 'e.g. Remote, Paris'}),
            'salary': forms.TextInput(attrs={'placeholder': 'e.g. $70,000 - $90,000'}),
            'job_type': forms.Select(),
            'deadline': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_class = (
            'w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg text-sm '
            'focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all '
            'hover:border-blue-400'
        )
        for field in self.fields.values():
            existing_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing_class} {base_class}".strip()

class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['cover_letter']
        widgets = {
            'cover_letter': forms.Textarea(
                attrs={'rows': 4, 'placeholder': 'Write your cover letter here...'}
            )
        }

class JobSearchForm(forms.Form):
    search = forms.CharField(required=False, widget=forms.TextInput(
        attrs={'placeholder': 'Job title or keyword'}
    ))
    location = forms.CharField(required=False, widget=forms.TextInput(
        attrs={'placeholder': 'Location'}
    ))
    category = forms.ModelChoiceField(
        queryset=Category.objects.all().order_by('name'),
        required=False,
        empty_label='All Categories',
    )
    job_type = forms.ChoiceField(
        required=False,
        choices=[('', 'All Types')] + Job.JOB_TYPE_CHOICES
    )
