# browser.py
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


def get_driver(user_agent=None):
    """Returns a fully silenced Chrome WebDriver instance."""
    logging.getLogger("selenium").setLevel(logging.CRITICAL)
    os.environ["WDM_LOG_LEVEL"] = "0"
    os.environ["WDM_PRINT_FIRST_LINE"] = "false"

    options = Options()
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    # Reduce popup blocking in the browser used by the TUI
    options.add_argument("--disable-popup-blocking")

    # Allow requests to localhost from pages served over HTTPS (mixed content)
    # This is intentionally permissive for local tooling; it's not recommended for production browsers.
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:5000")
    options.add_argument("--unsafely-treat-insecure-origin-as-secure=https://127.0.0.1:5000")

    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")

    service = Service(
        ChromeDriverManager().install(),
        log_output=os.devnull
    )

    driver = webdriver.Chrome(service=service, options=options)
    return driver


def close_driver(driver):
    """Safely close a selenium webdriver instance if possible."""
    try:
        if not driver:
            return
        try:
            # prefer quit
            driver.quit()
        except Exception:
            try:
                driver.close()
            except Exception:
                pass
    except Exception:
        # be safe: ignore all errors during driver shutdown
        pass