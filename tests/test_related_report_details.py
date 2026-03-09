from __future__ import annotations

from reporepublic._related_report_details.html import (
    _format_related_report_detail_html_attributes,
    _format_related_report_detail_html_style,
    _render_related_report_detail_html_wrapper,
)
from reporepublic._related_report_details.models import (
    RELATED_REPORT_DETAIL_SECTION_ORDER,
    RelatedReportDetailBlock,
    RelatedReportDetailHtmlLayoutPolicy,
    RelatedReportDetailLineLayoutPolicy,
    RelatedReportDetailSection,
)
from reporepublic._related_report_details.rendering import (
    build_related_report_detail_block,
    build_related_report_detail_html_layout,
    build_related_report_detail_line_layout,
    build_related_report_detail_summary,
    collect_related_report_warning_lines,
    extract_related_report_warning_lines,
    format_related_report_detail_remediation_label,
    format_related_report_detail_section_label,
    format_related_report_detail_title,
    render_related_report_detail_html_fragments,
    render_related_report_detail_lines,
)


def test_build_related_report_detail_summary_returns_none_without_warnings() -> None:
    assert (
        build_related_report_detail_summary(
            mismatch_warnings=(),
            policy_drift_warnings=(),
            remediation=None,
        )
        is None
    )


def test_build_related_report_detail_summary_renders_mismatches_only() -> None:
    assert (
        build_related_report_detail_summary(
            mismatch_warnings=("Cleanup preview: issue filter mismatch",),
            policy_drift_warnings=(),
            remediation="ignored",
        )
        == "related report details\n"
        "mismatches\n"
        "- Cleanup preview: issue filter mismatch"
    )


def test_build_related_report_detail_summary_renders_policy_drifts_with_remediation() -> None:
    assert (
        build_related_report_detail_summary(
            mismatch_warnings=(),
            policy_drift_warnings=("Sync audit: embedded policy differs from current config",),
            remediation="refresh report exports",
        )
        == "related report details\n"
        "policy drifts\n"
        "- Sync audit: embedded policy differs from current config\n"
        "remediation: refresh report exports"
    )


def test_extract_related_report_warning_lines_formats_structured_entries() -> None:
    assert extract_related_report_warning_lines(
        [
            {"label": "Cleanup preview", "warning": "issue filter mismatch"},
            {"label": "Sync audit", "warning": "embedded policy differs from current config"},
        ]
    ) == (
        "Cleanup preview: issue filter mismatch",
        "Sync audit: embedded policy differs from current config",
    )


def test_collect_related_report_warning_lines_merges_string_and_structured_sources() -> None:
    assert collect_related_report_warning_lines(
        ["Cleanup result: issue filter mismatch"],
        [{"label": "Sync audit", "warning": "embedded policy differs from current config"}],
        None,
    ) == (
        "Cleanup result: issue filter mismatch",
        "Sync audit: embedded policy differs from current config",
    )


def test_build_related_report_detail_block_and_render_lines() -> None:
    block = build_related_report_detail_block(
        mismatch_warnings=("Cleanup preview: issue filter mismatch",),
        policy_drift_warnings=("Sync audit: embedded policy differs from current config",),
        remediation="refresh report exports",
    )
    assert block == RelatedReportDetailBlock(
        sections=(
            RelatedReportDetailSection(
                key="mismatches",
                items=("Cleanup preview: issue filter mismatch",),
            ),
            RelatedReportDetailSection(
                key="policy_drifts",
                items=("Sync audit: embedded policy differs from current config",),
            ),
        ),
        remediation="refresh report exports",
    )
    assert render_related_report_detail_lines(
        block,
        title="related report details:",
        section_label_style="machine",
        remediation_label_style="machine",
        layout_policy=build_related_report_detail_line_layout("indented_cli"),
    ) == (
        "related report details:",
        "  mismatches:",
        "    - Cleanup preview: issue filter mismatch",
        "  policy_drifts:",
        "    - Sync audit: embedded policy differs from current config",
        "  remediation: refresh report exports",
    )


def test_build_related_report_detail_line_layout_for_machine_markdown() -> None:
    assert build_related_report_detail_line_layout("machine_markdown") == (
        RelatedReportDetailLineLayoutPolicy(
            title_prefix="- ",
            section_prefix="  - ",
            item_prefix="    - ",
            remediation_prefix="  - ",
        )
    )


def test_build_related_report_detail_line_layout_for_indented_cli() -> None:
    assert build_related_report_detail_line_layout("indented_cli", prefix="> ") == (
        RelatedReportDetailLineLayoutPolicy(
            title_prefix="> ",
            section_prefix=">   ",
            item_prefix=">     - ",
            remediation_prefix=">   ",
        )
    )


def test_build_related_report_detail_html_layout() -> None:
    assert build_related_report_detail_html_layout() == (
        RelatedReportDetailHtmlLayoutPolicy(
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
    )


def test_render_related_report_detail_html_fragments() -> None:
    block = build_related_report_detail_block(
        mismatch_warnings=("Cleanup preview: issue filter mismatch",),
        policy_drift_warnings=("Sync audit: embedded policy differs from current config",),
        remediation="refresh report exports",
    )
    assert render_related_report_detail_html_fragments(
        block,
        title_style="display",
        section_label_style="display",
        remediation_label_style="display",
        layout_policy=build_related_report_detail_html_layout(),
    ) == (
        '<p class="run-subtitle" style="margin-top: 0.8rem;">related report details</p>',
        '<p class="run-subtitle" style="margin-top: 0.55rem;">mismatches</p>',
        '<ul class="list"><li>Cleanup preview: issue filter mismatch</li></ul>',
        '<p class="run-subtitle" style="margin-top: 0.55rem;">policy drifts</p>',
        '<ul class="list"><li>Sync audit: embedded policy differs from current config</li></ul>',
        '<p class="run-subtitle" style="margin-top: 0.55rem;">remediation</p>',
        '<p class="copy" style="margin-top: 0.3rem;">refresh report exports</p>',
    )


def test_render_related_report_detail_html_fragments_respects_tag_policy() -> None:
    block = build_related_report_detail_block(
        mismatch_warnings=("Cleanup preview: issue filter mismatch",),
        policy_drift_warnings=(),
        remediation=None,
    )
    assert render_related_report_detail_html_fragments(
        block,
        title_style="display",
        section_label_style="display",
        remediation_label_style="display",
        layout_policy=RelatedReportDetailHtmlLayoutPolicy(
            subtitle_tag="h4",
            subtitle_class="detail-subtitle",
            list_tag="ol",
            list_class="detail-list",
            item_tag="li",
            copy_tag="div",
            copy_class="detail-copy",
            title_margin_top="1rem",
            section_margin_top="0.6rem",
            remediation_margin_top="0.6rem",
            remediation_copy_margin_top="0.4rem",
        ),
    ) == (
        '<h4 class="detail-subtitle" style="margin-top: 1rem;">related report details</h4>',
        '<h4 class="detail-subtitle" style="margin-top: 0.6rem;">mismatches</h4>',
        '<ol class="detail-list"><li>Cleanup preview: issue filter mismatch</li></ol>',
    )


def test_private_format_related_report_detail_html_style() -> None:
    assert _format_related_report_detail_html_style(margin_top="0.8rem") == "margin-top: 0.8rem;"
    assert _format_related_report_detail_html_style() is None


def test_private_format_related_report_detail_html_attributes() -> None:
    assert _format_related_report_detail_html_attributes(
        class_name='detail"subtitle',
        style='margin-top: 0.8rem;"',
    ) == ' class="detail&quot;subtitle" style="margin-top: 0.8rem;&quot;"'
    assert _format_related_report_detail_html_attributes() == ""


def test_private_render_related_report_detail_html_wrapper() -> None:
    assert _render_related_report_detail_html_wrapper(
        "<li>one</li>",
        tag="ul",
        class_name="detail-list",
        style="margin-top: 0.6rem;",
    ) == '<ul class="detail-list" style="margin-top: 0.6rem;"><li>one</li></ul>'
    assert _render_related_report_detail_html_wrapper("body", tag="div") == "<div>body</div>"


def test_related_report_detail_label_policy_formats_titles_and_sections() -> None:
    assert RELATED_REPORT_DETAIL_SECTION_ORDER == ("mismatches", "policy_drifts")
    assert format_related_report_detail_title("display") == "related report details"
    assert format_related_report_detail_title("machine") == "related_report_details"
    assert format_related_report_detail_section_label("mismatches", "display") == "mismatches"
    assert format_related_report_detail_section_label("policy_drifts", "display") == "policy drifts"
    assert format_related_report_detail_section_label("policy_drifts", "machine") == "policy_drifts"
    assert format_related_report_detail_remediation_label("display") == "remediation"
    assert format_related_report_detail_remediation_label("machine") == "remediation"
