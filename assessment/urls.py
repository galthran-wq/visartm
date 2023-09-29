from django.urls import re_path
import assessment.views as assessment_views

urlpatterns = [
    re_path(r'^$', assessment_views.problems_list),
    re_path(r'^problem$', assessment_views.problem),
    re_path(r'^create_problem$', assessment_views.create_problem),
    re_path(r'^task$', assessment_views.task),
    re_path(r'^get_task$', assessment_views.get_task),
    re_path(r'^add_assessor$', assessment_views.add_assessor),
    re_path(r'^delete_assessor$', assessment_views.delete_assessor),
    re_path(r'^get_results$', assessment_views.get_results),
    re_path(r'^instructions$', assessment_views.instructions),
    re_path(r'^accept_exam$', assessment_views.accept_exam),
]
