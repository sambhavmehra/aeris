import socket
import ssl
import subprocess
import requests
import urllib.parse
from urllib.error import URLError
from typing import Optional

def _update_webweaver_graph(node_id: str, label: str, node_type: str, parent_id: Optional[str] = None, link_type: str = "connection"):
    import json
    try:
        from config import settings
        graph_path = settings.DATA_DIR / "webweaver_graph.json"
        
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        if graph_path.exists():
            try:
                graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
            except Exception:
                graph_data = {"nodes": [], "links": []}
        else:
            graph_data = {"nodes": [], "links": []}

        # Add node if not exists
        node_exists = False
        for n in graph_data.setdefault("nodes", []):
            if n["id"] == node_id:
                n["label"] = label
                n["type"] = node_type
                n["status"] = "online"
                node_exists = True
                break
        
        if not node_exists:
            graph_data["nodes"].append({
                "id": node_id,
                "label": label,
                "type": node_type,
                "status": "online"
            })
            
        # Add link if parent_id is specified
        if parent_id:
            link_exists = False
            for l in graph_data.setdefault("links", []):
                if l["source"] == parent_id and l["target"] == node_id:
                    l["type"] = link_type
                    link_exists = True
                    break
            if not link_exists:
                graph_data["links"].append({
                    "source": parent_id,
                    "target": node_id,
                    "type": link_type
                })
                
        graph_path.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
    except Exception as e:
        # Don't fail execution if graph update fails
        pass

def dns_lookup(domain: str, record_type: str = "ALL") -> str:
    """Perform a basic DNS lookup."""
    try:
        ip = socket.gethostbyname(domain)
        _update_webweaver_graph(domain, domain, "domain")
        _update_webweaver_graph(ip, ip, "ip", parent_id=domain, link_type="resolves_to")
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
    _update_webweaver_graph(target, target, "host")
    common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 8080, 8443]
    open_ports = []
    
    for port in common_ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex((target, port))
        if result == 0:
            open_ports.append(port)
            
            port_id = f"{target}:{port}"
            port_label = f"Port {port}"
            service_names = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB", 3306: "MySQL", 3389: "RDP", 8080: "HTTP-Alt", 8443: "HTTPS-Alt"}
            service_name = service_names.get(port, "unknown")
            _update_webweaver_graph(port_id, f"{port_label} ({service_name})", "service", parent_id=target, link_type="exposes_port")
            
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
    _update_webweaver_graph(domain, domain, "domain")
    common_subs = ["www", "mail", "ftp", "localhost", "webmail", "smtp", "pop", "ns1", "ns2", "webdisk", "cpanel", "dev", "test", "staging", "api"]
    found = []
    for sub in common_subs:
        target = f"{sub}.{domain}"
        try:
            ip = socket.gethostbyname(target)
            found.append(f"{target} ({ip})")
            _update_webweaver_graph(target, target, "subdomain", parent_id=domain, link_type="subdomain_of")
            _update_webweaver_graph(ip, ip, "ip", parent_id=target, link_type="resolves_to")
        except socket.error:
            pass
    if found:
        return f"Found {len(found)} common subdomains:\n" + "\n".join(found)
    return "No common subdomains found."

