import re

from playwright.sync_api import Page, expect
from tenacity import RetryCallState, retry, stop_after_attempt, wait_random_exponential

BASE_URL = "http://127.0.0.1:8080"


def log_retry_error(retry_state: RetryCallState) -> None:
    if retry_state is None or retry_state.outcome is None:
        return
    print(f"Retrying due to error: {retry_state.outcome.exception()}")


@retry(
    wait=wait_random_exponential(min=1, max=60),
    stop=stop_after_attempt(3),
    retry_error_callback=log_retry_error,
)
def test_enable_2fa_has_back_button(page: Page, user_password: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.get_by_label("Username").fill("test")
    page.get_by_label("Password").fill(user_password)
    page.get_by_role("button", name="Login").click()

    page.goto(f"{BASE_URL}/settings/enable-2fa", wait_until="domcontentloaded")
    expect(page.get_by_text("Back to Authentication")).to_be_visible()


@retry(
    wait=wait_random_exponential(min=1, max=60),
    stop=stop_after_attempt(3),
    retry_error_callback=log_retry_error,
)
def test_enable_2fa_back_button_returns(page: Page, user_password: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.get_by_label("Username").fill("test")
    page.get_by_label("Password").fill(user_password)
    page.get_by_role("button", name="Login").click()

    page.goto(f"{BASE_URL}/settings/enable-2fa", wait_until="domcontentloaded")
    page.get_by_text("Back to Authentication").click()
    expect(page).to_have_url(re.compile(".*auth"))
