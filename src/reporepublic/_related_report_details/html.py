from __future__ import annotations

from collections.abc import Sequence
from html import escape


def _render_related_report_detail_html_subtitle(
    label: str,
    *,
    subtitle_tag: str = "p",
    margin_top: str,
    subtitle_class: str,
) -> str:
    return _render_related_report_detail_html_text_element(
        label,
        tag=subtitle_tag,
        class_name=subtitle_class,
        style=_format_related_report_detail_html_style(margin_top=margin_top),
    )


def _render_related_report_detail_html_list(
    items: Sequence[str],
    *,
    list_tag: str,
    list_class: str,
    item_tag: str,
) -> str:
    return _render_related_report_detail_html_wrapper(
        "".join(_render_related_report_detail_html_text_element(item, tag=item_tag) for item in items),
        tag=list_tag,
        class_name=list_class,
    )


def _render_related_report_detail_html_copy(
    text: str,
    *,
    copy_tag: str,
    copy_class: str,
    margin_top: str,
) -> str:
    return _render_related_report_detail_html_text_element(
        text,
        tag=copy_tag,
        class_name=copy_class,
        style=_format_related_report_detail_html_style(margin_top=margin_top),
    )


def _format_related_report_detail_html_style(*, margin_top: str | None = None) -> str | None:
    declarations: list[str] = []
    if margin_top:
        declarations.append(f"margin-top: {margin_top};")
    if not declarations:
        return None
    return " ".join(declarations)


def _format_related_report_detail_html_attributes(
    *,
    class_name: str | None = None,
    style: str | None = None,
) -> str:
    attributes: list[tuple[str, str]] = []
    if class_name:
        attributes.append(("class", class_name))
    if style:
        attributes.append(("style", style))
    if not attributes:
        return ""
    rendered = " ".join(f'{name}="{escape(value, quote=True)}"' for name, value in attributes)
    return f" {rendered}"


def _render_related_report_detail_html_wrapper(
    content: str,
    *,
    tag: str,
    class_name: str | None = None,
    style: str | None = None,
) -> str:
    attrs = _format_related_report_detail_html_attributes(
        class_name=class_name,
        style=style,
    )
    return f"<{tag}{attrs}>{content}</{tag}>"


def _render_related_report_detail_html_text_element(
    text: str,
    *,
    tag: str,
    class_name: str | None = None,
    style: str | None = None,
) -> str:
    return _render_related_report_detail_html_wrapper(
        escape(text),
        tag=tag,
        class_name=class_name,
        style=style,
    )
