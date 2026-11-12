import crypto from "crypto";

const DEFAULT_SALT = "dev_salt_change_me";

export function hashPassword(password: string, salt = process.env.PASSWORD_SALT ?? DEFAULT_SALT) {
  return crypto.createHmac("sha256", salt).update(password).digest("hex");
}

export function verifyPassword(password: string, hash: string) {
  return hashPassword(password) === hash;
}
