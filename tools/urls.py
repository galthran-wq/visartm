from django.urls import re_path
import tools.views as tools_views

urlpatterns = [
    re_path(r'^$', tools_views.tools_list),
    re_path(r'^vw2uci', tools_views.vw2uci),
    re_path(r'^uci2vw', tools_views.uci2vw),
    re_path(r'^vkloader', tools_views.vkloader),
]
