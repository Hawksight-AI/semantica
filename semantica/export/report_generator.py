"""
Report Generator Module

This module provides comprehensive report generation capabilities for the
Semantica framework, enabling formatted reports for analysis results,
quality metrics, and framework statistics.

Key Features:
    - Multiple report formats (HTML, Markdown, JSON, Text)
    - Quality assurance reports
    - Analysis reports
    - Metrics reports
    - Custom report templates
    - Chart/visualization support

Example Usage:
    >>> from semantica.export import ReportGenerator
    >>> generator = ReportGenerator(format="html")
    >>> generator.generate_report(data, "report.html")
    >>> generator.generate_quality_report(metrics, "quality.md", format="markdown")

Author: Semantica Contributors
License: MIT
"""

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.helpers import ensure_directory
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class ReportGenerator:
    """
    Report generator for analysis results and metrics.

    This class provides comprehensive report generation functionality for
    various data types including quality metrics, analysis results, and
    framework statistics.

    Features:
        - Multiple report formats (HTML, Markdown, JSON, Text)
        - Quality assurance reports
        - Analysis reports
        - Metrics reports
        - Custom report templates
        - Chart/visualization support

    Example Usage:
        >>> generator = ReportGenerator(
        ...     format="html",
        ...     include_charts=True
        ... )
        >>> generator.generate_report(data, "report.html")
    """

    def __init__(
        self,
        format: str = "markdown",
        include_charts: bool = False,
        template: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize report generator.

        Sets up the generator with specified format, chart inclusion, and template options.

        Args:
            format: Default report format - 'html', 'markdown', 'json', or 'text'
                   (default: 'markdown')
            include_charts: Whether to include charts/visualizations (default: False)
            template: Custom report template path or identifier (default: None)
            config: Optional configuration dictionary (merged with kwargs)
            **kwargs: Additional configuration options
        """
        self.logger = get_logger("report_generator")
        self.config = config or {}
        self.config.update(kwargs)

        # Report configuration
        self.format = format
        self.include_charts = include_charts
        self.template = template

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug(
            f"Report generator initialized: format={format}, "
            f"include_charts={include_charts}"
        )

    def generate_report(
        self,
        data: Dict[str, Any],
        file_path: Optional[Union[str, Path]] = None,
        format: Optional[str] = None,
        encoding: str = "utf-8",
        **options,
    ) -> Optional[str]:
        """
        Generate report from data.

        This method generates a formatted report from data dictionary in the
        specified format. Can write to file or return as string.

        Supported Formats:
            - "markdown": Markdown format (default)
            - "html": HTML format with styling
            - "json": JSON format
            - "text": Plain text format

        Args:
            data: Report data dictionary containing:
                - title: Report title
                - generated_at: Generation timestamp (optional, auto-added)
                - summary: Summary dictionary or string (optional)
                - metrics: Metrics dictionary (optional)
                - analysis: Analysis results dictionary (optional)
            file_path: Optional output file path. If None, returns report as string.
            format: Report format - 'html', 'markdown', 'json', or 'text'
                   (default: self.format)
            encoding: File encoding (default: 'utf-8')
            **options: Additional format-specific options

        Returns:
            Report string if file_path is None, None if file was written

        Raises:
            ValidationError: If format is unsupported

        Example:
            >>> data = {
            ...     "title": "Analysis Report",
            ...     "metrics": {"total": 100, "success": 95}
            ... }
            >>> # Write to file
            >>> generator.generate_report(data, "report.html", format="html")
            >>> # Get as string
            >>> report = generator.generate_report(data, format="markdown")
        """
        # Track report generation
        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path) if file_path else None,
            module="export",
            submodule="ReportGenerator",
            message=f"Generating {format or self.format} report",
        )

        try:
            report_format = format or self.format

            self.logger.debug(
                f"Generating report ({report_format}): "
                f"title={data.get('title', 'Report')}, "
                f"file_path={file_path}"
            )

            self.progress_tracker.update_tracking(
                tracking_id, message=f"Generating {report_format} report..."
            )
            # Generate report based on format
            if report_format == "markdown":
                report = self._generate_markdown(data, **options)
            elif report_format == "html":
                report = self._generate_html(data, **options)
            elif report_format == "json":
                report = self._generate_json(data, **options)
            elif report_format == "text":
                report = self._generate_text(data, **options)
            else:
                raise ValidationError(
                    f"Unsupported report format: {report_format}. "
                    "Supported formats: markdown, html, json, text"
                )

            # Write to file if path provided
            if file_path:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Writing report to file..."
                )
                file_path = Path(file_path)
                ensure_directory(file_path.parent)

                with open(file_path, "w", encoding=encoding) as f:
                    f.write(report)

                self.logger.info(f"Generated report ({report_format}) to: {file_path}")
                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Generated report ({report_format}) to: {file_path}",
                )
                return None

            # Return report string
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Generated {report_format} report",
            )
            return report

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def generate_quality_report(
        self,
        quality_metrics: Dict[str, Any],
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Optional[str]:
        """
        Generate quality assurance report.

        This method generates a specialized quality assurance report from quality
        metrics, including an automatic summary with overall score and status.

        Args:
            quality_metrics: Quality metrics dictionary containing:
                - score/overall_score: Overall quality score (0-1)
                - completeness: Completeness metric (optional)
                - accuracy: Accuracy metric (optional)
                - consistency: Consistency metric (optional)
                - Additional custom metrics
            file_path: Optional output file path. If None, returns report as string.
            **options: Additional options passed to generate_report()

        Returns:
            Report string if file_path is None, None if file was written

        Example:
            >>> metrics = {
            ...     "score": 0.85,
            ...     "completeness": 0.90,
            ...     "accuracy": 0.80
            ... }
            >>> generator.generate_quality_report(metrics, "quality.html", format="html")
        """
        self.logger.debug("Generating quality assurance report")

        # Build report data with summary
        report_data = {
            "title": "Quality Assurance Report",
            "generated_at": datetime.now().isoformat(),
            "metrics": quality_metrics,
            "summary": self._generate_quality_summary(quality_metrics),
        }

        return self.generate_report(report_data, file_path=file_path, **options)

    def generate_analysis_report(
        self,
        analysis_results: Dict[str, Any],
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Union[str, None]:
        """
        Generate analysis report.

        Args:
            analysis_results: Analysis results dictionary
            file_path: Optional output file path
            **options: Additional options

        Returns:
            Report string if file_path not provided, None otherwise
        """
        report_data = {
            "title": "Analysis Report",
            "generated_at": datetime.now().isoformat(),
            "analysis": analysis_results,
            "summary": self._generate_analysis_summary(analysis_results),
        }

        return self.generate_report(report_data, file_path=file_path, **options)

    def generate_metrics_report(
        self,
        metrics: Dict[str, Any],
        file_path: Optional[Union[str, Path]] = None,
        **options,
    ) -> Union[str, None]:
        """
        Generate metrics report.

        Args:
            metrics: Metrics dictionary
            file_path: Optional output file path
            **options: Additional options

        Returns:
            Report string if file_path not provided, None otherwise
        """
        report_data = {
            "title": "Framework Metrics Report",
            "generated_at": datetime.now().isoformat(),
            "metrics": metrics,
            "summary": self._generate_metrics_summary(metrics),
        }

        return self.generate_report(report_data, file_path=file_path, **options)

    def _generate_markdown(self, data: Dict[str, Any], **options) -> str:
        """Generate Markdown report."""
        lines = []

        # Title
        title = data.get("title", "Report")
        lines.append(f"# {title}")
        lines.append("")

        # Generated at
        if "generated_at" in data:
            lines.append(f"**Generated:** {data['generated_at']}")
            lines.append("")

        # Summary
        if "summary" in data:
            lines.append("## Summary")
            lines.append("")
            summary = data["summary"]
            if isinstance(summary, dict):
                for key, value in summary.items():
                    lines.append(f"- **{key}**: {value}")
            else:
                lines.append(str(summary))
            lines.append("")

        # Metrics
        if "metrics" in data:
            lines.append("## Metrics")
            lines.append("")
            metrics = data["metrics"]
            self._add_dict_to_markdown(metrics, lines, level=2)

        # Analysis
        if "analysis" in data:
            lines.append("## Analysis")
            lines.append("")
            analysis = data["analysis"]
            self._add_dict_to_markdown(analysis, lines, level=2)

        return "\n".join(lines)

    def _generate_html(self, data: Dict[str, Any], **options) -> str:
        """Generate HTML report."""
        lines = ["<!DOCTYPE html>"]
        lines.append('<html lang="en">')
        lines.append("<head>")
        lines.append('  <meta charset="UTF-8">')
        lines.append(
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">'
        )
        title = data.get("title", "Report")
        lines.append(f"  <title>{html.escape(str(title))}</title>")
        lines.append("  <style>")
        lines.append("    body { font-family: Arial, sans-serif; margin: 20px; }")
        lines.append("    h1 { color: #333; }")
        lines.append("    h2 { color: #666; margin-top: 30px; }")
        lines.append(
            "    table { border-collapse: collapse; width: 100%; margin: 20px 0; }"
        )
        lines.append(
            "    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }"
        )
        lines.append("    th { background-color: #f2f2f2; }")
        lines.append("  </style>")
        lines.append("</head>")
        lines.append("<body>")

        # Title
        title = data.get("title", "Report")
        lines.append(f"  <h1>{html.escape(str(title))}</h1>")

        # Generated at
        if "generated_at" in data:
            lines.append(
                f'  <p><strong>Generated:</strong> '
                f'{html.escape(str(data["generated_at"]))}</p>'
            )

        # Summary
        if "summary" in data:
            lines.append("  <h2>Summary</h2>")
            summary = data["summary"]
            if isinstance(summary, dict):
                lines.append("  <ul>")
                for key, value in summary.items():
                    lines.append(
                        f"    <li><strong>{html.escape(str(key))}:</strong> "
                        f"{html.escape(str(value))}</li>"
                    )
                lines.append("  </ul>")
            else:
                lines.append(f"  <p>{html.escape(str(summary))}</p>")

        # Metrics
        if "metrics" in data:
            lines.append("  <h2>Metrics</h2>")
            metrics = data["metrics"]
            self._add_dict_to_html(metrics, lines)

        lines.append("</body>")
        lines.append("</html>")

        return "\n".join(lines)

    def _generate_json(self, data: Dict[str, Any], **options) -> str:
        """Generate JSON report."""
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _generate_text(self, data: Dict[str, Any], **options) -> str:
        """Generate plain text report."""
        lines = []

        # Title
        title = data.get("title", "Report")
        lines.append("=" * 60)
        lines.append(title)
        lines.append("=" * 60)
        lines.append("")

        # Generated at
        if "generated_at" in data:
            lines.append(f"Generated: {data['generated_at']}")
            lines.append("")

        # Summary
        if "summary" in data:
            lines.append("SUMMARY")
            lines.append("-" * 60)
            summary = data["summary"]
            if isinstance(summary, dict):
                for key, value in summary.items():
                    lines.append(f"  {key}: {value}")
            else:
                lines.append(str(summary))
            lines.append("")

        # Metrics
        if "metrics" in data:
            lines.append("METRICS")
            lines.append("-" * 60)
            metrics = data["metrics"]
            self._add_dict_to_text(metrics, lines, indent=2)

        return "\n".join(lines)

    def _add_dict_to_markdown(
        self, data: Dict[str, Any], lines: List[str], level: int = 2
    ) -> None:
        """Add dictionary to markdown."""
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{'#' * level} {key}")
                lines.append("")
                self._add_dict_to_markdown(value, lines, level + 1)
            elif isinstance(value, list):
                lines.append(f"**{key}:**")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(
                            "- " + ", ".join(f"{k}: {v}" for k, v in item.items())
                        )
                    else:
                        lines.append(f"- {item}")
                lines.append("")
            else:
                lines.append(f"- **{key}**: {value}")

    def _add_dict_to_html(self, data: Dict[str, Any], lines: List[str]) -> None:
        """Add dictionary to HTML."""
        lines.append("  <table>")
        lines.append("    <tr><th>Key</th><th>Value</th></tr>")

        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, indent=2)
            else:
                value_str = str(value)

            lines.append(
                f"    <tr><td>{html.escape(str(key))}</td>"
                f"<td>{html.escape(value_str)}</td></tr>"
            )

        lines.append("  </table>")

    def _add_dict_to_text(
        self, data: Dict[str, Any], lines: List[str], indent: int = 0
    ) -> None:
        """Add dictionary to text."""
        prefix = " " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                self._add_dict_to_text(value, lines, indent + 2)
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        item_str = ", ".join(f"{k}={v}" for k, v in item.items())
                        lines.append(f"{prefix}  - {item_str}")
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")

    def _generate_quality_summary(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate quality summary from metrics.

        This method creates a summary dictionary from quality metrics including
        overall score, status (PASS/FAIL), and key quality dimensions.

        Args:
            metrics: Quality metrics dictionary

        Returns:
            Dictionary with summary information:
                - Overall Score: Formatted score (0.00-1.00)
                - Status: "PASS" if score >= 0.7, "FAIL" otherwise
                - Completeness: Completeness metric or "N/A"
                - Accuracy: Accuracy metric or "N/A"
                - Consistency: Consistency metric or "N/A"
        """
        score = metrics.get("score") or metrics.get("overall_score", 0.0)

        return {
            "Overall Score": f"{score:.2f}",
            "Status": "PASS" if score >= 0.7 else "FAIL",
            "Completeness": metrics.get("completeness", "N/A"),
            "Accuracy": metrics.get("accuracy", "N/A"),
            "Consistency": metrics.get("consistency", "N/A"),
        }

    def _generate_analysis_summary(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate analysis summary."""
        return {
            "Analysis Type": analysis.get("type", "Unknown"),
            "Items Analyzed": analysis.get("total_count", 0),
            "Status": analysis.get("status", "Completed"),
        }

    def _generate_metrics_summary(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate metrics summary."""
        return {
            "Total Items": metrics.get("total_items", 0),
            "Success Rate": f"{metrics.get('success_rate', 0.0):.2%}",
            "Average Confidence": f"{metrics.get('average_confidence', 0.0):.2f}",
        }
