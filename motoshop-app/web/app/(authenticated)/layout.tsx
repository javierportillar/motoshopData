"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Navigation, gerenteNavItems, vendedorNavItems } from "@/components/ui/Navigation";
import { useAuthStore } from "@/lib/auth/store";
import { OfflineQueueBadge } from "@/components/OfflineQueueBadge";
import { QueueScheduler } from "@/components/QueueScheduler";

export default function AuthenticatedLayout({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const router = useRouter();
  const role = useAuthStore((s) => s.role);
  const logout = useAuthStore((s) => s.logout);

  function handleLogout(): void {
    logout();
    router.push("/login");
  }

  const items = role === "vendedor" ? vendedorNavItems() : gerenteNavItems();

  return (
    <>
      <Navigation items={items} role={(role as "vendedor" | "admin" | "gerente") ?? "gerente"} onLogout={handleLogout} />
      <main className="mx-auto max-w-lg px-4 pb-20 pt-4 lg:ml-60 lg:max-w-4xl lg:pb-8">
        {children}
      </main>
      <OfflineQueueBadge />
      <QueueScheduler />
    </>
  );
}
