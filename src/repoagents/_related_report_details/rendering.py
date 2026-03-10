from __future__ import annotations

from collections.abc import Sequence

from .html import (
    _render_related_report_detail_html_copy,
    _render_related_report_detail_html_list,
    _render_related_report_detail_html_subtitle,
)
from .models import (
    RELATED_REPORT_DETAIL_SECTION_ORDER,
    RelatedReportDetailBlock,
    RelatedReportDetailHtmlLayoutPolicy,
    RelatedReportDetailLabelStyle,
    RelatedReportDetailLineLayoutKind,
    RelatedReportDetailLineLayoutPolicy,
    RelatedReportDetailSection,
)


def build_related_report_detail_summary(
    *,
    mismatch_warnings: Sequence[str],
    policy_drift_warnings: Sequence[str],
    remediation: str | None,
) -> str | None:
    block = build_related_report_detail_block(
        mismatch_warnings=mismatch_warnings,
        policy_drift_warnings=policy_drift_warnings,
        remediation=remediation,
    )
    if block is None:
        return None
    lines = [format_related_report_detail_title("display")]
    for section in block.sections:
        lines.append(format_related_report_detail_section_label(section.key, "display"))
        lines.extend(f"- {warning}" for warning in section.items)
    if block.remediation:
        lines.append(
            f"{format_related_report_detail_remediation_label('display')}: {block.remediation}"
        )
    return "\n".join(lines)


def extract_related_report_warning_lines(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    warnings: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            warnings.append(item)
            continue
        if not isinstance(item, dict):
            continue
        label = _string_or_none(item.get("label")) or "Related report"
        warning = _string_or_none(item.get("warning")) or "issue filter mismatch"
        warnings.append(f"{label}: {warning}")
    return tuple(warnings)


def collect_related_report_warning_lines(*values: object) -> tuple[str, ...]:
    warnings: list[str] = []
    for value in values:
        warnings.extend(extract_related_report_warning_lines(value))
    return tuple(warnings)


def build_related_report_detail_block(
    *,
    mismatch_warnings: Sequence[str],
    policy_drift_warnings: Sequence[str],
    remediation: str | None,
) -> RelatedReportDetailBlock | None:
    section_items = {
        "mismatches": tuple(item for item in mismatch_warnings if item),
        "policy_drifts": tuple(item for item in policy_drift_warnings if item),
    }
    sections = tuple(
        RelatedReportDetailSection(key=key, items=section_items[key])
        for key in RELATED_REPORT_DETAIL_SECTION_ORDER
        if section_items[key]
    )
    if not sections:
        return None
    return RelatedReportDetailBlock(
        sections=sections,
        remediation=remediation if section_items["policy_drifts"] and remediation else None,
    )


def build_related_report_detail_line_layout(
    kind: RelatedReportDetailLineLayoutKind,
    *,
    prefix: str = "",
) -> RelatedReportDetailLineLayoutPolicy:
    if kind == "machine_markdown":
        return RelatedReportDetailLineLayoutPolicy(
            title_prefix="- ",
            section_prefix="  - ",
            item_prefix="    - ",
            remediation_prefix="  - ",
        )
    return RelatedReportDetailLineLayoutPolicy(
        title_prefix=prefix,
        section_prefix=f"{prefix}  ",
        item_prefix=f"{prefix}    - ",
        remediation_prefix=f"{prefix}  ",
    )


def build_related_report_detail_html_layout() -> RelatedReportDetailHtmlLayoutPolicy:
    return RelatedReportDetailHtmlLayoutPolicy(
        subtitle_tag="p",
        subtitle_class="run-subtitle",
        list_tag="ul",
        list_class="list",
        item_tag="li",
        copy_tag="p",
        copy_class="copy",
        title_margin_top="0.8rem",
        section_margin_top="0.55rem",
        remediation_margin_top="0.55rem",
        remediation_copy_margin_top="0.3rem",
    )


def render_related_report_detail_lines(
    block: RelatedReportDetailBlock | None,
    *,
    title: str,
    section_label_style: RelatedReportDetailLabelStyle,
    remediation_label_style: RelatedReportDetailLabelStyle,
    layout_policy: RelatedReportDetailLineLayoutPolicy,
) -> tuple[str, ...]:
    if block is None:
        return ()
    lines: list[str] = [f"{layout_policy.title_prefix}{title}"]
    for section in block.sections:
        lines.append(
            f"{layout_policy.section_prefix}"
            f"{format_related_report_detail_section_label(section.key, section_label_style)}:"
        )
        lines.extend(f"{layout_policy.item_prefix}{warning}" for warning in section.items)
    if block.remediation:
        lines.append(
            f"{layout_policy.remediation_prefix}"
            f"{format_related_report_detail_remediation_label(remediation_label_style)}: {block.remediation}"
        )
    return tuple(lines)


def render_related_report_detail_html_fragments(
    block: RelatedReportDetailBlock | None,
    *,
    title_style: RelatedReportDetailLabelStyle,
    section_label_style: RelatedReportDetailLabelStyle,
    remediation_label_style: RelatedReportDetailLabelStyle,
    layout_policy: RelatedReportDetailHtmlLayoutPolicy,
) -> tuple[str, ...]:
    if block is None:
        return ()
    fragments: list[str] = [
        _render_related_report_detail_html_subtitle(
            format_related_report_detail_title(title_style),
            subtitle_tag=layout_policy.subtitle_tag,
            margin_top=layout_policy.title_margin_top,
            subtitle_class=layout_policy.subtitle_class,
        )
    ]
    for section in block.sections:
        fragments.append(
            _render_related_report_detail_html_subtitle(
                format_related_report_detail_section_label(section.key, section_label_style),
                subtitle_tag=layout_policy.subtitle_tag,
                margin_top=layout_policy.section_margin_top,
                subtitle_class=layout_policy.subtitle_class,
            )
        )
        fragments.append(
            _render_related_report_detail_html_list(
                section.items,
                list_tag=layout_policy.list_tag,
                list_class=layout_policy.list_class,
                item_tag=layout_policy.item_tag,
            )
        )
    if block.remediation:
        fragments.append(
            _render_related_report_detail_html_subtitle(
                format_related_report_detail_remediation_label(remediation_label_style),
                subtitle_tag=layout_policy.subtitle_tag,
                margin_top=layout_policy.remediation_margin_top,
                subtitle_class=layout_policy.subtitle_class,
            )
        )
        fragments.append(
            _render_related_report_detail_html_copy(
                block.remediation,
                copy_tag=layout_policy.copy_tag,
                copy_class=layout_policy.copy_class,
                margin_top=layout_policy.remediation_copy_margin_top,
            )
        )
    return tuple(fragments)


def format_related_report_detail_title(style: RelatedReportDetailLabelStyle) -> str:
    if style == "machine":
        return "related_report_details"
    return "related report details"


def format_related_report_detail_section_label(
    key: str,
    style: RelatedReportDetailLabelStyle,
) -> str:
    if style == "machine":
        return key
    return _display_section_label(key)


def format_related_report_detail_remediation_label(
    style: RelatedReportDetailLabelStyle,
) -> str:
    if style == "machine":
        return "remediation"
    return "remediation"


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _display_section_label(key: str) -> str:
    if key == "policy_drifts":
        return "policy drifts"
    return key
