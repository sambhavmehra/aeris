"""
Path Utility Module - Consistent path resolution for shared directories
"""
from pathlib import Path
import os
import logging

logger = logging.getLogger("PathUtils")

def get_home_path() -> Path:
    """Get user home directory."""
    return Path.home()

def get_downloads_path() -> Path:
    """Get Downloads folder path."""
    return Path.home() / "Downloads"

def get_documents_path() -> Path:
    """Get Documents folder path."""
    return Path.home() / "Documents"

def get_desktop_path() -> Path:
    """Get Desktop folder path."""
    return Path.home() / "Desktop"

def get_shared_directories() -> dict:
    """Get all accessible shared directories on the system."""
    home = Path.home()
    directories = {
        "home": home,
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "desktop": home / "Desktop",
        "pictures": home / "Pictures",
        "music": home / "Music",
        "videos": home / "Videos",
    }
    return directories

def resolve_path(path_str: str, base_dir: str = None) -> Path:
    """
    Resolve a path string to an absolute Path object.
    Handles ~, relative, and absolute paths.
    
    Args:
        path_str: Path string to resolve
        base_dir: Optional base directory for relative paths
        
    Returns:
        Resolved Path object
    """
    # Expand ~ for home directory
    if path_str.startswith("~"):
        resolved = Path(os.path.expanduser(path_str)).resolve()
        logger.debug(f"Resolved ~ path: {path_str} -> {resolved}")
        return resolved
    
    # Check aliases
    path_lower = path_str.lower().strip()
    aliases = {
        "downloads": get_downloads_path(),
        "my downloads": get_downloads_path(),
        "documents": get_documents_path(),
        "my documents": get_documents_path(),
        "desktop": get_desktop_path(),
        "my desktop": get_desktop_path(),
        "pictures": Path.home() / "Pictures",
        "my pictures": Path.home() / "Pictures",
        "music": Path.home() / "Music",
        "videos": Path.home() / "Videos",
    }
    
    if path_lower in aliases:
        resolved = aliases[path_lower]
        logger.debug(f"Resolved alias: {path_str} -> {resolved}")
        return resolved
    
    # Absolute path
    if Path(path_str).is_absolute():
        resolved = Path(path_str).resolve()
        logger.debug(f"Resolved absolute path: {path_str} -> {resolved}")
        return resolved
    
    # Relative path with base_dir
    if base_dir:
        base = Path(base_dir).resolve()
        resolved = (base / path_str).resolve()
        logger.debug(f"Resolved relative path: {path_str} (base: {base}) -> {resolved}")
        return resolved
    
    # Default: resolve relative to current working directory
    resolved = Path(path_str).resolve()
    logger.debug(f"Resolved relative path: {path_str} -> {resolved}")
    return resolved

def check_path_accessible(path_obj: Path) -> tuple[bool, str]:
    """
    Check if a path is accessible (exists and has proper permissions).
    
    Returns:
        (is_accessible, status_message)
    """
    try:
        if not path_obj.exists():
            return False, f"Path does not exist: {path_obj}"
        
        if path_obj.is_file():
            # Try to read
            _ = os.access(path_obj, os.R_OK)
            return True, f"File accessible: {path_obj}"
        
        if path_obj.is_dir():
            # Try to list
            list(path_obj.iterdir())
            return True, f"Directory accessible: {path_obj}"
        
        return False, f"Path is neither file nor directory: {path_obj}"
    except PermissionError:
        return False, f"Permission denied: {path_obj}"
    except Exception as e:
        return False, f"Error accessing path: {path_obj} - {str(e)}"

def get_user_config():
    """Get user configuration and project paths."""
    return {
        "username": os.getenv("USERNAME", "User"),
        "home": str(Path.home()),
        "downloads": str(get_downloads_path()),
        "documents": str(get_documents_path()),
        "desktop": str(get_desktop_path()),
        "current_directory": os.getcwd(),
    }

def list_shared_dirs_status() -> dict:
    """
    List all shared directories and their accessibility status.
    """
    dirs = get_shared_directories()
    status = {}
    
    for name, path in dirs.items():
        exists = path.exists()
        if exists:
            try:
                items = len(list(path.iterdir()))
                status[name] = {
                    "path": str(path),
                    "exists": True,
                    "accessible": True,
                    "item_count": items
                }
                logger.info(f"✓ {name}: {path} ({items} items)")
            except PermissionError:
                status[name] = {
                    "path": str(path),
                    "exists": True,
                    "accessible": False,
                    "error": "Permission denied"
                }
                logger.warning(f"✗ {name}: Permission denied - {path}")
        else:
            status[name] = {
                "path": str(path),
                "exists": False,
                "accessible": False,
                "error": "Path does not exist"
            }
            logger.warning(f"✗ {name}: Does not exist - {path}")
    
    return status
