"use client";

import { useState } from "react";
import { Card } from "@/lib/ui/Card";
import { Button } from "@/lib/ui/Button";
import { registerPushSubscription, unregisterPushSubscription } from "@/lib/push/setup";
import { useRouter } from "next/navigation";

export default function ProfilePage(): JSX.Element {
  const router = useRouter();
  const [pushStatus, setPushStatus] = useState<"idle" | "loading" | "active" | "error">("idle");

  async function handleTogglePush() {
    setPushStatus("loading");
    const ok = pushStatus === "active"
      ? await unregisterPushSubscription()
      : await registerPushSubscription();
    setPushStatus(ok ? "active" : "error");
    if (ok) setTimeout(() => setPushStatus("idle"), 3000);
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-secondary-dark">Perfil</h1>
        <p className="text-sm text-gray-500">Configuración de la cuenta</p>
      </div>

      <Card header={<h2 className="font-semibold text-secondary-dark">Notificaciones</h2>}>
        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            Recibí alertas cuando haya productos con quiebre de stock o
            reportes importantes (disponible en F4).
          </p>
          <Button
            variant={pushStatus === "active" ? "secondary" : "primary"}
            onClick={handleTogglePush}
            disabled={pushStatus === "loading"}
          >
            {pushStatus === "loading"
              ? "Configurando..."
              : pushStatus === "active"
                ? "Desactivar alertas"
                : "Activar alertas"}
          </Button>
          {pushStatus === "error" && (
            <p className="text-xs text-red-500">
              No se pudo configurar. Probá desde otro navegador o dispositivo.
            </p>
          )}
          {pushStatus === "active" && (
            <p className="text-xs text-green-600">Alertas activadas ✓</p>
          )}
        </div>
      </Card>

      <Card header={<h2 className="font-semibold text-secondary-dark">Cuenta</h2>}>
        <Button variant="ghost" onClick={handleLogout}>
          Cerrar sesión
        </Button>
      </Card>
    </div>
  );
}
