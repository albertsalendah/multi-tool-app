from enum import StrEnum


class Capability(StrEnum):
    BROWSER = "browser"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    CAPTCHA = "captcha"
    CLIPBOARD = "clipboard"
    DATABASE = "database"
