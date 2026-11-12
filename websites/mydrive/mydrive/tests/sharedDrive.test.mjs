import test from "node:test";
import assert from "node:assert/strict";

import { getSharedItemCapabilities } from "../src/lib/sharedDrive.mjs";

test("shared root folders with edit permission stay editable for sharees", () => {
  assert.deepEqual(
    getSharedItemCapabilities({
      directShare: true,
      isOwned: false,
      isSharedRoot: true,
      itemKind: "folder",
      permission: "EDIT",
      currentPermission: "READ",
    }),
    { canEdit: true, canDelete: false }
  );
});

test("shared root files stay non-editable for sharees even with edit access", () => {
  assert.deepEqual(
    getSharedItemCapabilities({
      directShare: true,
      isOwned: false,
      isSharedRoot: true,
      itemKind: "file",
      permission: "EDIT",
      currentPermission: "READ",
    }),
    { canEdit: false, canDelete: false }
  );
});

test("shared subfolders inherit edit capability from the current shared context", () => {
  assert.deepEqual(
    getSharedItemCapabilities({
      isOwned: false,
      isSharedRoot: false,
      itemKind: "file",
      currentPermission: "EDIT",
    }),
    { canEdit: true, canDelete: false }
  );
});
