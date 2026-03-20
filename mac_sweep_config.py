from pathlib import Path

HOME = Path.home()

SCAN_TARGETS = [
    {
        "label": "User Cache",
        "path": HOME / "Library/Caches",
        "description": "App caches stored per-user",
        "safe": True,
        "category": "cache",
    },
    {
        "label": "System Cache",
        "path": Path("/Library/Caches"),
        "description": "System-wide app caches",
        "safe": True,
        "category": "cache",
    },
    {
        "label": "Browser Caches",
        "path": HOME / "Library/Caches/Google/Chrome",
        "description": "Chrome browser cache",
        "safe": True,
        "category": "browser",
    },
    {
        "label": "Safari Cache",
        "path": HOME / "Library/Caches/com.apple.Safari",
        "description": "Safari browser cache",
        "safe": True,
        "category": "browser",
    },
    {
        "label": "Homebrew Cache",
        "path": HOME / "Library/Caches/Homebrew",
        "description": "Downloaded Homebrew packages",
        "safe": True,
        "category": "package",
    },
    {
        "label": "pip Cache",
        "path": HOME / "Library/Caches/pip",
        "description": "Python pip package cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "npm Cache",
        "path": HOME / ".npm/_cacache",
        "description": "Node.js npm package cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Yarn Cache",
        "path": HOME / "Library/Caches/Yarn",
        "description": "Yarn package manager cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Gradle Cache",
        "path": HOME / ".gradle/caches",
        "description": "Java Gradle build cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Maven Cache",
        "path": HOME / ".m2/repository",
        "description": "Java Maven local repository",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Xcode DerivedData",
        "path": HOME / "Library/Developer/Xcode/DerivedData",
        "description": "Xcode build artefacts (can be very large)",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Xcode Archives",
        "path": HOME / "Library/Developer/Xcode/Archives",
        "description": "Old Xcode app archives",
        "safe": False,
        "category": "dev",
    },
    {
        "label": "iOS Device Support",
        "path": HOME / "Library/Developer/Xcode/iOS DeviceSupport",
        "description": "Device symbols for older iOS versions",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Simulator Runtimes",
        "path": HOME / "Library/Developer/CoreSimulator/Caches",
        "description": "iOS Simulator caches",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Trash",
        "path": HOME / ".Trash",
        "description": "Items in the Trash waiting to be emptied",
        "safe": True,
        "category": "system",
    },
    {
        "label": "Old Logs",
        "path": HOME / "Library/Logs",
        "description": "Application log files",
        "safe": True,
        "category": "logs",
    },
    {
        "label": "System Logs",
        "path": Path("/var/log"),
        "description": "macOS system logs",
        "safe": True,
        "category": "logs",
    },
    {
        "label": "Crash Reports",
        "path": HOME / "Library/Logs/DiagnosticReports",
        "description": "App crash diagnostic reports",
        "safe": True,
        "category": "logs",
    },
    {
        "label": "iOS Backups",
        "path": HOME / "Library/Application Support/MobileSync/Backup",
        "description": "Local iPhone/iPad backups",
        "safe": False,
        "category": "backup",
    },
    {
        "label": "Time Machine Snapshots",
        "path": Path("/.MobileBackups"),
        "description": "Local Time Machine snapshots",
        "safe": False,
        "category": "backup",
    },
    {
        "label": "Docker Data",
        "path": HOME / "Library/Containers/com.docker.docker/Data/vms/0/data",
        "description": "Docker VM disk (actual allocated size)",
        "safe": False,
        "category": "dev",
    },
    {
        "label": "Docker Cache",
        "path": HOME / "Library/Containers/com.docker.docker/Data/cache",
        "description": "Docker layer & build cache",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Language Support Files",
        "path": Path("/System/Library/PrivateFrameworks"),
        "description": "Extra language packs (read-only on modern macOS)",
        "safe": False,
        "category": "system",
    },
    {
        "label": "Old Downloads",
        "path": HOME / "Downloads",
        "description": "Files in Downloads folder (review before deleting)",
        "safe": False,
        "category": "user",
    },
]

CATEGORY_COLORS = {
    "cache": "cyan",
    "browser": "blue",
    "package": "green",
    "dev": "yellow",
    "logs": "magenta",
    "backup": "red",
    "apps": "orange3",
    "system": "white",
    "user": "bright_white",
}

CATEGORY_ICONS = {
    "cache": "🗂 ",
    "browser": "🌐",
    "package": "📦",
    "dev": "🔨",
    "logs": "📋",
    "backup": "💾",
    "apps": "📱",
    "system": "⚙️ ",
    "user": "👤",
}

RISK_RANK = {
    "safe": 1,
    "review": 2,
    "danger": 3,
}

RISK_COLORS = {
    "safe": "green",
    "review": "yellow",
    "danger": "red",
}

CATEGORY_SAFE_EXPLANATIONS = {
    "cache": "Regenerated automatically by apps and macOS.",
    "browser": "Browsers recreate cache content as you browse.",
    "package": "Package manager caches can be re-downloaded.",
    "dev": "Mostly build artefacts and local development cache.",
    "logs": "Log files are historical and can be recreated.",
    "backup": "Contains user/device backup data; review carefully.",
    "apps": "May include app state or user content.",
    "system": "System-managed area; cleanup can have side effects.",
    "user": "Likely user files; verify before deleting.",
}
