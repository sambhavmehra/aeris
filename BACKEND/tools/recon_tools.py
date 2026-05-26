import socket
import ssl
import subprocess
import requests
import urllib.parse
from urllib.error import URLError

def dns_lookup(domain: str, record_type: str = "ALL") -> str:
    """Perform a basic DNS lookup."""
    try:
        ip = socket.gethostbyname(domain)
        return f"DNS Lookup for {domain}:\n- A Record (IPv4): {ip}"
    except Exception as e:
        return f"DNS Lookup failed for {domain}: {e}"

def whois_lookup(domain: str) -> str:
    """Perform a basic WHOIS lookup using system command."""
    try:
        # For Windows, this relies on a whois executable or falls back to an error
        result = subprocess.run(["whois", domain], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            return result.stdout[:1000] + "\n...[truncated]"
        return "WHOIS command failed or not installed on the system."
    except Exception as e:
        return f"WHOIS failed: {e}"

def port_scan(target: str) -> str:
    """Perform a fast port scan of common ports."""
    common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 8080, 8443]
    open_ports = []
    
    for port in common_ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex((target, port))
        if result == 0:
            open_ports.append(port)
        sock.close()
        
    if open_ports:
        return f"Open ports found on {target}: {', '.join(map(str, open_ports))}"
    return f"No common open ports found on {target} (scanned {len(common_ports)} ports)."

def header_analysis(url: str) -> str:
    """Fetch HTTP headers and analyze for security misconfigurations."""
    if not url.startswith("http"):
        url = "http://" + url
    try:
        resp = requests.head(url, timeout=5, allow_redirects=True)
        headers = resp.headers
        analysis = []
        
        # Security headers check
        sec_headers = {
            "Strict-Transport-Security": "Missing HSTS",
            "X-Frame-Options": "Missing Clickjacking protection",
            "X-Content-Type-Options": "Missing MIME-sniffing protection",
            "Content-Security-Policy": "Missing CSP",
            "Server": "Server version exposed",
            "X-Powered-By": "Technology stack exposed"
        }
        
        for h, msg in sec_headers.items():
            if h not in headers:
                if "Missing" in msg:
                    analysis.append(msg)
            else:
                if "exposed" in msg:
                    analysis.append(f"{msg}: {headers[h]}")
                    
        return f"Header Analysis for {url}:\nStatus: {resp.status_code}\n" + "\n".join(analysis)
    except Exception as e:
        return f"Header analysis failed: {e}"

def ssl_check(domain: str) -> str:
    """Check SSL certificate validity."""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(5.0)
            s.connect((domain, 443))
            cert = s.getpeercert()
            issuer = dict(x[0] for x in cert['issuer'])
            return f"SSL Check for {domain}:\n- Issuer: {issuer.get('organizationName', 'Unknown')}\n- Valid From: {cert['notBefore']}\n- Valid To: {cert['notAfter']}"
    except Exception as e:
        return f"SSL Check failed for {domain}: {e}"

def subdomain_enum(domain: str) -> str:
    """Basic subdomain enumeration using a common list."""
    common_subs = ["www", "mail", "ftp", "localhost", "webmail", "smtp", "pop", "ns1", "ns2", "webdisk", "cpanel", "dev", "test", "staging", "api"]
    found = []
    for sub in common_subs:
        target = f"{sub}.{domain}"
        try:
            ip = socket.gethostbyname(target)
            found.append(f"{target} ({ip})")
        except socket.error:
            pass
    if found:
        return f"Found {len(found)} common subdomains:\n" + "\n".join(found)
    return "No common subdomains found."
