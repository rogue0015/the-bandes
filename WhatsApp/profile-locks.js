const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");

const STALE_PROFILE_ERROR = /profile appears to be in use|process_singleton_posix/i;
const PROFILE_LOCK_FILES = [
  "SingletonLock",
  "SingletonCookie",
  "SingletonSocket",
  "DevToolsActivePort",
];

function isStaleProfileError(error) {
  return STALE_PROFILE_ERROR.test(String(error?.message || error));
}

async function isRunningChromium(pid) {
  try {
    const stat = await fs.readFile(`/proc/${pid}/stat`, "utf8");
    const processState = stat.slice(stat.lastIndexOf(")") + 2).split(" ", 1)[0];
    if (processState === "Z") return false;
    const command = await fs.readFile(`/proc/${pid}/cmdline`, "utf8");
    return /chrom(e|ium)/i.test(command);
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

async function removeStaleProfileLocks(profilePath, isProcessRunning = isRunningChromium) {
  const lockPath = path.join(profilePath, "SingletonLock");
  let lockOwner;
  try {
    lockOwner = await fs.readlink(lockPath);
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }

  const ownerMatch = /^(.+)-(\d+)$/.exec(lockOwner);
  if (
    ownerMatch
    && ownerMatch[1] === os.hostname()
    && await isProcessRunning(ownerMatch[2])
  ) {
    throw new Error("Chromium profile lock belongs to a running local process");
  }

  for (const filename of PROFILE_LOCK_FILES) {
    try {
      await fs.unlink(path.join(profilePath, filename));
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  return true;
}

module.exports = { isStaleProfileError, removeStaleProfileLocks };
