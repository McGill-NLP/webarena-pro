import test from "node:test";
import assert from "node:assert/strict";

import { buildAppUrl, getAuthRedirectPath } from "../src/lib/navigation.mjs";

test("buildAppUrl keeps the current origin for auth redirects", () => {
  assert.equal(
    buildAppUrl("/login", "https://example.com/shared-with-me"),
    "https://example.com/login"
  );
});

test("getAuthRedirectPath normalizes missing leading slashes", () => {
  assert.equal(getAuthRedirectPath("signup"), "/signup");
  assert.equal(getAuthRedirectPath("/login"), "/login");
});
