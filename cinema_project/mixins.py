"""Shared helpers for views and forms."""
from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only staff users may create, edit or delete."""

    def test_func(self):
        return self.request.user.is_staff


class BootstrapFormMixin:
    """Adds Bootstrap 5 classes to every field so forms look right in AdminLTE."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class FormPageMixin:
    """Gives the shared form template its title, icon and cancel link."""

    page_title = ""
    page_icon = "bi-pencil-square"
    cancel_url = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(page_title=self.page_title, page_icon=self.page_icon, cancel_url=self.cancel_url)
        return ctx
