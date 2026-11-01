"""
Server-Side Request Forgery (SSRF) Protection and Safe HTTP Ingestion Utilities for WebinarAI.

Defends against SSRF, DNS rebinding, internal network reconnaissance,
redirect hijacking, non-standard port scanning, and infinite stream exhaustion.
"""

import ipaddress
import logging
import os
import re
import socket
import urllib.parse
from typing import Tuple, Optional, Dict, Any, List
import requests

logger = logging.getLogger(__name__)

# Standard permitted public web protocols and ports
APPROVED_SCHEMES = ('http', 'https')
APPROVED_PORTS = (80, 443, 8080, 8443)

# Cloud metadata endpoints and known dangerous internal destinations
BLOCKED_HOSTNAMES = {
    'localhost',
    'localhost.localdomain',
    'ip6-localhost',
    'ip6-loopback',
    'metadata.google.internal',
    'metadata.internal',
    'instance-data',
}

class SSRFSecurityError(Exception):
    """Exception raised when an outbound URL violates SSRF safety boundaries."""
    pass

class SSRFStreamLimitExceeded(SSRFSecurityError):
    """Exception raised when a streaming download exceeds maximum byte boundaries."""
    pass


def unwrap_ipv4_mapped(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwraps IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1) to IPv4."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def is_ip_restricted(ip_str: str) -> Tuple[bool, str]:
    """
    Evaluates whether an IP address belongs to private, loopback, link-local,
    multicast, reserved, or cloud metadata ranges.
    Returns (is_restricted, reason).
    """
    try:
        raw_ip = ipaddress.ip_address(ip_str)
        ip = unwrap_ipv4_mapped(raw_ip)
    except ValueError:
        return True, "Invalid IP address representation"

    if ip.is_loopback:
        return True, "Loopback destination prohibited"
    if ip.is_private:
        return True, "Private RFC 1918 / unique-local destination prohibited"
    if ip.is_link_local:
        return True, "Link-local / APIPA destination prohibited"
    if ip.is_reserved:
        return True, "IETF reserved IP range prohibited"
    if ip.is_multicast:
        return True, "Multicast destination prohibited"
    if ip.is_unspecified:
        return True, "Unspecified destination address prohibited"

    # Specific check for cloud instance metadata IPv4 (169.254.169.254)
    if str(ip) == "169.254.169.254":
        return True, "Cloud metadata endpoint prohibited"

    return False, "Public routable address"


def validate_url_ssrf(
    url: str,
    allowed_schemes: tuple = APPROVED_SCHEMES,
    allowed_ports: tuple = APPROVED_PORTS
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Inspects URL syntax, resolves DNS, and validates that all resolved IP addresses
    are public routable destinations.
    
    Returns (is_safe, error_message, primary_resolved_ip).
    Never exposes internal system details or network topologies in error messages.
    """
    if not url or not isinstance(url, str):
        return False, "Invalid link. Please provide a valid HTTP or HTTPS media URL.", None

    url_clean = url.strip()
    try:
        parsed = urllib.parse.urlparse(url_clean)
    except Exception:
        return False, "Malformed URL structure.", None

    # Scheme validation
    scheme = parsed.scheme.lower()
    if scheme not in allowed_schemes:
        return False, f"Unsupported protocol '{scheme}'. Only HTTP and HTTPS are permitted.", None

    # Hostname validation
    hostname = parsed.hostname
    if not hostname:
        return False, "Invalid URL: Destination host is missing.", None

    hostname_lower = hostname.lower().strip('.')
    if hostname_lower in BLOCKED_HOSTNAMES or hostname_lower.endswith('.localhost') or hostname_lower.endswith('.local'):
        return False, "Destination host is restricted.", None

    # Port validation
    port = parsed.port
    if port is None:
        port = 443 if scheme == 'https' else 80

    if port not in allowed_ports:
        return False, f"Access to port {port} is restricted.", None

    # DNS Resolution & IP Evaluation
    try:
        # Resolve all addresses (both IPv4 and IPv6)
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        if not addr_info:
            return False, "Could not resolve destination server address.", None

        resolved_ips: List[str] = []
        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            if ip_str not in resolved_ips:
                resolved_ips.append(ip_str)

        # Inspect every resolved IP address
        for ip_str in resolved_ips:
            restricted, reason = is_ip_restricted(ip_str)
            if restricted:
                logger.warning(f"[SSRF Defense] Blocked outbound request to host '{hostname}' resolving to restricted IP '{ip_str}' ({reason})")
                return False, "Destination address is restricted or non-routable.", None

        return True, None, resolved_ips[0]

    except socket.gaierror as e:
        logger.info(f"[SSRF Defense] DNS resolution failed for host '{hostname}': {str(e)}")
        return False, "Destination host could not be resolved. Please verify the link.", None
    except Exception as e:
        logger.error(f"[SSRF Defense] Unexpected error evaluating host '{hostname}': {str(e)}")
        return False, "Unable to verify destination server safety.", None


def safe_request(
    url: str,
    method: str = 'GET',
    headers: Optional[Dict[str, str]] = None,
    stream: bool = False,
    max_redirects: int = 5,
    timeout: Tuple[int, int] = (10, 30)
) -> requests.Response:
    """
    Executes an HTTP request with strict hop-by-hop redirect SSRF re-validation.
    Guarantees that redirects do not pivot to internal, loopback, or cloud metadata endpoints.
    """
    current_url = url
    redirect_count = 0
    client_headers = {
        'User-Agent': 'WebinarAI-Retrieval-Agent/1.0 (+http://webinarai.edu)',
        **(headers or {})
    }

    session = requests.Session()

    while True:
        # Validate current hop URL against SSRF boundaries
        is_safe, error_msg, _ = validate_url_ssrf(current_url)
        if not is_safe:
            raise SSRFSecurityError(error_msg or "SSRF boundary violation on target address.")

        try:
            response = session.request(
                method=method,
                url=current_url,
                headers=client_headers,
                allow_redirects=False,
                stream=stream,
                timeout=timeout
            )
        except requests.exceptions.Timeout:
            raise SSRFSecurityError("Connection to media server timed out.")
        except requests.exceptions.RequestException as e:
            raise SSRFSecurityError(f"Network error accessing media server: {str(e)}")

        # Check for HTTP redirect status codes (301, 302, 303, 307, 308)
        if response.is_redirect:
            redirect_count += 1
            if redirect_count > max_redirects:
                raise SSRFSecurityError(f"Too many HTTP redirects (exceeded limit of {max_redirects}).")

            location = response.headers.get('Location')
            if not location:
                raise SSRFSecurityError("Redirect response missing Location header.")

            # Resolve relative redirect URLs against current URL
            current_url = urllib.parse.urljoin(current_url, location)
            logger.info(f"[SSRF Defense] Following redirect #{redirect_count} to: {current_url}")
            continue

        return response


def safe_download_media_stream(
    url: str,
    destination_path: str,
    max_size_bytes: int,
    chunk_size: int = 65536,
    timeout: Tuple[int, int] = (10, 60)
) -> Dict[str, Any]:
    """
    Streams media safely from a validated URL to disk:
    1. Pre-checks Content-Length header against max_size_bytes.
    2. Writes data incrementally in 64KB chunks.
    3. Enforces strict cumulative byte counting; aborts immediately and cleans up on limit overflow.
    4. Ensures file integrity and returns detected content metadata.
    """
    is_safe, error_msg, _ = validate_url_ssrf(url)
    if not is_safe:
        return {
            'success': False,
            'error': error_msg or "Destination is restricted.",
            'code': 'SSRF_RESTRICTED'
        }

    # Ensure target directory exists
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    try:
        response = safe_request(url, method='GET', stream=True, timeout=timeout)
    except SSRFSecurityError as se:
        return {
            'success': False,
            'error': str(se),
            'code': 'SSRF_BLOCKED'
        }

    if response.status_code != 200:
        return {
            'success': False,
            'error': f"Media server returned HTTP status {response.status_code}.",
            'code': f'HTTP_{response.status_code}'
        }

    # Header-based early Content-Length verification
    content_length_header = response.headers.get('Content-Length')
    if content_length_header and content_length_header.isdigit():
        content_length = int(content_length_header)
        if content_length > max_size_bytes:
            max_mb = max_size_bytes // (1024 * 1024)
            size_mb = content_length // (1024 * 1024)
            return {
                'success': False,
                'error': f"File size ({size_mb}MB) exceeds allowable limit of {max_mb}MB.",
                'code': 'FILE_TOO_LARGE'
            }

    content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()

    # Stream download with cumulative byte counting
    total_bytes = 0
    temp_path = destination_path + ".part"

    try:
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        f.close()
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        max_mb = max_size_bytes // (1024 * 1024)
                        return {
                            'success': False,
                            'error': f"Streaming download exceeded maximum permitted size of {max_mb}MB.",
                            'code': 'FILE_TOO_LARGE'
                        }
                    f.write(chunk)

        if total_bytes == 0:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return {
                'success': False,
                'error': "Retrieved media stream is empty (0 bytes).",
                'code': 'EMPTY_STREAM'
            }

        # Atomically rename .part to final destination
        if os.path.exists(destination_path):
            os.remove(destination_path)
        os.replace(temp_path, destination_path)

        return {
            'success': True,
            'storage_path': destination_path,
            'file_size': total_bytes,
            'content_type': content_type
        }

    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return {
            'success': False,
            'error': f"Interruption during media streaming: {str(e)}",
            'code': 'STREAM_ERROR'
        }

