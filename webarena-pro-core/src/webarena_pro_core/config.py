LOGIN_CREDENTIALS = {
    "acidwave": {
        "username": "aciduser",
        "password": "aciduser",
    },
    "password-manager": {
        "username": "agent1",
        "password": "agentpass",
    },
    "nextcloud": {
        "maya_username": "maya.patel",
        "maya_password": "agentpass",
        "daniel_username": "daniel.brooks",
        "daniel_password": "agentpass",
    },
    "firefly": {
        "username": "test@example.com",
        "password": "R9WrgT2vkn63TDBV",
    },
    "travelmap": {
        "email": "avery@example.com",
        "password": "demo123",
    },
    "flight-search": {
        "passkey": "flyingagents",
    },
    "mattermost": {
        "username": "john.doe",
        "password": "User@Secure123",
    },
    "jobportal": {
        "username": "alice_seeker",
        "password": "DemoPass123!",
    },
    "thunderbird": {
        "username": "alice@techcorp.local",
        "password": "User@Secure123",
    },
    "immich": {
        "username": "agent1@immich.local",
        "password": "agent1password",
    },
    "metabase":  {
        "username": "admin@admin.com",
        "password": "apassword123",
    },
    "notion": {
        "email": "demo@webarena.local",
        "password": "password123",
    },
    "yt-lite": {
        "username": "seed_user",
        "password": "password",
    },
    "x-lite": {
        "username": "techvalueinvestor",
        "password": "password123",
    },
    "minerva-lite": {
        "student_id": "260123456",
        "student_password": "mcgill123",
        "advisor_id": "9801001",
        "advisor_password": "advisor123",
    },
    "peppermint": {
        "username": "james@peppermint.local",
        "password": "Password1!",
    },
    "penpot": {
        "email": "admin@penpot.local",
        "password": "Admin@Secure123",
    },
    "pipedrive": {
        "email": "admin@local.host",
        "password": "admin123",
    },
    "erp-next": {
        "username": "agent1@erpnext.local",
        "password": "User@Secure123",
    },
}

WEBSITE_CREDENTIALS = {
    "acidwave": [
        {"username": "aciduser", "password": "aciduser"},
    ],
    "password-manager": [
        {"username": "agent1", "password": "agentpass"},
    ],
    "nextcloud": [
        {"username": "maya.patel", "password": "agentpass"},
        {"username": "daniel.brooks", "password": "agentpass"},
        {"username": "admin", "password": "admin"},
    ],
    "flight-search": [
        {"passkey": "flyingagents"},
        # Evaluator alias: the api_registry templates log in with
        # auth_user="flyingagents" (login_user_key="passkey").
        {"username": "flyingagents", "password": "flyingagents"},
    ],
    "jobportal": [
        {
            "username": "employer_acme",
            "password": "DemoPass123!",
            "user_type": "employer",
        },
        {
            "username": "alice_seeker",
            "password": "DemoPass123!",
            "user_type": "job_seeker",
        },
    ],
    "thunderbird": [
        {"username": "alice@techcorp.local", "password": "User@Secure123"},
        {"username": "bob@techcorp.local", "password": "User@Secure123"},
        {"username": "carol@techcorp.local", "password": "User@Secure123"},
        {"username": "david@techcorp.local", "password": "User@Secure123"},
    ],
    "mattermost": [
        {"username": "admin", "password": "Admin@Secure123"},
        {"username": "john.doe", "password": "User@Secure123"},
        {"username": "jane.smith", "password": "User@Secure123"},
    ],
    "firefly": [
        {"email": "test@example.com", "password": "R9WrgT2vkn63TDBV"},
    ],
    "travelmap": [
        {"email": "avery@example.com", "password": "demo123"},
    ],
    "immich": [
        {"username": "agent1@immich.local", "password": "agent1password"},
        {"username": "admin@immich.local", "password": "webarena_admin"},
    ],
    "metabase": [
        {"username": "admin@admin.com", "password": "apassword123"},
    ],
    "mydrive": [
        {"email": "agent1@test.com", "password": "password", "username": "agent1"},
    ],
    "notion": [
        {"email": "demo@webarena.local", "password": "password123"},
    ],
    "yt-lite": [
        {"username": "seed_user", "password": "password"},
    ],
    "x-lite": [
        {"username": "techvalueinvestor", "password": "password123"},
        {"username": "airescientist", "password": "password123"},
    ],
    "minerva-lite": [
        {"username": "260123456", "password": "mcgill123"},
        {"username": "9801001", "password": "advisor123"},
    ],
    "peppermint": [
        {"username": "james@peppermint.local", "password": "Password1!"},
        {"username": "priya@peppermint.local", "password": "Password1!"},
        {"username": "marcus@peppermint.local", "password": "Password1!"},
        {"username": "admin@admin.com", "password": "1234"},
    ],
    "penpot": [
        {"username": "admin@penpot.local", "password": "Admin@Secure123"},
        {"username": "alice@designstudio.io", "password": "User@Secure123"},
    ],
    "pipedrive": [
        {"email": "admin@local.host", "password": "admin123"},
    ],
    "erp-next": [
        {"username": "agent1@erpnext.local", "password": "User@Secure123"},
        {"username": "agent2@erpnext.local", "password": "User@Secure123"},
        {"username": "agent3@erpnext.local", "password": "User@Secure123"},
        # Evaluator-only: the Frappe REST templates read as Administrator.
        {"username": "Administrator", "password": "admin"},
    ],
}

CREDENTIALS = LOGIN_CREDENTIALS


def get_website_credentials(website: str) -> dict[str, str] | None:
    if isinstance(CREDENTIALS, dict):
        credentials = CREDENTIALS.get(website)
        return credentials if isinstance(credentials, dict) else None

    if isinstance(CREDENTIALS, list):
        for credentials_by_site in CREDENTIALS:
            if not isinstance(credentials_by_site, dict):
                continue
            credentials = credentials_by_site.get(website)
            if isinstance(credentials, dict):
                return credentials

    return None


def get_login_credentials(website: str) -> list[dict[str, str]]:
    credentials = WEBSITE_CREDENTIALS.get(website, [])
    return [dict(credential) for credential in credentials]
