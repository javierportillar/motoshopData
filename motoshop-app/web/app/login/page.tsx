"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuthStore } from "@/lib/auth/store";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import { useToast } from "@/lib/ui/Toast";

/** Decodifica payload de JWT sin verificar firma (solo para UI). */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const base64 = token.split(".")[1];
    if (!base64) return null;
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

export default function LoginPage(): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);
  const { addToast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    const newErrors: typeof errors = {};
    if (!username.trim()) newErrors.username = "Requerido";
    if (!password) newErrors.password = "Requerida";
    if (Object.keys(newErrors).length) {
      setErrors(newErrors);
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        addToast(data.detail ?? "Credenciales inválidas", "error");
        return;
      }

      const payload = decodeJwtPayload(data.access_token);
      const sub = (payload?.sub as string) ?? username;
      const role = (payload?.role as string) ?? "vendedor";
      setUser(sub, role);
      addToast("Bienvenido", "success");
      router.push("/");
    } catch {
      addToast("Error de conexión", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary text-2xl font-bold text-white shadow-lg">
            M
          </div>
          <h1 className="text-2xl font-bold text-secondary-dark">MotoShop</h1>
          <p className="mt-1 text-sm text-gray-500">
            Consulta de catálogo y stock
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Usuario"
            placeholder="Tu usuario"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            error={errors.username}
            autoComplete="username"
            autoFocus
            icon={
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            }
          />

          <Input
            label="Contraseña"
            type="password"
            placeholder="Tu contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.password}
            autoComplete="current-password"
          />

          <Button
            type="submit"
            loading={loading}
            className="w-full"
            size="lg"
          >
            Iniciar sesión
          </Button>
        </form>
      </div>
    </main>
  );
}
