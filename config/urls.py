"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import include, path

from opportunities.discovery_views import discover
from opportunities.profile_views import (
    add_profile_weight,
    copy_profile_template,
    create_profile,
    delete_profile,
    duplicate_profile,
    edit_profile,
    my_profiles,
    remove_profile_weight,
    set_default_profile,
    toggle_profile_archive,
)


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "accounts/",
        include(
            "django.contrib.auth.urls"
        ),
    ),

    path(
        "discover/",
        discover,
        name="discover",
    ),

    path(
        "profiles/",
        my_profiles,
        name="my_profiles",
    ),

    path(
        "profiles/new/",
        create_profile,
        name="create_profile",
    ),

    path(
        "profiles/<int:profile_id>/edit/",
        edit_profile,
        name="edit_profile",
    ),

    path(
        "profiles/<int:profile_id>/signals/add/",
        add_profile_weight,
        name="add_profile_weight",
    ),

    path(
        "profiles/<int:profile_id>/signals/"
        "<int:weight_id>/remove/",
        remove_profile_weight,
        name="remove_profile_weight",
    ),

    path(
        "profiles/<int:profile_id>/default/",
        set_default_profile,
        name="set_default_profile",
    ),

    path(
        "profiles/<int:profile_id>/duplicate/",
        duplicate_profile,
        name="duplicate_profile",
    ),

    path(
        "profiles/<int:profile_id>/archive/",
        toggle_profile_archive,
        name="toggle_profile_archive",
    ),

    path(
        "profiles/<int:profile_id>/delete/",
        delete_profile,
        name="delete_profile",
    ),

    path(
        "profiles/copy/<int:template_id>/",
        copy_profile_template,
        name="copy_profile_template",
    ),
]
