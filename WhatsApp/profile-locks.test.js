const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { isStaleProfileError, removeStaleProfileLocks } = require("./profile-locks");

test("recognizes Chromium profile singleton lock errors", () => {
  assert.equal(
    isStaleProfileError(new Error("The profile appears to be in use by another Chromium process")),
    true
  );
  assert.equal(isStaleProfileError(new Error("Network request failed")), false);
});

test("removes Chromium lock metadata without touching saved profile data", async () => {
  const profilePath = await fs.mkdtemp(path.join(os.tmpdir(), "bandes-profile-"));
  try {
    await fs.symlink("previous-host-30", path.join(profilePath, "SingletonLock"));
    await fs.symlink("cookie-id", path.join(profilePath, "SingletonCookie"));
    await fs.symlink("/tmp/chromium/SingletonSocket", path.join(profilePath, "SingletonSocket"));
    await fs.writeFile(path.join(profilePath, "DevToolsActivePort"), "9222\n");
    await fs.writeFile(path.join(profilePath, "Preferences"), "{}");

    assert.equal(await removeStaleProfileLocks(profilePath), true);
    await assert.rejects(fs.lstat(path.join(profilePath, "SingletonLock")), { code: "ENOENT" });
    await assert.rejects(fs.lstat(path.join(profilePath, "DevToolsActivePort")), { code: "ENOENT" });
    assert.equal(await fs.readFile(path.join(profilePath, "Preferences"), "utf8"), "{}");
  } finally {
    await fs.rm(profilePath, { recursive: true, force: true });
  }
});

test("does not remove a lock owned by a running local Chromium process", async () => {
  const profilePath = await fs.mkdtemp(path.join(os.tmpdir(), "bandes-profile-"));
  const lockPath = path.join(profilePath, "SingletonLock");
  try {
    await fs.symlink(`${os.hostname()}-${process.pid}`, lockPath);
    await assert.rejects(
      removeStaleProfileLocks(profilePath, async () => true),
      /Chromium profile lock belongs to a running local process/
    );
    assert.equal((await fs.lstat(lockPath)).isSymbolicLink(), true);
  } finally {
    await fs.rm(profilePath, { recursive: true, force: true });
  }
});
