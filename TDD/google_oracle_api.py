"""
Google vs. Oracle API Copyright Lawsuit Testbed Downloader

Downloads the core java.lang and java.util classes that were at the center
of the Oracle v. Google API copyright lawsuit:
  - OpenJDK 7 (Oracle) — from GitHub mirror
  - AOSP Froyo / Android 2.2 (Google) — from official android.googlesource.com

The AOSP Froyo codebase is based on Apache Harmony, where Google
reimplemented the Java API (same SSO: class names, method signatures,
parameter names) with entirely different implementation bodies.

Note: android.googlesource.com (Gitiles) serves raw file content only via
      ?format=TEXT, which returns base64-encoded text.
"""

import base64
import os
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# SSL certificate verification bypass (for some corporate/proxy environments)
ssl_context = ssl._create_unverified_context()

# Download directories
BASE_DIR = os.path.join("example", "Case-Oracle")
LEFT_DIR = os.path.join(BASE_DIR, "OpenJDK_Oracle")
RIGHT_DIR = os.path.join(BASE_DIR, "AOSP_Google")

# Core classes from the lawsuit
# OpenJDK 7 (Oracle) vs Android 2.2 Froyo (Google/Apache Harmony)
TARGET_FILES = {
    "String.java": {
        "left": "https://raw.githubusercontent.com/openjdk/jdk7u/master/jdk/src/share/classes/java/lang/String.java",
        "right": "https://android.googlesource.com/platform/dalvik/+/refs/tags/android-2.2_r1/libcore/luni/src/main/java/java/lang/String.java"
    },
    "Math.java": {
        "left": "https://raw.githubusercontent.com/openjdk/jdk7u/master/jdk/src/share/classes/java/lang/Math.java",
        "right": "https://android.googlesource.com/platform/dalvik/+/refs/tags/android-2.2_r1/libcore/luni/src/main/java/java/lang/Math.java"
    },
    "List.java": {
        "left": "https://raw.githubusercontent.com/openjdk/jdk7u/master/jdk/src/share/classes/java/util/List.java",
        "right": "https://android.googlesource.com/platform/dalvik/+/refs/tags/android-2.2_r1/libcore/luni/src/main/java/java/util/List.java"
    },
    "Collections.java": {
        "left": "https://raw.githubusercontent.com/openjdk/jdk7u/master/jdk/src/share/classes/java/util/Collections.java",
        "right": "https://android.googlesource.com/platform/dalvik/+/refs/tags/android-2.2_r1/libcore/luni/src/main/java/java/util/Collections.java"
    },
    "ArrayList.java": {
        "left": "https://raw.githubusercontent.com/openjdk/jdk7u/master/jdk/src/share/classes/java/util/ArrayList.java",
        "right": "https://android.googlesource.com/platform/dalvik/+/refs/tags/android-2.2_r1/libcore/luni/src/main/java/java/util/ArrayList.java"
    }
}


def _download_raw(url: str) -> bytes:
    """Download raw file content from a URL.

    For android.googlesource.com (Gitiles), appends ?format=TEXT and
    decodes the base64 response. For all other URLs, returns content as-is.
    """
    is_gitiles = "googlesource.com" in url

    if is_gitiles:
        url = url.rstrip("/") + "?format=TEXT"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ssl_context, timeout=30) as resp:
        data = resp.read()

    if is_gitiles:
        # Gitiles returns base64-encoded content
        data = base64.b64decode(data)

    return data


def download_file(filename: str, urls: dict[str, str]) -> None:
    """Download one file pair (Oracle left, Google right)."""
    print(f"[{filename}] 다운로드 시작...")

    left_path = os.path.join(LEFT_DIR, filename)
    right_path = os.path.join(RIGHT_DIR, filename)

    try:
        # OpenJDK (Oracle)
        data = _download_raw(urls["left"])
        with open(left_path, "wb") as f:
            f.write(data)
        print(f"  [Oracle]  ✓ {len(data):,} bytes")

        # AOSP (Google)
        data = _download_raw(urls["right"])
        with open(right_path, "wb") as f:
            f.write(data)
        print(f"  [Google]  ✓ {len(data):,} bytes")

        print(f"[{filename}] ✓ 완료")
    except Exception as e:
        print(f"[{filename}] ✗ 실패: {e}")


def main():
    print("Google vs. Oracle 테스트베드 구축을 시작합니다...\n")
    os.makedirs(LEFT_DIR, exist_ok=True)
    os.makedirs(RIGHT_DIR, exist_ok=True)

    with ThreadPoolExecutor(max_workers=5) as executor:
        for filename, urls in TARGET_FILES.items():
            executor.submit(download_file, filename, urls)

    print("\n테스트베드 구축 완료!")
    print(f"대조군 (Oracle): {LEFT_DIR}")
    print(f"실험군 (Google): {RIGHT_DIR}")
    print("\n[테스트 실행 방법]")
    print(f"diffinite {LEFT_DIR} {RIGHT_DIR} --deep --multi-channel -o oracle_report.pdf")


if __name__ == "__main__":
    main()