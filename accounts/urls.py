from django.urls import re_path
import accounts.views as accounts_views
import django.contrib.auth.views as auth_views

urlpatterns = [
    re_path(r'^login', accounts_views.login_view),
    re_path(r'^logout', accounts_views.logout_view),
    re_path(r'^signup', accounts_views.signup),
    re_path(r'^sendmail', accounts_views.sendmail),
    # re_path(r'password_reset_done$', auth_views.password_reset_done,
    #     name='password_reset_done'),
    # re_path(r'password_reset_confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/',
    #     auth_views.password_reset_confirm, name='password_reset_confirm'),
    # re_path(r'password_reset_complete$', auth_views.password_reset_complete,
    #     name='password_reset_complete'),
    # re_path(r'password_reset', auth_views.password_reset, name='password_reset'),
    re_path(r'^user/(?P<user_name>.+)$',
        accounts_views.account_view,
        name='account'),
    re_path(r'^group/(?P<group_id>\d+)$', accounts_views.group_view, name='group'),

    re_path(r'^vk_get_token', accounts_views.vk_get_token),
    re_path(r'^vk_confirm_token$', accounts_views.vk_confirm_token),
]
