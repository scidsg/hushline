#!/usr/bin/env python
from typing import List, Optional, Tuple, cast

from flask import current_app
from sqlalchemy.sql import exists

from hushline import create_app
from hushline.db import db
from hushline.model import Tier, User, Username
from hushline.storage import S3Driver, public_store


def main() -> None:
    print("Adding dev data")
    create_app().app_context().push()
    create_users()
    create_tiers()
    create_localstack_buckets()


def create_users() -> None:
    users = [
        {
            "username": "admin",
            "password": "Test-testtesttesttest-1",
            "is_admin": True,
            "is_verified": True,
            "display_name": "Hush Line Admin",
            "bio": "Hush Line administrator account.",
        },
        {
            "username": "artvandelay",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Art Vandelay",
            "bio": (
                "Art is the CEO of Vandelay Industries, an international "
                "importing/exporting company. Potato and corn chips, "
                "diapers, and matches."
            ),
        },
        {
            "username": "jerryseinfeld",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Jerry Seinfeld",
            "bio": (
                "I'm a neurotic stand-up comic who loves cereal and Superman. "
                "Use my tip line to rant about nothing—it's a show about nothing!"
            ),
            "extra_fields": [
                ("Website", "https://jerryseinfeld.com", True),
                ("Signal", "@Jerry.01", False),
            ],
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "georgecostanza",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "George Costanza",
            "bio": (
                "Perpetually unemployed, living with my parents, but I have "
                "big plans. Use my tip line if you spot shrinkage or contraband Twix."
            ),
            "extra_fields": [
                ("Website", "https://yankees.com", False),
                ("Signal", "@George.99", False),
            ],
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "elainebenes",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Elaine Benes",
            "bio": (
                "I dance like nobody’s watching—because they shouldn’t. "
                "Send tips on questionable sponges."
            ),
            "extra_fields": [
                ("Email", "elaine@pendant.com", False),
            ],
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "cosmokramer",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Cosmo Kramer",
            "bio": (
                "I'm the wacky neighbor with grand schemes (pizza bagels, anyone?). "
                "Hit my tip line if you discover the next big invention idea."
            ),
            "extra_fields": [
                ("Business Ideas", "Homemade Pizzeria", False),
            ],
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "newman",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Postal Employee Newman",
            "bio": "Postal worker and sworn enemy to Jerry. Hello, Jerry.",
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "frankcostanza",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Frank Costanza",
            "bio": (
                "I invented the manzier and celebrate Festivus. "
                "Tip line for any beef you got—SERENITY NOW!"
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "michaelbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Michael Bluth",
            "bio": (
                "Holding this family together with hopes, dreams, and bad magic shows. "
                "Use my tip line to warn me if Gob’s illusions go too far."
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "gobbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Gob Bluth",
            "bio": (
                "I'm an illusionist, not a magician—tricks are what a hooker does for money. "
                "Tip me off to any half-decent gigs or adorable rabbits."
            ),
        },
        {
            "username": "busterbluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Buster Bluth",
            "bio": (
                "Motherboy champion and proud hook-hand owner. "
                "Use my tip line for anything related to juice boxes or loose seals."
            ),
        },
        {
            "username": "lucillebluth",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Lucille Bluth",
            "bio": (
                "Manipulative matriarch with a taste for vodka. "
                "Notify me about 2-for-1 martini deals."
            ),
            "extra_fields": [
                ("Favorite Drink", "Vodka Martini", True),
            ],
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "tobiasfunke",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": False,
            "display_name": "Tobias Fünke",
            "bio": (
                "Never-nude, aspiring actor, and first analrapist. "
                "Tip me on potential casting calls or discreet cutoffs sales."
            ),
        },
        {
            "username": "larrydavid",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Larry David",
            "bio": (
                "I’m just trying to say what everyone’s thinking—sometimes it’s trouble. "
                "Use my tip line for petty gripes or leftover 'spite store' leads."
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "jeffgreene",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Jeff Greene",
            "bio": (
                "Larry’s longtime manager, often enabling awkward situations. "
                "Send me tips on hush-hush deals or who’s offended Larry this week."
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "leonblack",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Leon Black",
            "bio": (
                "I mooch off Larry and offer streetwise pep talks. "
                "Hit me with tips on side hustles or a new 'shit bow' story."
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "dwightschrute",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Dwight Schrute",
            "bio": (
                "Assistant to the Regional Manager. "
                "Contact my tip line for beet sales or suspicious behavior from Jim."
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
        {
            "username": "martymcfly",
            "password": "Test-testtesttesttest-1",
            "is_admin": False,
            "is_verified": True,
            "display_name": "Marty McFly",
            "bio": (
                "Time-traveling teen with a hoverboard. "
                "Use my tip line if someone calls me chicken or there's a DeLorean sighting."
            ),
            "pgp_key": (
                "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
                "Version: ProtonMail\n"
                "\n"
                "xjMEXiN/UBYJKwYBBAHaRw8BAQdAkalcTpVnOJSv6Sz7e1U1PSzLFoRLfUAH\n"
                "3YKdavTR7iDNL2dsZW5uLnNvcnJlbnRpbm9AcG0ubWUgPGdsZW5uLnNvcnJl\n"
                "bnRpbm9AcG0ubWU+wngEEBYKACAFAl4jf1AGCwkHCAMCBBUICgIEFgIBAAIZ\n"
                "AQIbAwIeAQAKCRCcnhzX3YAXZHoAAP99IptrvyKxZn1fv8WncHvNV2oP+pyh\n"
                "YsKmPr4Xv/O4ggEA3dGQdbke3zhysfRx/S95UwzH0TrLU7mTQif1a0NFgwjC\n"
                "qAQQFggAWgUCY08+AAkQ2AbBr1l46McWIQQKhlL+XVM4YFeJn+nYBsGvWXjo\n"
                "xywcb3BlbnBncC1jYUBwcm90b24ubWUgPG9wZW5wZ3AtY2FAcHJvdG9uLm1l\n"
                "PgWDBAtmqgAA2E0A/R2vXOoqUUyRuFhEzKUaNWMLeWBiqLHIxLO1W1jBmeei\n"
                "AQC8C3idUvM7IVaMW3K8Q0x5Dx+/c0C6jqG0iZyxE+g7Ac44BF4jf1ASCisG\n"
                "AQQBl1UBBQEBB0CN1gW+5a1yrHvTQ4SSb9DG4qjDdANSNTD5uAegyYkMcAMB\n"
                "CAfCYQQYFggACQUCXiN/UAIbDAAKCRCcnhzX3YAXZL5XAQCE5wzSF02WECYv\n"
                "O9ad2q095aqlNypwHbMn8ttsMhQ97QD9HtC+fbcLAb0DHRsKuL9DmJwGj45E\n"
                "QsxwmU8lzRZlpgg=\n"
                "=cngN\n"
                "-----END PGP PUBLIC KEY BLOCK-----"
            ),
        },
    ]

    MAX_EXTRA_FIELDS = 4

    for data in users:
        # Extract and cast basic user information
        username = cast(str, data["username"])
        is_admin = cast(bool, data["is_admin"])
        display_name = cast(str, data.get("display_name", username))
        bio = cast(str, data.get("bio", ""))[:250]  # Ensure truncation to 250 characters
        is_verified = cast(bool, data.get("is_verified", False))
        extra_fields = cast(List[Tuple[str, str, bool]], data.get("extra_fields", []))
        pgp_key = cast(Optional[str], data.get("pgp_key"))  # Optional PGP key

        # Check if user already exists
        if not db.session.query(exists().where(Username._username == username)).scalar():
            # Create a new user
            user = User(password=password, is_admin=is_admin)

            # Assign PGP key if provided
            if pgp_key:
                user.pgp_key = pgp_key

            db.session.add(user)
            db.session.flush()

            # Create primary username
            un1 = Username(
                user_id=user.id,
                _username=username,
                display_name=display_name,
                bio=bio,
                is_primary=True,
                show_in_directory=True,
                is_verified=is_verified,
            )

            # Create alias username
            un2 = Username(
                user_id=user.id,
                _username=f"{username}-alias",
                display_name=f"{display_name} (Alias)",
                bio=f"{bio} (Alias)",
                is_primary=False,
                show_in_directory=True,
                is_verified=False,
            )

            # Assign extra fields to the primary username
            for i, (label, value, verified) in enumerate(extra_fields, start=1):
                if i > MAX_EXTRA_FIELDS:
                    break  # Stop if maximum number of extra fields is exceeded
                setattr(un1, f"extra_field_label{i}", label)
                setattr(un1, f"extra_field_value{i}", value)
                setattr(un1, f"extra_field_verified{i}", verified)

            # Add the new usernames to the database
            db.session.add(un1)
            db.session.add(un2)
            db.session.commit()

            print(f"Test user created:\n  username = {username}\n  password = {password}")
        else:
            print(f"User already exists: {username}")


def create_tiers() -> None:
    tiers = [
        {
            "name": "Free",
            "monthly_amount": 0,
        },
        {
            "name": "Business",
            "monthly_amount": 2000,
        },
    ]
    for data in tiers:
        name = cast(str, data["name"])
        monthly_amount = cast(int, data["monthly_amount"])
        if not db.session.scalar(db.exists(Tier).where(Tier.name == name).select()):
            tier = Tier(name, monthly_amount)
            db.session.add(tier)
            db.session.commit()

        print(f"Tier:\n  name = {name}\n  monthly_amount = {monthly_amount}")

    print("Dev data added")


def create_localstack_buckets() -> None:
    driver = public_store._driver
    if isinstance(driver, S3Driver):
        bucket = current_app.config[driver._config_name("S3_BUCKET")]
        driver._client.create_bucket(Bucket=bucket)
        print(f"Public storage bucket: {bucket}")


if __name__ == "__main__":
    main()
