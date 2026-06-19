import ipaddress
import socket
import logging
import json
import re
from datetime import datetime
import platform

def auto_helper_validate_and_format_input(ip_address):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        ip = ipaddress.ip_address(ip_address)
        logging.info(f'Valid IP address: {ip}')
    except ValueError:
        logging.error(f'Invalid IP address: {ip_address}')
        return None

    try:
        socket.gethostbyname(ip_address)
        logging.info(f'DNS resolution successful for {ip_address}')
    except socket.gaierror:
        logging.error(f'DNS resolution failed for {ip_address}')
        return None

    system_info = {
        'platform': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'architecture': platform.machine(),
        'processor': platform.processor(),
        'ip_address': ip_address,
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    json_output = json.dumps(system_info, indent=4)
    logging.info(f'System info: {json_output}')

    text = 'Hello, world!'
    formatted_text = f'{text:^50}'
    logging.info(f'Formatted text: {formatted_text}')

    pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
    match = re.search(pattern, ip_address)
    if match:
        logging.info(f'Regex match: {match.group()}')
    else:
        logging.error(f'Regex match not found')

    return system_info