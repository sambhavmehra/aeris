import subprocess
import re
import socket
import ctypes
import time
from ctypes import byref, POINTER, c_ulong, c_void_p
from typing import Dict, Any, List, Optional
from tools.recon_tools import _update_webweaver_graph

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8)
    ]

def _trigger_hardware_scan() -> bool:
    """Trigger an active hardware Wi-Fi scan via native Windows WLAN API."""
    try:
        wlanapi = ctypes.windll.wlanapi
        handle = c_void_p()
        negotiated_version = c_ulong()
        
        # 1. Open handle
        ret = wlanapi.WlanOpenHandle(2, None, byref(negotiated_version), byref(handle))
        if ret != 0:
            return False

        try:
            # 2. Enum wireless interfaces
            interface_list = c_void_p()
            ret = wlanapi.WlanEnumInterfaces(handle, None, byref(interface_list))
            if ret != 0:
                return False

            try:
                num_items = ctypes.cast(interface_list, POINTER(c_ulong)).contents.value
                if num_items > 0:
                    # Access the GUID of the first active interface
                    guid_ptr = ctypes.cast(interface_list.value + 8, POINTER(GUID))
                    interface_guid = guid_ptr.contents
                    
                    # 3. Request scan
                    ret = wlanapi.WlanScan(handle, byref(interface_guid), None, None, None)
                    return ret == 0
            finally:
                if interface_list:
                    wlanapi.WlanFreeMemory(interface_list)
        finally:
            if handle:
                wlanapi.WlanCloseHandle(handle, None)
    except Exception:
        pass
    return False

def wifi_scan_networks() -> str:
    """Scan nearby visible WiFi networks using Windows netsh command.
    Returns a formatted summary of SSID, Signal Strength, Authentication, BSSID, and Channel.
    """
    try:
        # Trigger active hardware scan first and wait for it to complete
        if _trigger_hardware_scan():
            time.sleep(2.0)  # Yield for scan results to propagate to system cache
        
        # Run netsh command to scan networks
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15
        )
        if result.returncode != 0:
            return f"Failed to scan networks: {result.stderr or 'Unknown netsh error'}"
        
        output = result.stdout
        networks = []
        current_net: Dict[str, Any] = {}
        current_bssid: Dict[str, Any] = {}
        
        # Parse output line by line
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # Match SSID header
            ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line)
            if ssid_match:
                if current_net:
                    networks.append(current_net)
                current_net = {
                    "ssid": ssid_match.group(1).strip() or "[Hidden SSID]",
                    "network_type": "",
                    "authentication": "",
                    "encryption": "",
                    "bssids": []
                }
                continue
                
            if current_net:
                # Auth details
                if line.startswith("Network type"):
                    current_net["network_type"] = line.split(":", 1)[1].strip()
                elif line.startswith("Authentication"):
                    current_net["authentication"] = line.split(":", 1)[1].strip()
                elif line.startswith("Encryption"):
                    current_net["encryption"] = line.split(":", 1)[1].strip()
                # BSSID details
                elif line.startswith("BSSID"):
                    if current_bssid:
                        current_net["bssids"].append(current_bssid)
                    bssid_mac = line.split(":", 1)[1].strip()
                    current_bssid = {"bssid": bssid_mac, "signal": "0%", "channel": "Unknown", "basic_rates": ""}
                elif line.startswith("Signal"):
                    current_bssid["signal"] = line.split(":", 1)[1].strip()
                elif line.startswith("Channel"):
                    current_bssid["channel"] = line.split(":", 1)[1].strip()
                elif line.startswith("Basic rates"):
                    current_bssid["basic_rates"] = line.split(":", 1)[1].strip()
                    
        # Append last BSSID and network
        if current_bssid and current_net:
            current_net["bssids"].append(current_bssid)
        if current_net:
            networks.append(current_net)
            
        if not networks:
            return "No WiFi networks found, or WiFi interface is disabled."
            
        # Format the output report
        report = ["=== WiFi Scan Report ==="]
        for idx, net in enumerate(networks, 1):
            ssid = net["ssid"]
            auth = net["authentication"]
            encrypt = net["encryption"]
            report.append(f"\n{idx}. SSID: {ssid}")
            report.append(f"   Auth/Encryption: {auth} / {encrypt}")
            
            # Update webweaver graph for each SSID/BSSID
            _update_webweaver_graph(ssid, ssid, "wifi_ssid")
            
            for b in net["bssids"]:
                bssid = b["bssid"]
                sig = b["signal"]
                chan = b["channel"]
                report.append(f"   - BSSID: {bssid} | Signal: {sig} | Channel: {chan}")
                _update_webweaver_graph(bssid, f"BSSID {bssid} (Sig: {sig})", "wifi_bssid", parent_id=ssid, link_type="broadcasts")
                
        return "\n".join(report)
        
    except Exception as e:
        return f"Error scanning WiFi networks: {str(e)}"

def wifi_current_connection() -> str:
    """Show details of the current active WiFi connection on the machine."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        if result.returncode != 0:
            return f"Failed to retrieve interface info: {result.stderr}"
            
        output = result.stdout
        # Check if connected
        if "State" in output and "disconnected" in output.lower():
            return "WiFi Interface detected, but it is currently disconnected."
            
        # Parse fields
        conn_info = {}
        for line in output.splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                conn_info[key.strip()] = val.strip()
                
        if not conn_info or "State" not in conn_info:
            return "No active wireless connection or wlan interface not found."
            
        report = [
            "=== Current WiFi Connection ===",
            f"Name: {conn_info.get('Name', 'Unknown')}",
            f"Description: {conn_info.get('Description', 'Unknown')}",
            f"State: {conn_info.get('State', 'Unknown')}",
            f"SSID: {conn_info.get('SSID', 'Unknown')}",
            f"BSSID: {conn_info.get('BSSID', 'Unknown')}",
            f"Network Type: {conn_info.get('Network type', 'Unknown')}",
            f"Radio Type: {conn_info.get('Radio type', 'Unknown')}",
            f"Authentication: {conn_info.get('Authentication', 'Unknown')}",
            f"Cipher: {conn_info.get('Cipher', 'Unknown')}",
            f"Channel: {conn_info.get('Channel', 'Unknown')}",
            f"Receive Rate (Mbps): {conn_info.get('Receive rate (Mbps)', 'Unknown')}",
            f"Transmit Rate (Mbps): {conn_info.get('Transmit rate (Mbps)', 'Unknown')}",
            f"Signal: {conn_info.get('Signal', 'Unknown')}"
        ]
        
        # Update WebWeaver Graph
        ssid = conn_info.get('SSID')
        if ssid:
            _update_webweaver_graph(ssid, ssid, "wifi_ssid")
            bssid = conn_info.get('BSSID')
            if bssid:
                _update_webweaver_graph(bssid, f"Connected BSSID: {bssid}", "wifi_bssid", parent_id=ssid, link_type="active_connection")
                
        return "\n".join(report)
        
    except Exception as e:
        return f"Error retrieving current WiFi interface connection info: {str(e)}"

def wifi_saved_profiles() -> str:
    """List all saved WiFi profile names on the machine."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "profiles"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        if result.returncode != 0:
            return f"Failed to get saved profiles: {result.stderr}"
            
        output = result.stdout
        profiles = []
        for line in output.splitlines():
            line = line.strip()
            if "All User Profile" in line:
                profile_name = line.split(":", 1)[1].strip()
                profiles.append(profile_name)
                
        if not profiles:
            return "No saved WiFi profiles found."
            
        report = ["=== Saved WiFi Profiles ==="]
        for p in profiles:
            report.append(f"- {p}")
        return "\n".join(report)
        
    except Exception as e:
        return f"Error listing saved profiles: {str(e)}"

def wifi_profile_detail(profile_name: str) -> str:
    """Show details of a specific saved WiFi profile.
    If the user has administrative/owner rights, it lists configuration settings and key contents.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "profile", f"name={profile_name}", "key=clear"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10
        )
        if result.returncode != 0:
            return f"Failed to get profile details: {result.stderr or 'Profile not found'}"
            
        output = result.stdout
        parsed_details = []
        key_content = "Not Found/Protected"
        
        for line in output.splitlines():
            line = line.strip()
            if "Key Content" in line:
                key_content = line.split(":", 1)[1].strip()
            elif ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if key in ["Name", "Type", "Authentication", "Cipher", "Security key"]:
                    parsed_details.append(f"{key}: {val}")
                    
        report = [
            f"=== WiFi Profile Details for '{profile_name}' ===",
            *parsed_details,
            f"Security Key Material: {key_content}"
        ]
        return "\n".join(report)
        
    except Exception as e:
        return f"Error retrieving profile details: {str(e)}"

def wifi_network_info() -> str:
    """Get full system network adapter configurations (ipconfig /all equivalent)."""
    try:
        result = subprocess.run(
            ["ipconfig", "/all"],
            capture_output=True,
            text=True,
            encoding="oem",  # Use OEM encoding for Windows console compatibility
            errors="ignore",
            timeout=10
        )
        if result.returncode != 0:
            return f"Failed to retrieve ipconfig details: {result.stderr}"
            
        # Parse ipconfig to pull out relevant active adapters
        lines = result.stdout.splitlines()
        active_adapters = []
        current_adapter = []
        is_active = False
        
        for line in lines:
            if not line.strip() and current_adapter:
                if is_active:
                    active_adapters.append("\n".join(current_adapter))
                current_adapter = []
                is_active = False
                continue
                
            current_adapter.append(line)
            lower_line = line.lower()
            if "ipv4 address" in lower_line or "default gateway" in lower_line:
                if "0.0.0.0" not in lower_line:
                    is_active = True
                    
        if current_adapter and is_active:
            active_adapters.append("\n".join(current_adapter))
            
        if not active_adapters:
            return "No active network adapters found with IPv4 or Default Gateway configs."
            
        return "=== Active Network Interfaces ===\n\n" + "\n\n".join(active_adapters)
        
    except Exception as e:
        return f"Error running network configurations utility: {str(e)}"

def wifi_arp_table() -> str:
    """Read the local Address Resolution Protocol (ARP) table to discover neighboring hosts on the network link."""
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            encoding="oem",
            errors="ignore",
            timeout=10
        )
        if result.returncode != 0:
            return f"Failed to retrieve ARP table: {result.stderr}"
            
        lines = result.stdout.splitlines()
        report = ["=== Local Network Hosts (ARP Table) ==="]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Filter out broad or multicast addresses for cleaner results
            parts = line.split()
            if len(parts) >= 3:
                ip, mac, link_type = parts[0], parts[1], parts[2]
                if link_type.lower() == "dynamic" or (link_type.lower() == "static" and not ip.startswith("224.") and not ip.endswith(".255")):
                    report.append(f"IP: {ip:<16} | MAC: {mac:<18} | Type: {link_type}")
                    _update_webweaver_graph(ip, f"Host: {ip}", "host")
                    _update_webweaver_graph(mac, f"MAC: {mac}", "mac_address", parent_id=ip, link_type="has_mac")
                    
        if len(report) == 1:
            return "ARP table resolved, but no dynamic/private neighbors were found."
            
        return "\n".join(report)
        
    except Exception as e:
        return f"Error retrieving local ARP table: {str(e)}"

def wifi_speed_test() -> str:
    """Measure network latency and ping response quality to generic major DNS nodes (8.8.8.8 and 1.1.1.1)."""
    targets = ["8.8.8.8", "1.1.1.1"]
    report = ["=== Network Latency & Speed Diagnostic ==="]
    
    for target in targets:
        try:
            # Run a quick 3-packet ping test
            result = subprocess.run(
                ["ping", "-n", "3", target],
                capture_output=True,
                text=True,
                encoding="oem",
                errors="ignore",
                timeout=10
            )
            if result.returncode != 0:
                report.append(f"\nTarget {target}: Host unreachable or firewall blocking.")
                continue
                
            # Extract round trip average
            avg_match = re.search(r"Average = (\d+)ms", result.stdout)
            lost_match = re.search(r"Lost = (\d+)", result.stdout)
            
            if avg_match and lost_match:
                avg = avg_match.group(1)
                lost = lost_match.group(1)
                status = "Excellent" if int(avg) < 50 else ("Fair" if int(avg) < 150 else "Poor")
                report.append(f"\nTarget {target}:")
                report.append(f"  - Average Round-Trip Time: {avg} ms ({status})")
                report.append(f"  - Packet Loss: {lost}/3 packets lost")
            else:
                report.append(f"\nTarget {target}: Ping successful, but output format was unparseable.")
                
        except Exception as e:
            report.append(f"\nTarget {target} test failed: {str(e)}")
            
    return "\n".join(report)
