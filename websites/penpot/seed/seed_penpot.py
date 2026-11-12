#!/usr/bin/env python3
"""
Penpot Seed Data Script
=======================
Populates a Penpot instance with realistic mock data for agent testing.
Targets the backend RPC API directly (port 6060, no nginx needed).

Usage:
    python seed_penpot.py --url http://localhost:6060 --seed-file ../seed_data.json

Registration flow (Penpot 2.14.1):
    POST /api/rpc/command/prepare-register-profile  {email, password, fullname}  -> {token}
    POST /api/rpc/command/register-profile          {token}                      -> profile
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class PenpotSeeder:
    def __init__(self, base_url: str, seed_file: str):
        self.base_url = base_url.rstrip("/")
        self.rpc = f"{self.base_url}/api/rpc/command"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        with open(seed_file) as f:
            self.data = json.load(f)

        self.profile_ids: dict[str, str] = {}   # username -> id
        self.team_ids:    dict[str, str] = {}   # team name -> id
        self.project_ids: dict[str, str] = {}   # "team/project" -> id

    # ── HTTP helpers ──────────────────────────────────────────────────────────
    def _post(self, cmd: str, payload: dict) -> requests.Response:
        return self.session.post(f"{self.rpc}/{cmd}", json=payload)

    def _get(self, cmd: str, params: dict | None = None) -> requests.Response:
        return self.session.get(f"{self.rpc}/{cmd}", params=params)

    # ── Server readiness ──────────────────────────────────────────────────────
    def wait_for_server(self, timeout: int = 180):
        log.info("Waiting for Penpot backend at %s...", self.base_url)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = self.session.get(f"{self.rpc}/get-profile", timeout=5)
                if r.status_code in (200, 401, 403):
                    log.info("Backend is ready (HTTP %s).", r.status_code)
                    return
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(3)
        log.error("Timed out after %ds waiting for backend.", timeout)
        sys.exit(1)

    # ── Auth ──────────────────────────────────────────────────────────────────
    def register(self, email: str, password: str, fullname: str) -> str | None:
        """Register a new user; return profile id or None if already exists."""
        # Step 1: prepare (get a short-lived JWT token)
        r = self._post("prepare-register-profile", {
            "email": email,
            "password": password,
            "fullname": fullname,
        })
        if r.status_code not in (200, 201):
            log.debug("  prepare-register failed for %s: %s", email, r.text[:200])
            return None
        token = r.json().get("token") if isinstance(r.json(), dict) else None
        if not token:
            # transit+json: the list form ["^ ", "~:token", "..."]
            data = r.json()
            if isinstance(data, list) and "~:token" in data:
                token = data[data.index("~:token") + 1]
        if not token:
            log.warning("  No token in prepare-register response for %s", email)
            return None

        # Step 2: complete registration
        r = self._post("register-profile", {
            "token": token,
            "accept-newsletter-subscription": False,
        })
        if r.status_code in (200, 201):
            data = r.json()
            uid = data.get("id") if isinstance(data, dict) else None
            if not uid and isinstance(data, list) and "~:id" in data:
                uid = data[data.index("~:id") + 1]
            log.info("  Registered: %s", email)
            return uid
        log.debug("  register-profile failed for %s: %s", email, r.text[:200])
        return None

    def login(self, email: str, password: str) -> str | None:
        r = self._post("login-with-password", {"email": email, "password": password})
        if r.status_code == 200:
            data = r.json()
            uid = data.get("id") if isinstance(data, dict) else None
            if uid:
                log.debug("  Logged in as %s", email)
                return uid
        log.warning("  Login failed for %s: %s", email, r.status_code)
        return None

    def logout(self):
        self._post("logout", {})

    # ── Personal team ─────────────────────────────────────────────────────────
    def get_personal_team_id(self) -> str | None:
        """Return the id of the currently-logged-in user's personal (default) team."""
        r = self._get("get-teams")
        if r.status_code != 200:
            log.warning("  get-teams failed: %s", r.status_code)
            return None
        data = r.json()
        teams = data if isinstance(data, list) else []
        for team in teams:
            if isinstance(team, dict) and team.get("is-default"):
                return team.get("id")
        return None

    # ── Teams ─────────────────────────────────────────────────────────────────
    def create_team(self, name: str) -> str | None:
        r = self._post("create-team", {"name": name})
        if r.status_code in (200, 201):
            data = r.json()
            tid = data.get("id") if isinstance(data, dict) else None
            log.info("  Created team: %s", name)
            return tid
        log.warning("  create-team failed for '%s': %s", name, r.text[:200])
        return None

    # ── Projects ──────────────────────────────────────────────────────────────
    def create_project(self, team_id: str, name: str) -> str | None:
        r = self._post("create-project", {"team-id": team_id, "name": name})
        if r.status_code in (200, 201):
            data = r.json()
            pid = data.get("id") if isinstance(data, dict) else None
            log.info("    Created project: %s", name)
            return pid
        log.warning("    create-project failed for '%s': %s", name, r.text[:200])
        return None

    # ── Files ─────────────────────────────────────────────────────────────────
    def create_file(self, project_id: str, name: str, is_shared: bool = False) -> str | None:
        r = self._post("create-file", {
            "project-id": project_id,
            "name": name,
            "is-shared": is_shared,
        })
        if r.status_code in (200, 201):
            data = r.json()
            fid = data.get("id") if isinstance(data, dict) else None
            log.info("      Created file: %s", name)
            return fid
        log.warning("      create-file failed for '%s': %s", name, r.text[:200])
        return None

    # ── Main pipeline ─────────────────────────────────────────────────────────
    def seed(self):
        log.info("=" * 60)
        log.info("Penpot Seed Data Loader")
        log.info("=" * 60)

        self.wait_for_server()

        all_users = [self.data["admin"]] + self.data["users"]

        # ── Register all users ───────────────────────────────────────────────
        log.info("Registering %d users...", len(all_users))
        for user in all_users:
            key = user.get("username", user["email"])
            uid = self.register(user["email"], user["password"], user["fullname"])
            if uid:
                self.profile_ids[key] = uid
            else:
                # Already exists — log in to get the id
                cookies_backup = dict(self.session.cookies)
                uid = self.login(user["email"], user["password"])
                if uid:
                    self.profile_ids[key] = uid
                    self.logout()
                    self.session.cookies.clear()
                    for k, v in cookies_backup.items():
                        self.session.cookies.set(k, v)

        log.info("Profiles ready: %d", len(self.profile_ids))

        # ── Create teams, projects, files ────────────────────────────────────
        for team_data in self.data.get("teams", []):
            owner_key = team_data.get("owner", "admin")
            owner_user = next(
                (u for u in all_users if u.get("username", u["email"]) == owner_key),
                self.data["admin"],
            )

            log.info("Team '%s' (owner: %s)...", team_data["name"], owner_key)
            self.login(owner_user["email"], owner_user["password"])

            team_id = self.create_team(team_data["name"])
            if not team_id:
                self.logout()
                continue
            self.team_ids[team_data["name"]] = team_id

            for project_data in team_data.get("projects", []):
                project_id = self.create_project(team_id, project_data["name"])
                if not project_id:
                    continue
                self.project_ids[f"{team_data['name']}/{project_data['name']}"] = project_id

                for file_data in project_data.get("files", []):
                    self.create_file(
                        project_id,
                        file_data["name"],
                        file_data.get("is_shared", False),
                    )

            self.logout()

        # ── Personal projects for each user ───────────────────────────────────
        log.info("Creating personal projects...")
        for user in all_users:
            personal_projects = user.get("personal_projects", [])
            if not personal_projects:
                continue
            key = user.get("username", user["email"])
            self.login(user["email"], user["password"])
            personal_team_id = self.get_personal_team_id()
            if not personal_team_id:
                log.warning("  Could not find personal team for %s", key)
                self.logout()
                continue
            log.info("  User '%s' personal team: %s", key, personal_team_id)
            for project_data in personal_projects:
                project_id = self.create_project(personal_team_id, project_data["name"])
                if not project_id:
                    continue
                self.project_ids[f"{key}/{project_data['name']}"] = project_id
                for file_data in project_data.get("files", []):
                    self.create_file(
                        project_id,
                        file_data["name"],
                        file_data.get("is_shared", False),
                    )
            self.logout()

        # ── Summary ──────────────────────────────────────────────────────────
        log.info("=" * 60)
        log.info("Seeding complete!")
        log.info("  Profiles: %d", len(self.profile_ids))
        log.info("  Teams:    %d", len(self.team_ids))
        log.info("  Projects: %d", len(self.project_ids))
        log.info("=" * 60)

        ids_file = Path(__file__).parent / "profile_ids.json"
        with open(ids_file, "w") as f:
            json.dump({"profile_ids": self.profile_ids, "team_ids": self.team_ids}, f, indent=2)
        log.info("IDs written to: %s", ids_file)

    # ── Team membership SQL ───────────────────────────────────────────────────
    def generate_membership_sql(self) -> str:
        lines = [
            "-- Team membership SQL (generated by seed_penpot.py)",
            "",
        ]
        for team_data in self.data.get("teams", []):
            team_name = team_data["name"]
            for member in team_data.get("members", []):
                username = member["username"]
                role = member["role"]
                user = next(
                    (u for u in [self.data["admin"]] + self.data["users"]
                     if u.get("username", u["email"]) == username),
                    None,
                )
                if not user:
                    continue
                email = user["email"]
                is_admin = "true" if role == "admin" else "false"
                can_edit = "true" if role in ("editor", "admin") else "false"
                lines.append(
                    f"INSERT INTO team_profile_rel "
                    f"(team_id, profile_id, is_owner, is_admin, can_edit, created_at, updated_at) "
                    f"SELECT t.id, p.id, false, {is_admin}, {can_edit}, NOW(), NOW() "
                    f"FROM team t, profile p "
                    f"WHERE t.name = '{team_name}' AND p.email = '{email}' "
                    f"ON CONFLICT (team_id, profile_id) DO NOTHING;"
                )
        return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Seed a Penpot instance with mock data.")
    parser.add_argument("--url", default="http://localhost:6060")
    parser.add_argument(
        "--seed-file",
        default=str(Path(__file__).parent.parent / "seed_data.json"),
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--generate-sql", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    seeder = PenpotSeeder(args.url, args.seed_file)

    if args.generate_sql:
        print(seeder.generate_membership_sql())
        return

    seeder.seed()


if __name__ == "__main__":
    main()
