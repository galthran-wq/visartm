﻿from django.shortcuts import render, redirect
from django.http import (HttpResponseForbidden, HttpResponse,
                         HttpResponseNotFound)
from django.contrib.auth.decorators import login_required

from datetime import datetime
import json
import os

from datasets.models import Dataset
from models.models import ArtmModel
from assessment.models import (AssessmentProblem, AssessmentTask,
                               ProblemAssessor, ExamVerification)
from django.contrib.auth.models import User
import visartm.views as general_views
from django.conf import settings


@login_required
def problems_list(request):
    assessment_problems = []
    for entry in ProblemAssessor.objects.filter(assessor=request.user):
        assessment_problems.append(
            {
                "problem": entry.problem,
                "tasks": AssessmentTask.objects.filter(
                    assessor=request.user,
                    problem=entry.problem,
                    status=1),
                "supervise": (
                    entry.problem.dataset.owner == request.user)})
    context = {"assessment_problems": assessment_problems}
    context["datasets"] = Dataset.objects_safe(request)

    assessment_folder = os.listdir(
        os.path.join(
            settings.BASE_DIR,
            "templates",
            "assessment"))
    context["types"] = [x for x in assessment_folder if '.' not in x]
    return render(request, 'assessment/problems_list.html', (context))


@login_required
def problem(request):
    if request.method == 'POST':
        problem = AssessmentProblem.objects.get(id=request.POST["problem_id"])
        if not problem.can_assess(request.user):
            return HttpResponseForbidden(
                ("You are not authorized to assess this problem, "
                 "so you can't make any changes to it."))

        problem.alter(request)
        if "next" in request.POST:
            return redirect(request.POST["next"])
        else:
            return redirect("/assessment/problem?problem_id=" +
                            str(problem.id) + "&mode=settings")

    problem = AssessmentProblem.objects.get(id=request.GET["problem_id"])
    problem.refresh()
    if problem.dataset.owner != request.user:
        return HttpResponseForbidden(
            "Only owner of dataset (%s) can see assessment problem."
            % str(problem.dataset.owner))

    if "mode" in request.GET and request.GET["mode"] == "settings":
        context = problem.get_view_context()
        context["no_footer"] = True
        return render(
            request,
            os.path.join(
                "assessment",
                problem.type,
                "settings.html"),
            (context))
    elif "mode" in request.GET and request.GET["mode"] == "report":
        if problem.type == "segmentation":
            context = problem.get_report_context()
            return render(
                request,
                os.path.join(
                    "assessment",
                    problem.type,
                    "report.html"),
                (context))
        else:
            return HttpResponse("Reports on this problem are not provided.")
    elif "mode" in request.GET and request.GET["mode"] == "assessor_report":
        return problem.get_module().get_assessor_report(problem, request)
    else:
        from django.contrib.auth.models import User
        not_assessors = [x.username for x in User.objects.all()]
        assessors = [
            x.assessor.username for x in ProblemAssessor.objects.filter(
                problem=problem)]
        for assessor in assessors:
            not_assessors.remove(assessor)
        context = ({
            "problem": problem,
            "assessors": assessors,
            "not_assessors": not_assessors,
            "tasks_in_progress": AssessmentTask.objects.filter(problem=problem,
                                                               status=1),
            "count_tasks": problem.count_tasks(),
            "models": ArtmModel.objects.filter(dataset=problem.dataset)
        })
    return render(request, "assessment/problem.html", context)


@login_required
def create_problem(request):
    dataset_id = int(request.GET["dataset_id"])
    type = request.GET["type"]
    dataset = Dataset.objects.get(id=dataset_id)
    if dataset.owner != request.user:
        return HttpResponseForbidden(
            "Only owner of dataset (%s) can create assessment problem." % str(
                dataset.owner))
    problem = AssessmentProblem()
    problem.dataset = dataset
    problem.type = type
    problem.save()
    problem.get_module().initialize_problem(problem)

    relation = ProblemAssessor()
    relation.problem = problem
    relation.assessor = request.user
    relation.save()

    return redirect("/assessment/problem?problem_id=" + str(problem.id))


@login_required
def get_task(request):
    problem = AssessmentProblem.objects.get(id=request.GET["problem_id"])

    if problem.can_assess(request.user):
        if problem.exam_needed:
            try:
                ver = ExamVerification.objects.get(
                    problem=problem, assessor=request.user)
            except BaseException:
                ver = ExamVerification()
                ver.problem = problem
                ver.assessor = request.user
                ver.passed = False
                ver.save()
            if not ver.passed:
                import urllib
                exam_url = "%s/start_exam?%s" % (
                    problem.exam_host,
                    urllib.parse.urlencode({
                        "username": request.user.username,
                        "problem_id": problem.id,
                        "host": request.META['HTTP_HOST']
                    })
                )
                return general_views.message(
                    request,
                    ("Вам нужно пройти тестирование, "
                     "прежде чем приступать к оцениванию.<br>"
                     "Чтобы приступить к тестированию, "
                     "щёлкните <a href=%s>здесь</a>.") %
                    exam_url)

        task = problem.create_task(request)
        if not task:
            return general_views.message(
                request, "Seems like everything is assessed!")
        return redirect("/assessment/task?task_id=" + str(task.id))
    else:
        return HttpResponseForbidden((
            "You are not allowed to make assessions "
            "in this assessment problem."))


@login_required
def task(request):
    if request.method == 'POST':
        task = AssessmentTask.objects.get(id=request.POST["task_id"])
        if "finished" in request.POST:
            task.finalize(request.POST)
            task.completion_time = datetime.now()
            task.status = 2
            task.save()

            if ("continue" in request.POST and
                    request.POST["continue"] == "true"):
                return redirect(
                    "/assessment/get_task?problem_id=%d" %
                    task.problem.id)
            else:
                return general_views.message(
                    request,
                    "Thank you! Assess one more task?<br>" +
                    "<a href='/assessment/get_task?problem_id=" +
                    str(
                        task.problem.id) +
                    "'>Yes</a>.<br>" +
                    "<a href='/dataset?dataset=" +
                    task.problem.dataset.text_id +
                    "'>No</a>.<br>")
        else:
            task.alter(request.POST)
            return redirect("/assessment/task?task_id=" + str(task.id))
    try:
        task = AssessmentTask.objects.get(id=request.GET["task_id"])
    except BaseException:
        return HttpResponseForbidden("Task doen't exist or was timed out.")
    if task.assessor != request.user:
        return HttpResponseForbidden("This is not your task.")
    if task.status == 2:
        return HttpResponseForbidden("Task is already completed.")

    return render(
        request, os.path.join(
            "assessment", task.problem.type, "assessor.html"), (
            task.get_view_context()))


def add_assessor(request):
    problem = AssessmentProblem.objects.get(id=request.GET["problem_id"])
    if request.user != problem.dataset.owner:
        return HttpResponseForbidden("You are not owner.")
    relation = ProblemAssessor()
    relation.assessor = User.objects.get(username=request.GET["username"])
    relation.problem = problem
    relation.save()
    return redirect("/assessment/problem?problem_id=" + str(problem.id))


def delete_assessor(request):
    problem = AssessmentProblem.objects.get(id=request.GET["problem_id"])
    if request.user != problem.dataset.owner:
        return HttpResponseForbidden("You are not owner.")
    if request.GET["username"] != problem.dataset.owner.username:
        ProblemAssessor.objects.filter(
            problem=problem,
            assessor__username=request.GET["username"]).delete()
    return redirect("/assessment/problem?problem_id=" + str(problem.id))


def get_results(request):
    problem = AssessmentProblem.objects.get(id=request.GET["problem_id"])
    if request.user != problem.dataset.owner:
        return HttpResponseForbidden("You are not owner.")
    response = HttpResponse(
        json.dumps(
            problem.get_results()),
        content_type='application/json')
    if "mode" in request.GET and request.GET['mode'] == 'file':
        timestamp = datetime.now().strftime("%d%m%y_%H%M%S")
        filename = "%s_%s_%s.json" % (
            problem.dataset.text_id, problem.type, timestamp)
        response['Content-Disposition'] = "attachment; filename=" + filename
    return response


@login_required
def instructions(request):
    problem = AssessmentProblem.objects.get(id=request.GET["problem_id"])
    if not problem.can_assess(request.user):
        return HttpResponseForbidden(
            "You are not authorized to assess this problem.")
    return render(
        request, os.path.join(
            "assessment", problem.type, "instructions.html"), (
            problem.get_view_context()))


def accept_exam(request):
    def hash_md5(s):
        import hashlib
        hasher = hashlib.md5()
        hasher.update(s.encode('utf-8'))
        return hasher.hexdigest()

    assessor = User.objects.get(username=request.GET["username"])
    problem = AssessmentProblem(id=int(request.GET["problem_id"]))
    try:
        ver = ExamVerification.objects.get(
            problem=problem, assessor=request.user)
    except BaseException:
        return HttpResponseNotFound("This exam wasn't requested by system.")

    received_hash = request.GET["hash"]
    correct_hash = hash_md5(
        assessor.username + str(problem.id) + settings.EXAM_KEY)
    if correct_hash != received_hash:
        return HttpResponseForbidden("Invalid verification hash.")

    ver.passed = True
    ver.save()

    return general_views.message(
        request, (
            "Тестирование успешно пройдено.<br>"
            "Чтобы приступить к оценивванию, щёлкните "
            "<a href='/assessment/get_task?problem_id=%d'>здесь</a>.")
        % (problem.id))
