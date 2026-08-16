/**
 * Gmail deep-linking helpers optimized for iOS Safari (Gmail iOS App) & Desktop browsers.
 */

export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function getGmailUrl(messageId: string, accountIndex = 0): string {
  const cleanId = (messageId || "").trim();
  return `https://mail.google.com/mail/u/${accountIndex}/#all/${encodeURIComponent(cleanId)}`;
}

export function openInGmail(messageId: string, accountIndex = 0): void {
  if (!messageId) return;
  const url = getGmailUrl(messageId, accountIndex);

  // On iOS Safari, standard window.location.href or direct top-level navigation
  // allows iOS Universal Links to immediately launch the native Gmail app.
  // Using target="_blank" on iOS Safari often bypasses the app and opens a browser tab.
  if (isIOS()) {
    window.location.href = url;
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
