from core.seed_snapshot import restore_seed_snapshot

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def reset_state(request):
    if not restore_seed_snapshot():
        call_command("seed_demo_data", reset=True, verbosity=0)
        call_command("seed_kaggle_data", reset=True, verbosity=0)
    return JsonResponse({"status": "ok"})

from core.eval_views import eval_state

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/reset', reset_state, name='reset_state'),
    path('api/eval/state', eval_state, name='eval_state'),
    path('accounts/', include('apps.accounts.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('', include('apps.jobs.urls')),  # Keep only this one for jobs URLs
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
