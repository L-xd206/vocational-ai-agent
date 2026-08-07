from django.http import JsonResponse

from .models import College


def api_college_list(request):
    colleges = College.objects.filter(is_enabled=True).values("id", "name")
    return JsonResponse({"colleges": list(colleges)})
