from django.urls import re_path, include
from django.contrib import admin

import visartm.views as general_views
import datasets.views as datasets_views
import models.views as models_views


urlpatterns = [
    re_path('^datasets/', include('datasets.urls')),
    re_path('^models/', include('models.urls')),
    re_path(r'^admin/', admin.site.urls),
    re_path('^accounts/', include('accounts.urls')),
    re_path(r'^api/', include('api.urls')),
    re_path(r'^assessment/', include('assessment.urls')),
    re_path(r'^research/', include('research.urls')),
    re_path(r'^tools/', include('tools.urls')),
    re_path(r'^visual/', include('visual.urls')),


    # general
    re_path(r'^$', general_views.start_page, name='home'),
    re_path(r'^settings', general_views.settings_page),

    # docs
    re_path(r'^docs$', general_views.docs_page),
    re_path(r'^docs/(?P<page>\w+)$', general_views.docs_page),


    # Datasets special
    re_path(r'^dataset$', datasets_views.visual_dataset),
    re_path(r'^term$', datasets_views.visual_term),
    re_path(r'^modality$', datasets_views.visual_modality),
    re_path(r'^search$', datasets_views.global_search),
    re_path(r'^document$', datasets_views.visual_document),


    # Models and topics
    re_path(r'^topic$', models_views.visual_topic),
    re_path(r'^model$', models_views.visual_model),
]
