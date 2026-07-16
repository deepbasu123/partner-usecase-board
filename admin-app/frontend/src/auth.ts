/** True only for exact ...@databricks.com addresses (case-insensitive). */
export function isDatabricksEmail(email?: string | null): boolean {
  if (!email) return false;
  return email.trim().toLowerCase().endsWith("@databricks.com");
}
