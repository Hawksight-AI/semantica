"""
Email Ingestion Module

This module provides comprehensive email ingestion capabilities for the
Semantica framework, enabling email retrieval, parsing, and content extraction
from various email protocols.

Key Features:
    - IMAP/POP3 email retrieval with secure connections
    - Email content parsing (plain text and HTML)
    - Attachment processing and extraction
    - Email metadata extraction (headers, dates, addresses)
    - Thread analysis and conversation grouping
    - Link extraction from email content

Main Classes:
    - EmailIngestor: Main email ingestion class
    - EmailParser: Email content parser
    - AttachmentProcessor: Email attachment handler

Example Usage:
    >>> from semantica.ingest import EmailIngestor
    >>> ingestor = EmailIngestor()
    >>> ingestor.connect_imap("imap.example.com", username="user", password="pass")
    >>> emails = ingestor.ingest_mailbox("INBOX", max_emails=100)
    >>> threads = ingestor.analyze_threads(emails)

Author: Semantica Contributors
License: MIT
"""

import email
import imaplib
import poplib
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


@dataclass
class EmailData:
    """
    Email data representation.

    This dataclass represents a structured email message with all relevant
    metadata, content, and attachments.

    Attributes:
        message_id: Unique message identifier
        subject: Email subject line
        from_address: Sender email address
        to_addresses: List of recipient email addresses
        cc_addresses: List of CC recipient email addresses
        date: Email date/time (optional)
        body_text: Plain text email body
        body_html: HTML email body
        attachments: List of attachment information dictionaries
        headers: Dictionary of email headers
        thread_id: Thread/conversation identifier (optional)
    """

    message_id: str
    subject: str
    from_address: str
    to_addresses: List[str]
    cc_addresses: List[str] = field(default_factory=list)
    date: Optional[datetime] = None
    body_text: str = ""
    body_html: str = ""
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    thread_id: Optional[str] = None


class AttachmentProcessor:
    """
    Email attachment processing and extraction.

    This class processes various email attachment types, extracts text content
    from documents, and handles image and media attachments. Creates temporary
    files for processing and provides cleanup functionality.

    Example Usage:
        >>> processor = AttachmentProcessor()
        >>> info = processor.process_attachment(data, "document.pdf", "application/pdf")
        >>> processor.cleanup_attachments([info["saved_path"]])
    """

    def __init__(self, **config):
        """
        Initialize attachment processor.

        Sets up the processor with configuration and creates a temporary
        directory for storing attachments.

        Args:
            **config: Processor configuration options (currently unused)
        """
        self.logger = get_logger("attachment_processor")
        self.config = config
        self.temp_dir = tempfile.mkdtemp(prefix="semantica_attachments_")
        self.logger.debug(f"Attachment processor initialized: temp_dir={self.temp_dir}")

    def process_attachment(
        self, attachment_data: bytes, filename: str, content_type: str
    ) -> Dict[str, Any]:
        """
        Process individual email attachment.

        This method saves the attachment to a temporary file, extracts text
        content if applicable (for text files and documents), and returns
        comprehensive attachment information.

        Args:
            attachment_data: Attachment content as bytes
            filename: Original attachment filename
            content_type: MIME content type (e.g., "application/pdf", "text/plain")

        Returns:
            dict: Attachment information dictionary containing:
                - filename: Original filename
                - content_type: MIME content type
                - size: File size in bytes
                - saved_path: Path to saved temporary file (or None if save failed)
                - text_content: Extracted text content (or None if not applicable)
        """
        attachment_info = {
            "filename": filename,
            "content_type": content_type,
            "size": len(attachment_data),
            "saved_path": None,
            "text_content": None,
        }

        # Save attachment to temporary file
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ".-_")
        file_path = Path(self.temp_dir) / safe_filename

        try:
            with open(file_path, "wb") as f:
                f.write(attachment_data)
            attachment_info["saved_path"] = str(file_path)
        except Exception as e:
            self.logger.error(f"Failed to save attachment {filename}: {e}")
            return attachment_info

        # Extract text content if applicable
        if content_type.startswith("text/"):
            try:
                text_content = attachment_data.decode("utf-8", errors="ignore")
                attachment_info["text_content"] = text_content
            except Exception:
                pass
        elif content_type in [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]:
            # Extract text from documents
            text_content = self.extract_text_content(file_path, content_type)
            attachment_info["text_content"] = text_content

        return attachment_info

    def extract_text_content(
        self, attachment_path: Path, file_type: str
    ) -> Optional[str]:
        """
        Extract text content from attachment.

        This method attempts to extract text content from various document
        types. Currently supports plain text files. PDF and Word document
        extraction would require additional libraries (pdfplumber for
        PDF, python-docx for Word).

        Args:
            attachment_path: Path to attachment file
            file_type: File MIME type (e.g., "application/pdf", "text/plain")

        Returns:
            str: Extracted text content, or None if extraction is not supported
                 or fails
        """
        try:
            if file_type == "application/pdf":
                # PDF text extraction would require pdfplumber
                self.logger.debug(
                    "PDF text extraction not implemented (requires pdfplumber)"
                )
                return None
            elif file_type in [
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]:
                # Word document extraction would require python-docx
                self.logger.debug(
                    "Word document extraction not implemented (requires python-docx)"
                )
                return None
            elif file_type.startswith("text/"):
                with open(attachment_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    self.logger.debug(
                        f"Extracted {len(content)} characters from text file"
                    )
                    return content
        except Exception as e:
            self.logger.error(f"Failed to extract text from {attachment_path}: {e}")

        return None

    def cleanup_attachments(self, attachment_paths: Optional[List[str]] = None):
        """
        Clean up temporary attachment files.

        This method removes the temporary directory and all files within it.
        The attachment_paths parameter is currently unused but reserved for
        selective cleanup in the future.

        Args:
            attachment_paths: List of attachment file paths (optional, currently
                             unused - entire temp directory is cleaned)
        """
        import shutil

        try:
            if Path(self.temp_dir).exists():
                shutil.rmtree(self.temp_dir)
                self.logger.debug(f"Cleaned up attachment directory: {self.temp_dir}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup attachments: {e}")


class EmailParser:
    """
    Email content parsing and extraction.

    This class parses email headers and metadata, extracts email body content
    from both plain text and HTML parts, handles MIME multipart messages, and
    extracts links from email content.

    Example Usage:
        >>> parser = EmailParser()
        >>> headers = parser.parse_headers(email_message)
        >>> body = parser.parse_body(email_message)
        >>> links = parser.extract_links(body["html"])
    """

    def __init__(self, **config):
        """
        Initialize email parser.

        Sets up the parser with configuration options.

        Args:
            **config: Parser configuration options (currently unused)
        """
        self.logger = get_logger("email_parser")
        self.config = config

    def parse_headers(self, email_message: email.message.Message) -> Dict[str, str]:
        """
        Parse email headers and metadata.

        This method extracts all email headers, decodes them if necessary
        (handling encoded headers with character sets), and returns them as
        a dictionary with lowercase keys.

        Args:
            email_message: Email message object from email library

        Returns:
            dict: Dictionary mapping header names (lowercase) to decoded
                  header values
        """
        headers = {}

        for header_name in email_message.keys():
            header_value = email_message[header_name]
            if header_value:
                # Decode header if needed
                decoded_value = decode_header(header_value)
                decoded_str = "".join(
                    part[0].decode(part[1] or "utf-8")
                    if isinstance(part[0], bytes)
                    else part[0]
                    for part in decoded_value
                )
                headers[header_name.lower()] = decoded_str

        return headers

    def parse_body(self, email_message: email.message.Message) -> Dict[str, str]:
        """
        Parse email body content.

        This method extracts both plain text and HTML content from email
        messages, handling both multipart and single-part messages. Skips
        attachment parts when extracting body content.

        Args:
            email_message: Email message object from email library

        Returns:
            dict: Body content dictionary with:
                - text: Plain text email body (empty string if not available)
                - html: HTML email body (empty string if not available)
        """
        body = {"text": "", "html": ""}

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                # Extract text content
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body["text"] = payload.decode(charset, errors="ignore")
                    except Exception as e:
                        self.logger.warning(f"Failed to decode text part: {e}")

                # Extract HTML content
                elif content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body["html"] = payload.decode(charset, errors="ignore")
                    except Exception as e:
                        self.logger.warning(f"Failed to decode HTML part: {e}")
        else:
            # Single part message
            content_type = email_message.get_content_type()
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    charset = email_message.get_content_charset() or "utf-8"
                    decoded = payload.decode(charset, errors="ignore")

                    if content_type == "text/html":
                        body["html"] = decoded
                    else:
                        body["text"] = decoded
            except Exception as e:
                self.logger.warning(f"Failed to decode body: {e}")

        return body

    def extract_links(self, email_content: str) -> List[str]:
        """
        Extract links from email content.

        This method extracts URLs from email content, supporting both HTML
        (extracts href attributes from anchor tags) and plain text (uses
        regex pattern matching). Removes duplicate URLs.

        Args:
            email_content: Email content (HTML or plain text)

        Returns:
            list: List of unique extracted URLs
        """
        links = []

        # Extract from HTML if available
        if email_content.strip().startswith("<"):
            try:
                soup = BeautifulSoup(email_content, "html.parser")
                for link_tag in soup.find_all("a", href=True):
                    links.append(link_tag["href"])
            except Exception:
                pass

        # Extract URLs from text using regex
        import re

        url_pattern = r"https?://(?:[a-zA-Z0-9\-._~!$&'()*+,;=:@/?#\[\]]|%[0-9a-fA-F]{2})+"
        text_links = re.findall(url_pattern, email_content)
        links.extend(text_links)

        # Remove duplicates
        return list(set(links))


class EmailIngestor:
    """
    Email protocol ingestion handler.

    This class provides comprehensive email ingestion capabilities, connecting
    to email servers via IMAP/POP3, retrieving emails from mailboxes, and
    processing email content and attachments.

    Features:
        - IMAP and POP3 protocol support
        - Secure connections (SSL/TLS)
        - Email filtering and pagination
        - Thread analysis
        - Attachment extraction

    Example Usage:
        >>> ingestor = EmailIngestor()
        >>> ingestor.connect_imap("imap.example.com", username="user", password="pass")
        >>> emails = ingestor.ingest_mailbox("INBOX", max_emails=100, unread_only=True)
        >>> threads = ingestor.analyze_threads(emails)
        >>> ingestor.disconnect()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize email ingestor.

        Sets up the ingestor with email parser and attachment processor.
        Connection to email servers must be established separately using
        connect_imap() or connect_pop3().

        Args:
            config: Optional email ingestion configuration dictionary
            **kwargs: Additional configuration parameters (merged into config)
        """
        self.logger = get_logger("email_ingestor")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize parser
        self.parser = EmailParser(**self.config)

        # Initialize attachment processor
        self.attachment_processor = AttachmentProcessor(**self.config)

        # Connection objects (initialized on connect)
        self.imap_client: Optional[imaplib.IMAP4_SSL] = None
        self.pop3_client: Optional[poplib.POP3_SSL] = None

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        self.logger.debug("Email ingestor initialized")

    def connect_imap(
        self,
        server: str,
        port: int = 993,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Connect to IMAP server.

        This method establishes a secure SSL connection to an IMAP server and
        authenticates with the provided credentials. The connection is stored
        for use in subsequent operations.

        Args:
            server: IMAP server address (hostname or IP)
            port: IMAP server port (default: 993 for SSL)
            username: Email username (optional, can be provided later)
            password: Email password (optional, can be provided later)

        Raises:
            ProcessingError: If connection or authentication fails
        """
        try:
            self.imap_client = imaplib.IMAP4_SSL(server, port)
            if username and password:
                self.imap_client.login(username, password)
                self.logger.info(
                    f"Connected and authenticated to IMAP server: {server}:{port}"
                )
            else:
                self.logger.info(
                    f"Connected to IMAP server: {server}:{port} (not authenticated)"
                )
        except Exception as e:
            self.logger.error(f"Failed to connect to IMAP: {e}")
            raise ProcessingError(f"Failed to connect to IMAP server: {e}") from e

    def connect_pop3(
        self,
        server: str,
        port: int = 995,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Connect to POP3 server.

        This method establishes a secure SSL connection to a POP3 server and
        authenticates with the provided credentials. The connection is stored
        for use in subsequent operations.

        Args:
            server: POP3 server address (hostname or IP)
            port: POP3 server port (default: 995 for SSL)
            username: Email username (optional, can be provided later)
            password: Email password (optional, can be provided later)

        Raises:
            ProcessingError: If connection or authentication fails
        """
        try:
            self.pop3_client = poplib.POP3_SSL(server, port)
            if username and password:
                self.pop3_client.user(username)
                self.pop3_client.pass_(password)
                self.logger.info(
                    f"Connected and authenticated to POP3 server: {server}:{port}"
                )
            else:
                self.logger.info(
                    f"Connected to POP3 server: {server}:{port} (not authenticated)"
                )
        except Exception as e:
            self.logger.error(f"Failed to connect to POP3: {e}")
            raise ProcessingError(f"Failed to connect to POP3 server: {e}") from e

    def ingest_mailbox(
        self,
        mailbox_name: str = "INBOX",
        protocol: str = "imap",
        since: Optional[str] = None,
        max_emails: Optional[int] = None,
        unread_only: bool = False,
        **filters,
    ) -> List[EmailData]:
        """
        Ingest emails from specified mailbox.

        This method retrieves emails from a mailbox using the specified
        protocol (IMAP or POP3), applies optional filters, and returns
        processed email data.

        Args:
            mailbox_name: Mailbox name (default: "INBOX", IMAP only)
            protocol: Protocol to use ("imap" or "pop3", default: "imap")
            since: Date to start from (IMAP only, format: "DD-MMM-YYYY")
            max_emails: Maximum number of emails to retrieve (optional)
            unread_only: Only fetch unread emails (IMAP only, default: False)
            **filters: Additional filtering criteria (merged with above)

        Returns:
            list: List of EmailData objects representing processed emails

        Raises:
            ProcessingError: If protocol is unsupported or client not connected
            ValidationError: If protocol is invalid
        """
        # Merge explicit parameters with filters
        merged_filters = {
            "since": since or filters.get("since"),
            "max_emails": max_emails or filters.get("max_emails"),
            "unread_only": unread_only or filters.get("unread_only", False),
        }
        # Remove None values
        merged_filters = {k: v for k, v in merged_filters.items() if v is not None}

        if protocol.lower() == "imap":
            if not self.imap_client:
                raise ProcessingError(
                    "IMAP client not connected. Call connect_imap() first."
                )
            return self._ingest_imap(mailbox_name, **merged_filters)
        elif protocol.lower() == "pop3":
            if not self.pop3_client:
                raise ProcessingError(
                    "POP3 client not connected. Call connect_pop3() first."
                )
            return self._ingest_pop3(**merged_filters)
        else:
            raise ValidationError(
                f"Unsupported protocol: {protocol}. Supported: 'imap', 'pop3'"
            )

    def _ingest_imap(self, mailbox_name: str, **filters) -> List[EmailData]:
        """
        Ingest emails using IMAP protocol.

        This private method handles IMAP-specific email retrieval, including
        mailbox selection, search criteria building, and email fetching.

        Args:
            mailbox_name: Name of the mailbox to access
            **filters: Email filtering criteria (since, max_emails, unread_only)

        Returns:
            list: List of EmailData objects

        Raises:
            ProcessingError: If mailbox access or email retrieval fails
        """
        try:
            # Select mailbox
            self.imap_client.select(mailbox_name)

            # Build search criteria
            search_criteria = "ALL"
            if filters.get("unread_only"):
                search_criteria = "UNSEEN"
            if filters.get("since"):
                search_criteria = f"({search_criteria} SINCE {filters['since']})"

            # Search for emails
            status, message_ids = self.imap_client.search(None, search_criteria)

            if status != "OK":
                raise ProcessingError("Failed to search emails")

            email_ids = message_ids[0].split()

            # Limit number of emails
            max_emails = filters.get("max_emails")
            if max_emails:
                email_ids = email_ids[-max_emails:]  # Get most recent

            emails = []
            for email_id in email_ids:
                try:
                    status, msg_data = self.imap_client.fetch(email_id, "(RFC822)")
                    if status == "OK":
                        email_message = email.message_from_bytes(msg_data[0][1])
                        email_data = self.process_email(email_message)
                        emails.append(email_data)
                except Exception as e:
                    self.logger.error(f"Failed to process email {email_id}: {e}")

            return emails

        except Exception as e:
            self.logger.error(f"Error ingesting IMAP mailbox: {e}")
            raise ProcessingError(f"Failed to ingest mailbox: {e}")

    def _ingest_pop3(self, **filters) -> List[EmailData]:
        """
        Ingest emails using POP3 protocol.

        This private method handles POP3-specific email retrieval. POP3 does
        not support mailbox selection or advanced filtering like IMAP.

        Args:
            **filters: Email filtering criteria (max_emails supported)

        Returns:
            list: List of EmailData objects

        Raises:
            ProcessingError: If email retrieval fails
        """
        try:
            # Get email list
            num_messages = len(self.pop3_client.list()[1])

            max_emails = filters.get("max_emails", num_messages)
            emails = []

            # Fetch emails (most recent first)
            start = max(1, num_messages - max_emails + 1)
            for i in range(start, num_messages + 1):
                try:
                    response = self.pop3_client.retr(i)
                    email_content = b"\n".join(response[1])
                    email_message = email.message_from_bytes(email_content)
                    email_data = self.process_email(email_message)
                    emails.append(email_data)
                except Exception as e:
                    self.logger.error(f"Failed to process email {i}: {e}")

            return emails

        except Exception as e:
            self.logger.error(f"Error ingesting POP3: {e}")
            raise ProcessingError(f"Failed to ingest POP3: {e}")

    def process_email(self, email_message: email.message.Message) -> EmailData:
        """
        Process individual email message.

        This method extracts all relevant information from an email message,
        including headers, body content, attachments, and thread information.

        Args:
            email_message: Email message object from email library

        Returns:
            EmailData: Structured email data object with all extracted
                      information
        """
        # Parse headers
        headers = self.parser.parse_headers(email_message)

        # Extract basic information
        message_id = headers.get("message-id", "")
        subject = headers.get("subject", "")
        from_address = headers.get("from", "")
        to_addresses = self._parse_address_list(headers.get("to", ""))
        cc_addresses = self._parse_address_list(headers.get("cc", ""))

        # Parse date
        date_str = headers.get("date", "")
        email_date = None
        if date_str:
            try:
                from email.utils import parsedate_to_datetime

                email_date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        # Parse body
        body = self.parser.parse_body(email_message)

        # Extract thread ID
        thread_id = (
            headers.get("in-reply-to") or headers.get("references", "").split()[0]
            if headers.get("references")
            else None
        )

        # Extract attachments
        attachments = self.extract_attachments(email_message)

        return EmailData(
            message_id=message_id,
            subject=subject,
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            date=email_date,
            body_text=body["text"],
            body_html=body["html"],
            attachments=attachments,
            headers=headers,
            thread_id=thread_id,
        )

    def extract_attachments(
        self, email_message: email.message.Message
    ) -> List[Dict[str, Any]]:
        """
        Extract and process email attachments.

        This method walks through the email message parts, identifies
        attachments (based on Content-Disposition header), decodes filenames,
        and processes each attachment using the attachment processor.

        Args:
            email_message: Email message object from email library

        Returns:
            list: List of attachment information dictionaries, each containing:
                - filename: Attachment filename
                - content_type: MIME content type
                - size: File size in bytes
                - saved_path: Path to saved temporary file
                - text_content: Extracted text content (if applicable)
        """
        attachments = []

        if email_message.is_multipart():
            for part in email_message.walk():
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        # Decode filename
                        decoded_filename = decode_header(filename)[0][0]
                        if isinstance(decoded_filename, bytes):
                            decoded_filename = decoded_filename.decode(
                                "utf-8", errors="ignore"
                            )

                        # Get attachment data
                        attachment_data = part.get_payload(decode=True)
                        content_type = part.get_content_type()

                        # Process attachment
                        attachment_info = self.attachment_processor.process_attachment(
                            attachment_data, decoded_filename, content_type
                        )
                        attachments.append(attachment_info)

        return attachments

    def analyze_threads(self, emails: List[EmailData]) -> Dict[str, Any]:
        """
        Analyze email threads and conversations.

        This method groups emails into threads based on thread IDs (from
        In-Reply-To or References headers) or message IDs, and analyzes
        thread characteristics including participants and message counts.

        Args:
            emails: List of EmailData objects to analyze

        Returns:
            dict: Thread analysis dictionary containing:
                - total_threads: Total number of unique threads
                - threads: List of thread dictionaries, each containing:
                    - thread_id: Thread identifier
                    - emails: List of emails in the thread
                    - participants: List of participant email addresses
                    - subject: Thread subject (from first email)
                    - message_count: Number of messages in thread
        """
        threads = {}

        for email_data in emails:
            thread_id = email_data.thread_id or email_data.message_id

            if thread_id not in threads:
                threads[thread_id] = {
                    "thread_id": thread_id,
                    "emails": [],
                    "participants": set(),
                    "subject": email_data.subject,
                    "message_count": 0,
                }

            threads[thread_id]["emails"].append(email_data)
            threads[thread_id]["participants"].add(email_data.from_address)
            threads[thread_id]["participants"].update(email_data.to_addresses)
            threads[thread_id]["message_count"] += 1

        # Convert sets to lists for JSON serialization
        for thread in threads.values():
            thread["participants"] = list(thread["participants"])

        return {"total_threads": len(threads), "threads": list(threads.values())}

    def _parse_address_list(self, address_string: str) -> List[str]:
        """
        Parse email address list string into list of addresses.

        This private method parses email address strings (which may contain
        multiple addresses in various formats) into a list of email addresses.
        Uses email.utils for proper parsing, with regex fallback.

        Args:
            address_string: Email address string (may contain multiple addresses)

        Returns:
            list: List of email addresses
        """
        if not address_string:
            return []

        addresses = []
        try:
            from email.utils import getaddresses, parseaddr

            parsed_addresses = getaddresses([address_string])
            addresses = [addr[1] for addr in parsed_addresses if addr[1]]
        except Exception:
            # Fallback: simple extraction
            import re

            email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"
            addresses = re.findall(email_pattern, address_string)

        return addresses

    def disconnect(self):
        """
        Disconnect from email servers.

        This method closes all active connections (IMAP and POP3) and cleans
        up resources. Should be called when done with email operations.
        """
        if self.imap_client:
            try:
                self.imap_client.close()
                self.imap_client.logout()
            except Exception:
                pass
            self.imap_client = None

        if self.pop3_client:
            try:
                self.pop3_client.quit()
            except Exception:
                pass
            self.pop3_client = None
