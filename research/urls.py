from django.urls import re_path
import research.views as research_views

urlpatterns = [
    re_path(r'^$', research_views.researches),
    re_path(r'^create$', research_views.create_research),
    re_path(r'^rerun$', research_views.rerun_research),
    re_path(r'^scripts/(?P<script_name>\w+)$', research_views.view_script),
    re_path(r'^(?P<research_id>\d+)/$', research_views.show_research),
    re_path(r'^(?P<research_id>\d+)/pic/(?P<pic_id>\d+).png$',
        research_views.get_picture),
    re_path(r'^(?P<research_id>\d+)/pic/(?P<pic_id>\w+).eps$',
        research_views.get_picture_eps),
    re_path(r'^(?P<research_id>\d+)/pic/(?P<txt_id>\d+).txt$',
        research_views.get_txt)
]
