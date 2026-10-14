# Security-key availability UI

Screenshots use authenticated Flask-rendered pages, synthetic test-account data, and the real
compiled frontend assets in Chromium with JavaScript enabled. No production account data or
credentials are included. Enrollment behavior is separately verified by the real browser tests.

| State                                                            | Screenshot                                             |
| ---------------------------------------------------------------- | ------------------------------------------------------ |
| Enrollment available, authentication settings                    | [Available settings](available-authentication.png)     |
| Enrollment available, after identity confirmation                | [Enrollment form](available-enrollment.png)            |
| Enrollment unavailable, no existing security keys                | [Unavailable settings](unavailable-authentication.png) |
| Enrollment unavailable, existing key after identity confirmation | [Existing-key management](existing-key-management.png) |
