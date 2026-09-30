/**
 * Single place to change the public contact address.
 *
 * LAUNCH CHECK: this currently mirrors the repo's git identity
 * (iayushsharma10 / smartyayush333@gmail.com). Confirm Ayush wants exactly
 * this address published on a public site before launch — see
 * LAUNCH_BLOCKERS.md. No other email exists anywhere in this site.
 */
export const CONTACT_EMAIL = "smartyayush333@gmail.com"

export const CONTACT_MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(
  "Kestrel early access request",
)}`
