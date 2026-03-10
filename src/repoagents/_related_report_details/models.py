from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RelatedReportDetailSection:
    key: str
    items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RelatedReportDetailBlock:
    sections: tuple[RelatedReportDetailSection, ...]
    remediation: str | None


@dataclass(frozen=True, slots=True)
class RelatedReportDetailLineLayoutPolicy:
    title_prefix: str
    section_prefix: str
    item_prefix: str
    remediation_prefix: str


@dataclass(frozen=True, slots=True)
class RelatedReportDetailHtmlLayoutPolicy:
    subtitle_tag: str
    subtitle_class: str
    list_tag: str
    list_class: str
    item_tag: str
    copy_tag: str
    copy_class: str
    title_margin_top: str
    section_margin_top: str
    remediation_margin_top: str
    remediation_copy_margin_top: str


RelatedReportDetailLabelStyle = Literal["display", "machine"]
RelatedReportDetailLineLayoutKind = Literal["machine_markdown", "indented_cli"]
RELATED_REPORT_DETAIL_SECTION_ORDER = ("mismatches", "policy_drifts")
