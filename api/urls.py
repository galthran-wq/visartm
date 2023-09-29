from django.urls import re_path
import api.views as api_views

urlpatterns = [
    re_path(r'^documents/get$', api_views.get_documents),
    re_path(r'^polygons/children$', api_views.get_polygon_children),
    re_path(r'^settings/set$', api_views.set_parameter),
]
