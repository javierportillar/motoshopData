"use client";

/**
 * Estructura preparatoria para push notifications (DT-F3-11).
 *
 * En F3 SOLO se prepara:
 *   - SW registra subscription
 *   - API guarda subscription (endpoint placeholder)
 *   - Botón "Activar alertas" en perfil
 *
 * NO se disparan notificaciones hasta F4 (alertas de quiebre).
 */

const PUBLIC_VAPID_KEY = "BDdP0k_R4c5z7X2oQ9yT8wA3sE5rF6gH1jK2lQ3wE4rT5yU6iO7pA8sD9fG0hJ1kL2"; // placeholder

export interface PushSubscriptionData {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

export async function registerPushSubscription(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    console.log("Push not supported in this browser");
    return false;
  }

  try {
    const registration = await navigator.serviceWorker.ready;

    // Check existing subscription
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
      // Already subscribed — could send to server if not already saved
      return true;
    }

    // Request new subscription
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(PUBLIC_VAPID_KEY) as BufferSource,
    });

    // Send to API (placeholder endpoint)
    const subData: PushSubscriptionData = {
      endpoint: subscription.endpoint,
      keys: {
        p256dh: arrayBufferToBase64(subscription.getKey("p256dh")!),
        auth: arrayBufferToBase64(subscription.getKey("auth")!),
      },
    };

    const resp = await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subData),
    });

    return resp.ok;
  } catch (err) {
    console.error("Push subscription failed:", err);
    return false;
  }
}

export async function unregisterPushSubscription(): Promise<boolean> {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await subscription.unsubscribe();
      await fetch("/api/push/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
    }
    return true;
  } catch (err) {
    console.error("Push unsubscription failed:", err);
    return false;
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from(rawData.split("").map((c) => c.charCodeAt(0)));
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
