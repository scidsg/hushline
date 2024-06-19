import bs4
import pyotp
from flask.testing import FlaskClient

# Import models and other modules
from hushline.model import User


def test_enable_2fa(client: FlaskClient) -> None:
    # Register a new user
    user_data = {"username": "test_user", "password": "SecurePassword123!"}
    response = client.post("/register", data=user_data, follow_redirects=True)
    assert response.status_code == 200

    # Verify user is added to the database
    user = User.query.filter_by(primary_username="test_user").first()
    assert user is not None
    assert user.primary_username == "test_user"

    # And 2FA is disabled
    assert user._totp_secret is None

    # Login
    login_data = {"username": "test_user", "password": "SecurePassword123!"}
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200

    # Enable 2FA
    enable_2fa_response = client.post("/settings/toggle-2fa", follow_redirects=True)
    assert enable_2fa_response.status_code == 200
    assert "Scan the QR code with your 2FA app" in enable_2fa_response.text

    # Get the 2FA code from the HTML
    soup = bs4.BeautifulSoup(enable_2fa_response.data, "html.parser")
    totp_secret = soup.select_one(".totp-secret").text

    # Verify the 2FA code
    totp = pyotp.TOTP(totp_secret)
    verification_code = totp.now()

    # Verify the 2FA code
    verify_2fa_data = {"verification_code": verification_code}
    verify_2fa_response = client.post(
        "/settings/enable-2fa", data=verify_2fa_data, follow_redirects=True
    )
    assert verify_2fa_response.status_code == 200

    # Logging in should now require 2FA
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    assert "Enter your 2FA Code" in login_response.text
