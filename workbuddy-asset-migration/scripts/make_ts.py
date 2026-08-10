"""Print a safe timestamp for backup filenames (cross-platform, no CRLF)."""
from datetime import datetime

if __name__ == "__main__":
    print(datetime.now().strftime("%Y%m%d-%H%M%S"))
