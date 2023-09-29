from django.urls import re_path
import visual.views as visual_views

urlpatterns = [
    re_path(r'^global', visual_views.visual_global),
    re_path(r'^example/(?P<vis_name>\w+)$', visual_views.example),
    re_path(r'^clear', visual_views.clear),
]
