from django.urls import re_path
import datasets.views as datasets_views

urlpatterns = [
    re_path(r'^$', datasets_views.datasets_list),
    re_path(r'^reload$', datasets_views.dataset_reload),
    re_path(r'^create$', datasets_views.dataset_create),
    re_path(r'^delete$', datasets_views.dataset_delete),
    re_path(r'^dump$', datasets_views.dump),
    re_path(r'^download_vw$', datasets_views.download_vw),
    re_path(r'^document_all_topics$', datasets_views.document_all_topics),
    re_path(r'^document_segments$', datasets_views.document_segments),
]
