"""
Unit tests for Windows Credential Vault (DPAPI / keyring adapter).
AgentShield Tier-1 Security Compliance.
"""

from unittest.mock import patch

from src.infrastructure.credentials.windows_vault import WindowsCredentialVault


def test_windows_vault_token_lifecycle():
    vault = WindowsCredentialVault()
    profile_id = 9999

    # In test environment, mock keyring so we don't pollute host OS credential manager
    fake_storage = {}

    def fake_set_password(service, username, password):
        fake_storage[(service, username)] = password

    def fake_get_password(service, username):
        return fake_storage.get((service, username))

    def fake_delete_password(service, username):
        fake_storage.pop((service, username), None)

    with (
        patch("keyring.set_password", side_effect=fake_set_password),
        patch("keyring.get_password", side_effect=fake_get_password),
        patch("keyring.delete_password", side_effect=fake_delete_password),
    ):
        # 1. Save tokens
        vault.save_oauth_tokens(
            profile_id=profile_id,
            access_token="act_test_1234567890",
            refresh_token="rft_test_0987654321",
            client_secret="sec_test_abcdef",
        )

        # 2. Retrieve tokens
        tokens = vault.get_oauth_tokens(profile_id)
        assert tokens is not None
        assert tokens["access_token"] == "act_test_1234567890"
        assert tokens["refresh_token"] == "rft_test_0987654321"
        assert tokens["client_secret"] == "sec_test_abcdef"

        # 3. Clear tokens
        vault.clear_oauth_tokens(profile_id)
        assert vault.get_oauth_tokens(profile_id) is None
