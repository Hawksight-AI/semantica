"""
Email Content Parsing Module

This module handles parsing of email content and metadata, including headers,
MIME messages, body content, attachments, and email thread analysis.

Key Features:
    - Email header parsing (From, To, CC, BCC, Subject, Date)
    - MIME message processing
    - Email body content extraction (plain text, HTML)
    - Attachment handling
    - Email thread analysis
    - Encoded header decoding
    - Multi-part message processing

Main Classes:
    - EmailParser: Main email parsing class
    - MIMEParser: MIME message parser
    - EmailThreadAnalyzer: Email thread processor
    - EmailHeaders: Dataclass for email headers
    - EmailBody: Dataclass for email body content
    - EmailData: Dataclass for complete email data

Example Usage:
    >>> from semantica.parse import EmailParser
    >>> parser = EmailParser()
    >>> email_data = parser.parse("email.eml")
    >>> headers = parser.parse_headers("email.eml")
    >>> thread = parser.analyze_thread("email.eml")

Author: Semantica Contributors
License: MIT
"""

import email
import email.message
from dataclasses import dataclass, field
from email import message_from_bytes, message_from_string
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class EmailHeaders:
    """Email headers representation."""

    subject: Optional[str] = None
    from_address: Optional[str] = None
    to_addresses: List[str] = field(default_factory=list)
    cc_addresses: List[str] = field(default_factory=list)
    bcc_addresses: List[str] = field(default_factory=list)
    date: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: List[str] = field(default_factory=list)
    custom_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class EmailBody:
    """Email body representation."""

    text: Optional[str] = None
    html: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EmailData:
    """Email data representation."""

    headers: EmailHeaders
    body: EmailBody
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmailParser:
    """
    Email content parsing handler.

    • Parses email messages and metadata
    • Extracts headers and body content
    • Processes MIME multipart messages
    • Handles email attachments
    • Analyzes email threads and conversations
    • Supports various email formats
    """

    def __init__(self, config=None, **kwargs):
        """Initialize email parser."""
        self.logger = get_logger("email_parser")
        self.config = config or {}
        self.config.update(kwargs)

        self.mime_parser = MIMEParser(**self.config.get("mime", {}))
        self.thread_analyzer = EmailThreadAnalyzer(**self.config.get("thread", {}))
        self.progress_tracker = get_progress_tracker()

    def parse_email(
        self, email_content: Union[str, bytes, Path], **options
    ) -> EmailData:
        """
        Parse email message content.

        Args:
            email_content: Email content (string, bytes, or file path)
            **options: Parsing options:
                - extract_attachments: Whether to extract attachments (default: True)

        Returns:
            EmailData: Parsed email data
        """
        # Track email parsing
        file_path = None
        if isinstance(email_content, Path) or (
            isinstance(email_content, str) and Path(email_content).exists()
        ):
            file_path = Path(email_content)

        tracking_id = self.progress_tracker.start_tracking(
            file=str(file_path) if file_path else None,
            module="parse",
            submodule="EmailParser",
            message=f"Email: {file_path.name if file_path else 'content'}",
        )

        try:
            # Load email content
            if file_path:
                if not file_path.exists():
                    raise ValidationError(f"Email file not found: {file_path}")

                with open(file_path, "rb") as f:
                    email_bytes = f.read()
                email_msg = message_from_bytes(email_bytes)
            elif isinstance(email_content, bytes):
                email_msg = message_from_bytes(email_content)
            else:
                email_msg = message_from_string(email_content)

            try:
                # Extract headers
                headers = self.extract_headers(email_msg)

                # Extract body
                body = self.extract_body(
                    email_msg,
                    extract_attachments=options.get("extract_attachments", True),
                )

                self.progress_tracker.stop_tracking(
                    tracking_id,
                    status="completed",
                    message=f"Parsed email: {headers.subject or 'No subject'}",
                )
                return EmailData(
                    headers=headers,
                    body=body,
                    metadata={"message_id": headers.message_id, "date": headers.date},
                )

            except Exception as e:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                self.logger.error(f"Failed to parse email: {e}")
                raise ProcessingError(f"Failed to parse email: {e}")

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def extract_headers(self, email_message: email.message.Message) -> EmailHeaders:
        """
        Extract email headers and metadata.

        Args:
            email_message: Email message object

        Returns:
            EmailHeaders: Extracted headers
        """

        def decode_header_value(value):
            """Decode email header value."""
            if value is None:
                return None

            decoded_parts = decode_header(value)
            decoded_str = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    decoded_str += part.decode(encoding or "utf-8", errors="ignore")
                else:
                    decoded_str += part
            return decoded_str.strip()

        headers = EmailHeaders()

        # Extract standard headers
        headers.subject = decode_header_value(email_message.get("Subject"))
        headers.from_address = decode_header_value(email_message.get("From"))

        # Extract recipients
        to_header = email_message.get("To", "")
        if to_header:
            headers.to_addresses = [addr.strip() for addr in str(to_header).split(",")]

        cc_header = email_message.get("Cc", "")
        if cc_header:
            headers.cc_addresses = [addr.strip() for addr in str(cc_header).split(",")]

        bcc_header = email_message.get("Bcc", "")
        if bcc_header:
            headers.bcc_addresses = [
                addr.strip() for addr in str(bcc_header).split(",")
            ]

        # Extract dates
        date_str = email_message.get("Date")
        if date_str:
            try:
                date_obj = parsedate_to_datetime(date_str)
                headers.date = date_obj.isoformat() if date_obj else str(date_str)
            except Exception:
                headers.date = str(date_str)

        # Extract message IDs
        headers.message_id = email_message.get("Message-ID")
        headers.in_reply_to = email_message.get("In-Reply-To")

        # Extract references
        references = email_message.get("References", "")
        if references:
            headers.references = [ref.strip() for ref in str(references).split()]

        # Extract custom headers
        for header_name, header_value in email_message.items():
            if header_name not in [
                "Subject",
                "From",
                "To",
                "Cc",
                "Bcc",
                "Date",
                "Message-ID",
                "In-Reply-To",
                "References",
            ]:
                headers.custom_headers[header_name] = decode_header_value(header_value)

        return headers

    def extract_body(
        self, email_message: email.message.Message, extract_attachments: bool = True
    ) -> EmailBody:
        """
        Extract email body content.

        Args:
            email_message: Email message object
            extract_attachments: Whether to extract attachments

        Returns:
            EmailBody: Extracted body content
        """
        body = EmailBody()

        # Process MIME message
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = part.get("Content-Disposition", "")

                # Check if it's an attachment
                if "attachment" in content_disposition and extract_attachments:
                    attachment = self._extract_attachment(part)
                    if attachment:
                        body.attachments.append(attachment)

                # Extract text content
                elif content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body.text = payload.decode(charset, errors="ignore")

                # Extract HTML content
                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body.html = payload.decode(charset, errors="ignore")
        else:
            # Single part message
            content_type = email_message.get_content_type()
            payload = email_message.get_payload(decode=True)

            if payload:
                charset = email_message.get_content_charset() or "utf-8"
                if content_type == "text/html":
                    body.html = payload.decode(charset, errors="ignore")
                else:
                    body.text = payload.decode(charset, errors="ignore")

        return body

    def _extract_attachment(
        self, part: email.message.Message
    ) -> Optional[Dict[str, Any]]:
        """Extract attachment from email part."""
        try:
            filename = part.get_filename()
            if not filename:
                return None

            # Decode filename
            decoded_parts = decode_header(filename)
            decoded_filename = ""
            for part_bytes, encoding in decoded_parts:
                if isinstance(part_bytes, bytes):
                    decoded_filename += part_bytes.decode(
                        encoding or "utf-8", errors="ignore"
                    )
                else:
                    decoded_filename += part_bytes

            payload = part.get_payload(decode=True)

            return {
                "filename": decoded_filename,
                "content_type": part.get_content_type(),
                "size": len(payload) if payload else 0,
                "data": payload,
            }
        except Exception as e:
            self.logger.warning(f"Failed to extract attachment: {e}")
            return None

    def analyze_thread(self, emails: List[EmailData]) -> Dict[str, Any]:
        """
        Analyze email thread structure.

        Args:
            emails: List of email data objects

        Returns:
            dict: Thread analysis
        """
        return self.thread_analyzer.analyze_thread(emails)


class MIMEParser:
    """MIME message parsing engine."""

    def __init__(self, **config):
        """Initialize MIME parser."""
        self.logger = get_logger("mime_parser")
        self.config = config

    def parse_mime_message(
        self, message_content: Union[str, bytes]
    ) -> email.message.Message:
        """
        Parse MIME message structure.

        Args:
            message_content: MIME message content

        Returns:
            Email message object
        """
        if isinstance(message_content, bytes):
            return message_from_bytes(message_content)
        else:
            return message_from_string(message_content)


class EmailThreadAnalyzer:
    """Email thread analysis engine."""

    def __init__(self, **config):
        """Initialize email thread analyzer."""
        self.logger = get_logger("email_thread_analyzer")
        self.config = config

    def analyze_thread(self, emails: List[EmailData]) -> Dict[str, Any]:
        """
        Analyze email thread structure.

        Args:
            emails: List of email data objects

        Returns:
            dict: Thread analysis
        """
        analysis = {
            "thread_count": len(emails),
            "participants": set(),
            "messages_by_date": {},
            "reply_chains": [],
        }

        # Extract participants
        for email_data in emails:
            if email_data.headers.from_address:
                analysis["participants"].add(email_data.headers.from_address)
            analysis["participants"].update(email_data.headers.to_addresses)
            analysis["participants"].update(email_data.headers.cc_addresses)

        analysis["participants"] = list(analysis["participants"])

        # Group by date
        for email_data in emails:
            if email_data.headers.date:
                date_key = (
                    email_data.headers.date[:10]
                    if len(email_data.headers.date) >= 10
                    else email_data.headers.date
                )
                if date_key not in analysis["messages_by_date"]:
                    analysis["messages_by_date"][date_key] = []
                analysis["messages_by_date"][date_key].append(
                    email_data.headers.message_id
                )

        # Identify reply chains
        for email_data in emails:
            if email_data.headers.in_reply_to:
                analysis["reply_chains"].append(
                    {
                        "message_id": email_data.headers.message_id,
                        "in_reply_to": email_data.headers.in_reply_to,
                    }
                )

        return analysis
