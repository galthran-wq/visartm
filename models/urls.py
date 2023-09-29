from django.urls import re_path
import models.views as models_views

urlpatterns = [
    re_path(r'^$', models_views.models_list),
    re_path(r'^reload_model$', models_views.reload_model),
    re_path(r'^arrange_topics$', models_views.arrange_topics),
    re_path(r'^reset_visuals$', models_views.reset_visuals),
    re_path(r'^create$', models_views.create_model),
    re_path(r'^delete_model$', models_views.delete_model),
    re_path(r'^delete_all_models$', models_views.delete_all_models),
    re_path(r'^settings$', models_views.model_settings),
    re_path(r'^rename_topic$', models_views.rename_topic),
    re_path(r'^related_topics$', models_views.related_topics),
    re_path(r'^model_log$', models_views.model_log),
    re_path(r'^dump$', models_views.dump_model),
    re_path(r'^delete_cached_distances$', models_views.delete_cached_distances),
]
