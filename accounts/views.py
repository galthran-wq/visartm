from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group

from accounts.models import Profile
from models.models import ArtmModel
from datasets.models import Dataset
from assessment.models import (AssessmentProblem, AssessmentTask,
                               ProblemAssessor)
from research.models import Research
from django.conf import settings
import visartm.views as general_views
from django.conf import settings


def login_view(request):
    if request.method == 'GET':
        return render(request, 'accounts/login.html')

    username = request.POST['username']
    password = request.POST['password']
    user = authenticate(username=username, password=password)

    if user is not None:
        if user.is_active:
            login(request, user)
            try:
                return redirect(request.GET["next"])
            except BaseException:
                return redirect("/")
        else:
            return general_views.message(
                request,
                ("Disabled account. "
                 "<a href='/accounts/login'>Try again</a>."))
    else:
        return general_views.message(
            request, ("Invalid login. "
                      "<a href='/accounts/login'>Try again</a>."))


def logout_view(request):
    logout(request)
    return redirect("/")


def signup(request):
    if request.method == 'GET':
        context = {"captcha": not settings.DEBUG}
        return render(request, 'accounts/signup.html', (context))

    username = request.POST['username']
    password = request.POST['password']
    password_repeat = request.POST['password_repeat']
    email = request.POST['email']

    if not settings.DEBUG:
        if 'captcha' in request.POST:
            captha_response = request.POST['captcha']
        else:
            captha_response = ""

        if not captha_response.lower() == 'additive':
            return general_views.message(
                request, "You haven't passed Turing test.")

    if len(username) < 3:
        return general_views.message(
            request, "Username must be at least 3 character long.")

    if password != password_repeat:
        return general_views.message(
            request, ("Your passwords don't match."
                      "<br><a href='/accounts/signup'>Try again</a>"))

    if registration_closed():
        return general_views.message(
            request, ("Registration is disabled on this server."))

    try:
        user = User.objects.create_user(username, email, password)

        # Granting permissions
        if settings.DEBUG:
            user.user_permissions.add(
                Permission.objects.get(codename='add_dataset'))
            user.user_permissions.add(
                Permission.objects.get(codename='add_model'))
        user.save()
    except BaseException:
        HttpResponse("Fail.")

    return general_views.message(
        request, ("Registration complete."
                  "<br><a href='/accounts/login'>To login page</a>."))


def account_view(request, user_name):
    account = User.objects.get(username=user_name)
    context = {
        "account": account,
        "profile": Profile.get_profile(account)
    }

    if account == request.user:
        context["public_datasets"] = Dataset.objects.filter(
            owner=account, is_public=True)
        context["private_datasets"] = Dataset.objects.filter(
            owner=account, is_public=False)
        context["models"] = ArtmModel.objects.filter(author=account)

    context["groups"] = account.groups.all()

    permissions = []
    permissions.append({"name": "Create dataset", "codename": "add_dataset",
                        "value": account.has_perm("datasets.add_dataset")})
    permissions.append({"name": "Create models and other",
                        "codename": "add_artmmodel",
                        "value": account.has_perm("models.add_artmmodel")})
    context["permissions"] = permissions

    return render(request, 'accounts/account.html', (context))


def group_view(request, group_id):
    group = Group.objects.get(id=group_id)
    context = {
        'group': group,
        'users': group.user_set.all()
    }
    return render(request, 'accounts/group.html', (context))


def sendmail(request):
    from django.core.mail import send_mail

    send_mail(
        "VisARTM",
        "Hello, %s. "
        "For some reason you have requested the test message. "
        "So, here it is." %
        request.user.username, settings.EMAIL_HOST_USER, [
            request.user.email], fail_silently=False)

    return HttpResponse("Sent.")


def vk_get_token(request):
    redirect_uri = settings.VK_HOST + "/accounts/vk_confirm_token"
    url_template = ("https://oauth.vk.com/authorize?"
                    "client_id=%d&display=page&redirect_uri=%s"
                    "&scope=%s&response_type=token")
    print(url_template)
    url = url_template % (
        settings.VK_CLIENT_ID,
        redirect_uri,
        settings.VK_PERMISSIONS)
    return HttpResponseRedirect(url)


def vk_confirm_token(request):
    return render(request, 'accounts/vk_token_extractor.html')


def registration_closed():
    try:
        if settings.REGISTRATION_CLOSED:
            return True
    except BaseException:
        return False
    return False
