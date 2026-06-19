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
    """Get Documents folder path, checking OneDrive fallback."""
    home = Path.home()
    onedrive_docs = home / "OneDrive" / "Documents"
    if onedrive_docs.is_dir():
        return onedrive_docs
    return home / "Documents"

def get_desktop_path() -> Path:
    """Get Desktop folder path, checking OneDrive fallback."""
    home = Path.home()
    onedrive_desktop = home / "OneDrive" / "Desktop"
    if onedrive_desktop.is_dir():
        return onedrive_desktop
    return home / "Desktop"

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
    Handles ~, relative, absolute paths, drive letters, and Hinglish aliases.
    
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
    
    # Check aliases (expanded with drives, AERIS dirs, and Hinglish)
    path_lower = path_str.lower().strip()
    
    home = Path.home()
    
    # Build AERIS project paths dynamically
    try:
        from config import settings
        aeris_root = settings.BASE_DIR.parent
        backend = settings.BASE_DIR
        frontend = aeris_root / "FRONTEND"
        workspace = settings.WORKSPACE_DIR
    except Exception:
        aeris_root = Path("d:/Sambhav Projects/AERIS")
        backend = aeris_root / "BACKEND"
        frontend = aeris_root / "FRONTEND"
        workspace = aeris_root / "workspace"
    
    aliases = {
        # ── Standard user folders ──
        "downloads": get_downloads_path(),
        "download": get_downloads_path(),
        "my downloads": get_downloads_path(),
        "mera download": get_downloads_path(),
        "download folder": get_downloads_path(),
        "documents": get_documents_path(),
        "document": get_documents_path(),
        "my documents": get_documents_path(),
        "mera document": get_documents_path(),
        "docs": get_documents_path(),
        "desktop": get_desktop_path(),
        "my desktop": get_desktop_path(),
        "mera desktop": get_desktop_path(),
        "pictures": home / "Pictures",
        "my pictures": home / "Pictures",
        "photos": home / "Pictures",
        "meri photos": home / "Pictures",
        "music": home / "Music",
        "songs": home / "Music",
        "gaane": home / "Music",
        "videos": home / "Videos",
        "video": home / "Videos",
        "meri videos": home / "Videos",
        "home": home,
        "user folder": home,
        "home directory": home,
        
        # ── AppData / System ──
        "appdata": home / "AppData",
        "app data": home / "AppData",
        "temp": home / "AppData" / "Local" / "Temp",
        "program files": Path("C:/Program Files"),
        
        # ── Drive letters ──
        "c drive": Path("C:/"),
        "d drive": Path("D:/"),
        "e drive": Path("E:/"),
        "d wali drive": Path("D:/"),
        "c wali drive": Path("C:/"),
        
        # ── AERIS Project ──
        "aeris": aeris_root,
        "aeris project": aeris_root,
        "project root": aeris_root,
        "backend": backend,
        "back end": backend,
        "server": backend,
        "frontend": frontend,
        "front end": frontend,
        "workspace": workspace,
        "agents": backend / "agents",
        "agent": backend / "agents",
        "services": backend / "services",
        "service": backend / "services",
        "tools": backend / "tools",
        "intelligence": backend / "intelligence",
        "automation": backend / "automation",
        "memory": backend / "memory",
        "neural": backend / "neural",
        "plugins": backend / "plugins",
        "utils": backend / "utils",
        "data": backend / "data",
        "engine": backend / "engine",
        "generation": backend / "generation",
        "src": frontend / "src",
    }
    
    if path_lower in aliases:
        resolved = aliases[path_lower]
        logger.debug(f"Resolved alias: {path_str} -> {resolved}")
        return resolved

    # Check if path starts with a known alias prefix (e.g. "backend/api.py")
    normalized_path = path_str.replace("\\", "/")
    parts = [p.strip() for p in normalized_path.split("/") if p.strip()]
    if parts and parts[0].lower() in aliases:
        base = aliases[parts[0].lower()]
        resolved = Path(base).joinpath(*parts[1:]).resolve()
        logger.debug(f"Resolved prefix alias: {path_str} -> {resolved}")
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


def resolve_folder_smart(raw_query: str) -> tuple[Path | None, float]:
    """
    Smart folder resolution using the FolderIntelligence engine.
    Falls back to basic resolve_path() if FolderIntelligence finds nothing.
    
    Args:
        raw_query: Natural language folder reference (can be Hinglish, vague, etc.)
        
    Returns:
        (resolved_path, confidence) — confidence is 0.0-1.0. None if unresolved.
    """
    # Try FolderIntelligence first (fuzzy + context-aware)
    try:
        from intelligence.folder_intelligence import get_folder_intelligence
        fi = get_folder_intelligence()
        match = fi.resolve(raw_query)
        if match and match.confidence >= 0.5:
            logger.info(f"Smart folder resolved: '{raw_query}' -> {match.path} "
                        f"(confidence={match.confidence:.2f}, type={match.match_type})")
            return Path(match.path), match.confidence
    except Exception as e:
        logger.warning(f"FolderIntelligence failed for '{raw_query}': {e}")
    
    # Fallback to basic alias resolution
    try:
        resolved = resolve_path(raw_query)
        if resolved.is_dir():
            return resolved, 0.7
    except Exception:
        pass
    
    return None, 0.0

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
