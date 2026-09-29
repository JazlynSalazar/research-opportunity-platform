from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from opportunities.forms import (
    ResearchProfileForm,
    ResearchProfileWeightForm,
)
from opportunities.models import (
    ClassificationReview,
    ResearchProfile,
    ResearchProfileWeight,
)


def unique_profile_key(
    user,
    name,
    exclude_pk=None,
):
    base = slugify(name)[:80]

    if not base:
        base = "profile"

    candidate = base
    number = 2

    queryset = (
        ResearchProfile.objects
        .filter(
            owner=user,
            is_template=False,
        )
    )

    if exclude_pk is not None:
        queryset = queryset.exclude(
            pk=exclude_pk
        )

    while queryset.filter(
        key=candidate
    ).exists():
        candidate = (
            f"{base}-{number}"
        )[:100]

        number += 1

    return candidate


def signal_suggestions():
    signals = set()

    for category, name in (
        ResearchProfileWeight.objects
        .values_list(
            "category",
            "name",
        )
        .distinct()
    ):
        signals.add(
            (
                category,
                name,
            )
        )

    for category, name in (
        ClassificationReview.objects
        .filter(
            is_current=True,
        )
        .values_list(
            "suggestion_category",
            "suggestion_name",
        )
        .distinct()
    ):
        signals.add(
            (
                category,
                name,
            )
        )

    return sorted(
        signals,
        key=lambda item: (
            item[0],
            item[1].lower(),
        ),
    )


def choose_replacement_default(
    user,
    exclude_pk=None,
):
    queryset = (
        ResearchProfile.objects
        .filter(
            owner=user,
            is_template=False,
            active=True,
        )
        .order_by("name")
    )

    if exclude_pk is not None:
        queryset = queryset.exclude(
            pk=exclude_pk
        )

    replacement = queryset.first()

    if replacement:
        ResearchProfile.objects.filter(
            owner=user,
            is_template=False,
            is_default=True,
        ).update(
            is_default=False
        )

        replacement.is_default = True

        replacement.save(
            update_fields=[
                "is_default"
            ]
        )

    return replacement


@login_required
def my_profiles(request):
    active_profiles = (
        ResearchProfile.objects
        .filter(
            owner=request.user,
            is_template=False,
            active=True,
        )
        .prefetch_related(
            "weights"
        )
        .order_by(
            "-is_default",
            "name",
        )
    )

    archived_profiles = (
        ResearchProfile.objects
        .filter(
            owner=request.user,
            is_template=False,
            active=False,
        )
        .prefetch_related(
            "weights"
        )
        .order_by("name")
    )

    templates = (
        ResearchProfile.objects
        .filter(
            owner__isnull=True,
            is_template=True,
            active=True,
        )
        .prefetch_related(
            "weights"
        )
        .order_by("name")
    )

    return render(
        request,
        "opportunities/my_profiles.html",
        {
            "active_profiles": (
                active_profiles
            ),
            "archived_profiles": (
                archived_profiles
            ),
            "templates": templates,
        },
    )


@login_required
def create_profile(request):
    if request.method == "POST":
        form = ResearchProfileForm(
            request.POST
        )

        if form.is_valid():
            profile = form.save(
                commit=False
            )

            profile.owner = (
                request.user
            )

            profile.key = (
                unique_profile_key(
                    request.user,
                    profile.name,
                )
            )

            profile.active = True
            profile.is_template = False

            has_profile = (
                ResearchProfile.objects
                .filter(
                    owner=request.user,
                    is_template=False,
                    active=True,
                )
                .exists()
            )

            profile.is_default = (
                not has_profile
            )

            profile.save()

            messages.success(
                request,
                (
                    f'Created profile '
                    f'"{profile.name}". '
                    f"Now add relevance signals."
                ),
            )

            return redirect(
                "edit_profile",
                profile_id=profile.pk,
            )

    else:
        form = ResearchProfileForm()

    return render(
        request,
        "opportunities/profile_form.html",
        {
            "form": form,
            "profile": None,
            "weight_form": None,
            "signal_suggestions": [],
        },
    )


@login_required
def edit_profile(
    request,
    profile_id,
):
    profile = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    if request.method == "POST":
        form = ResearchProfileForm(
            request.POST,
            instance=profile,
        )

        if form.is_valid():
            profile = form.save(
                commit=False
            )

            profile.key = (
                unique_profile_key(
                    request.user,
                    profile.name,
                    exclude_pk=profile.pk,
                )
            )

            profile.save()

            messages.success(
                request,
                "Profile details updated.",
            )

            return redirect(
                "edit_profile",
                profile_id=profile.pk,
            )

    else:
        form = ResearchProfileForm(
            instance=profile
        )

    weight_form = (
        ResearchProfileWeightForm()
    )

    return render(
        request,
        "opportunities/profile_form.html",
        {
            "form": form,
            "profile": profile,
            "weight_form": weight_form,
            "signal_suggestions": (
                signal_suggestions()
            ),
        },
    )


@login_required
@require_POST
def add_profile_weight(
    request,
    profile_id,
):
    profile = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    form = ResearchProfileWeightForm(
        request.POST
    )

    if form.is_valid():
        category = form.cleaned_data[
            "category"
        ]

        name = form.cleaned_data[
            "name"
        ]

        weight = form.cleaned_data[
            "weight"
        ]

        _, created = (
            ResearchProfileWeight.objects
            .update_or_create(
                profile=profile,
                category=category,
                name=name,
                defaults={
                    "weight": weight,
                },
            )
        )

        if created:
            message = (
                f'Added relevance signal '
                f'"{name}".'
            )
        else:
            message = (
                f'Updated relevance signal '
                f'"{name}".'
            )

        messages.success(
            request,
            message,
        )

    else:
        messages.error(
            request,
            (
                "The relevance signal could "
                "not be saved."
            ),
        )

    return redirect(
        "edit_profile",
        profile_id=profile.pk,
    )


@login_required
@require_POST
def remove_profile_weight(
    request,
    profile_id,
    weight_id,
):
    profile = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    weight = get_object_or_404(
        ResearchProfileWeight,
        pk=weight_id,
        profile=profile,
    )

    name = weight.name
    weight.delete()

    messages.success(
        request,
        (
            f'Removed relevance signal '
            f'"{name}".'
        ),
    )

    return redirect(
        "edit_profile",
        profile_id=profile.pk,
    )


@login_required
@require_POST
def set_default_profile(
    request,
    profile_id,
):
    profile = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    if not profile.active:
        profile.active = True

    ResearchProfile.objects.filter(
        owner=request.user,
        is_template=False,
        is_default=True,
    ).exclude(
        pk=profile.pk
    ).update(
        is_default=False
    )

    profile.is_default = True

    profile.save(
        update_fields=[
            "active",
            "is_default",
        ]
    )

    messages.success(
        request,
        (
            f'"{profile.name}" is now '
            f"your default profile."
        ),
    )

    return redirect(
        "my_profiles"
    )


@login_required
@require_POST
@transaction.atomic
def duplicate_profile(
    request,
    profile_id,
):
    original = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    name = (
        f"Copy of {original.name}"
    )

    duplicate = (
        ResearchProfile.objects.create(
            owner=request.user,
            key=unique_profile_key(
                request.user,
                name,
            ),
            name=name,
            description=(
                original.description
            ),
            active=True,
            is_default=False,
            is_template=False,
        )
    )

    ResearchProfileWeight.objects.bulk_create(
        [
            ResearchProfileWeight(
                profile=duplicate,
                category=weight.category,
                name=weight.name,
                weight=weight.weight,
            )
            for weight
            in original.weights.all()
        ]
    )

    messages.success(
        request,
        (
            f'Created "{duplicate.name}".'
        ),
    )

    return redirect(
        "edit_profile",
        profile_id=duplicate.pk,
    )


@login_required
@require_POST
@transaction.atomic
def copy_profile_template(
    request,
    template_id,
):
    template = get_object_or_404(
        ResearchProfile,
        pk=template_id,
        is_template=True,
        owner__isnull=True,
        active=True,
    )

    name = template.name

    has_profiles = (
        ResearchProfile.objects
        .filter(
            owner=request.user,
            is_template=False,
            active=True,
        )
        .exists()
    )

    profile = (
        ResearchProfile.objects.create(
            owner=request.user,
            key=unique_profile_key(
                request.user,
                name,
            ),
            name=name,
            description=(
                template.description
            ),
            active=True,
            is_default=(
                not has_profiles
            ),
            is_template=False,
        )
    )

    ResearchProfileWeight.objects.bulk_create(
        [
            ResearchProfileWeight(
                profile=profile,
                category=weight.category,
                name=weight.name,
                weight=weight.weight,
            )
            for weight
            in template.weights.all()
        ]
    )

    messages.success(
        request,
        (
            f'Created private profile '
            f'"{profile.name}".'
        ),
    )

    return redirect(
        "edit_profile",
        profile_id=profile.pk,
    )


@login_required
@require_POST
def toggle_profile_archive(
    request,
    profile_id,
):
    profile = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    if profile.active:
        was_default = (
            profile.is_default
        )

        profile.active = False
        profile.is_default = False

        profile.save(
            update_fields=[
                "active",
                "is_default",
            ]
        )

        if was_default:
            choose_replacement_default(
                request.user,
                exclude_pk=profile.pk,
            )

        messages.success(
            request,
            (
                f'Archived "{profile.name}".'
            ),
        )

    else:
        profile.active = True

        has_default = (
            ResearchProfile.objects
            .filter(
                owner=request.user,
                is_template=False,
                active=True,
                is_default=True,
            )
            .exclude(
                pk=profile.pk
            )
            .exists()
        )

        if not has_default:
            profile.is_default = True

        profile.save(
            update_fields=[
                "active",
                "is_default",
            ]
        )

        messages.success(
            request,
            (
                f'Restored "{profile.name}".'
            ),
        )

    return redirect(
        "my_profiles"
    )


@login_required
@require_POST
@transaction.atomic
def delete_profile(
    request,
    profile_id,
):
    profile = get_object_or_404(
        ResearchProfile,
        pk=profile_id,
        owner=request.user,
        is_template=False,
    )

    name = profile.name
    was_default = profile.is_default

    profile.delete()

    if was_default:
        choose_replacement_default(
            request.user
        )

    messages.success(
        request,
        (
            f'Deleted "{name}".'
        ),
    )

    return redirect(
        "my_profiles"
    )
