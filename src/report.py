"""Run report generation for output/report.json and GitHub Actions step summaries."""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StageOutcome:
    """Outcome for an individual pipeline execution stage."""
    stage_name: str
    status: str  # "SUCCESS", "FAILED", "SKIPPED", "RUNNING"
    duration_seconds: float = 0.0
    details: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


class PipelineReporter:
    """Collects stage outcomes and writes sanitized summary reports."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.start_time = datetime.now(timezone.utc)
        self.stages: List[StageOutcome] = []
        self.selected_topic: Optional[str] = None
        self.selected_topic_id: Optional[str] = None
        self.mode: str = "draft"
        self.dry_run: bool = True
        self.post_id: Optional[str] = None
        self.post_url: Optional[str] = None
        self.qa_passed: Optional[bool] = None
        self.qa_failures: List[str] = []
        self.qa_warnings: List[str] = []
        self.qa_metrics: Dict[str, Any] = {}
        self.source_count: int = 0
        self.research_sources: List[Dict[str, Any]] = []
        self.screenshot_captured: bool = False
        self.overall_status: str = "IN_PROGRESS"
        self.next_action: str = ""

    def add_stage(
        self,
        stage_name: str,
        status: str,
        duration_seconds: float = 0.0,
        details: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record stage execution status."""
        self.stages.append(
            StageOutcome(
                stage_name=stage_name,
                status=status,
                duration_seconds=round(duration_seconds, 2),
                details=details,
                data=data or {},
            )
        )
        logger.info(f"[STAGE {stage_name}] Status: {status} ({duration_seconds:.2f}s) - {details or ''}")

    def finalize(self, success: bool, next_action: str = "") -> Dict[str, Any]:
        """Compile report data and write output/report.json and GitHub Step Summary."""
        end_time = datetime.now(timezone.utc)
        total_duration = round((end_time - self.start_time).total_seconds(), 2)
        self.overall_status = "SUCCESS" if success else "FAILED"
        self.next_action = next_action

        report_data = {
            "run_id": self.run_id,
            "overall_status": self.overall_status,
            "timestamp": end_time.isoformat(),
            "total_duration_seconds": total_duration,
            "dry_run": self.dry_run,
            "publish_mode": self.mode,
            "selected_topic_id": self.selected_topic_id,
            "selected_topic": self.selected_topic,
            "qa": {
                "passed": self.qa_passed,
                "failures": self.qa_failures,
                "warnings": self.qa_warnings,
                "metrics": self.qa_metrics,
            },
            "metrics": {
                "source_count": self.source_count,
                "screenshot_captured": self.screenshot_captured,
            },
            "research_sources": self.research_sources,
            "blogger": {
                "post_id": self.post_id,
                "post_url": self.post_url,
                "is_draft": self.mode == "draft",
            },
            "next_action": self.next_action,
            "stages": [
                {
                    "stage": s.stage_name,
                    "status": s.status,
                    "duration_seconds": s.duration_seconds,
                    "details": s.details,
                }
                for s in self.stages
            ],
        }

        # Write output/report.json
        report_path = self.output_dir / "report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        # Write GitHub Step Summary if running in GitHub Actions
        self._write_github_step_summary(report_data)

        return report_data

    def _write_github_step_summary(self, report: Dict[str, Any]) -> None:
        """Write formatted Markdown to GITHUB_STEP_SUMMARY environment file."""
        github_summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        summary_md = self.generate_markdown_summary(report)

        # Always save local summary copy
        local_md_path = self.output_dir / "summary.md"
        local_md_path.write_text(summary_md, encoding="utf-8")

        if github_summary_path:
            try:
                with open(github_summary_path, "a", encoding="utf-8") as f:
                    f.write(summary_md)
            except Exception as e:
                logger.warning(f"Could not append to GITHUB_STEP_SUMMARY: {e}")

    def generate_markdown_summary(self, report: Dict[str, Any]) -> str:
        """Produce clean GitHub Actions summary Markdown."""
        status_icon = "✅" if report["overall_status"] == "SUCCESS" else "❌"
        dry_run_tag = "**[DRY RUN]** " if report["dry_run"] else ""

        lines = [
            f"# {status_icon} Blogger Content Pipeline Summary {dry_run_tag}",
            "",
            f"- **Run ID:** `{report['run_id']}`",
            f"- **Duration:** {report['total_duration_seconds']}s",
            f"- **Topic:** {report['selected_topic'] or 'None selected'}",
            f"- **Publish Mode:** `{report['publish_mode']}` (Draft default enforced)",
            f"- **Sources Verified:** {report['metrics']['source_count']}",
            f"- **Screenshot Captured:** {'Yes' if report['metrics']['screenshot_captured'] else 'No / Skipped'}",
            "",
        ]

        qa_metrics = report["qa"].get("metrics") or {}
        if qa_metrics:
            lines.extend(["### 📊 Quality Check Metrics", ""])
            for key, value in qa_metrics.items():
                label = key.replace("_", " ").capitalize()
                display_value = "Yes" if value is True else "No" if value is False else value
                lines.append(f"- **{label}:** {display_value}")
            lines.append("")

        if report["qa"].get("warnings"):
            lines.extend(["### ⚠️ QA Warnings", ""])
            lines.extend(f"- {warning}" for warning in report["qa"]["warnings"])
            lines.append("")

        if report["blogger"]["post_url"]:
            lines.extend([
                "### 📝 Blogger Post Status",
                f"- **Post ID:** `{report['blogger']['post_id']}`",
                f"- **Draft URL:** [{report['blogger']['post_url']}]({report['blogger']['post_url']})",
                "",
            ])

        if report.get("research_sources"):
            lines.extend([
                "### 🔍 Research Sources & Evidence Verification",
                "| Source Title | URL | Extraction | HTTP | Verification | Details / Failure Reason |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for src in report["research_sources"]:
                s_title = src.get("title", "Untitled Source")
                s_url = src.get("url", "#")
                s_ext = "Success" if src.get("content_extraction_success") else "Failed"
                s_status = str(src.get("http_status") or "N/A")
                s_ver = "✅ Verified" if src.get("verified") else "❌ Unverified"
                s_reason = src.get("failure_reason") or (
                    f"Supports {len(src.get('verified_claims', []))} claim(s)" if src.get("verified") else "Unverified"
                )
                lines.append(f"| {s_title} | [{s_url}]({s_url}) | {s_ext} | {s_status} | {s_ver} | {s_reason} |")
            lines.append("")

        lines.extend([
            "### 🚦 Pipeline Stages",
            "| Stage | Status | Duration | Details |",
            "| :--- | :--- | :--- | :--- |",
        ])

        for s in report["stages"]:
            st_badge = "✅ PASS" if s["status"] == "SUCCESS" else ("⚠️ SKIP" if s["status"] == "SKIPPED" else "❌ FAIL")
            lines.append(f"| {s['stage']} | {st_badge} | {s['duration_seconds']}s | {s['details'] or '-'} |")

        lines.append("")
        if report["qa"]["failures"]:
            lines.append("### ⛔ QA Gate Hard Failures:")
            for f in report["qa"]["failures"]:
                lines.append(f"- ❌ {f}")
            lines.append("")

        if report["next_action"]:
            lines.extend([
                "### 🎯 Recommended Next Action",
                report["next_action"],
                "",
            ])

        return "\n".join(lines)
