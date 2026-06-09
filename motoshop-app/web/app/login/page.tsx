"use client";

import { useState } from "react";
import { useAuthStore } from "@/lib/auth/store";
import { Button } from "@/lib/ui/Button";
import { Input } from "@/lib/ui/Input";
import { useToast } from "@/lib/ui/Toast";

export default function LoginPage(): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const setUser = useAuthStore((s) => s.setUser);
  const { addToast } = useToast();

  // NOTA: NO hacer auto-redirect a "/" si isAuthenticated viene en true desde
  // localStorage. Cuando la cookie httponly expira pero el store sigue
  // persistido, el middleware rebota a /login y el useEffect dispararía un
  // loop de hard nav que evita siquiera tipear en el formulario. El redirect
  // post-login vive en handleSubmit, que es el único caso donde lo necesitamos.

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrors({});

    // Fallback de autofill (Face ID en iOS Safari rellena el DOM pero no
    // siempre dispara onChange en React). Leemos del FormData del form real.
    const formData = new FormData(e.currentTarget);
    const usernameVal = (String(formData.get("username") ?? "") || username).trim();
    const passwordVal = String(formData.get("password") ?? "") || password;

    const newErrors: typeof errors = {};
    if (!usernameVal) newErrors.username = "Requerido";
    if (!passwordVal) newErrors.password = "Requerida";
    if (Object.keys(newErrors).length) {
      setErrors(newErrors);
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: usernameVal, password: passwordVal }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        addToast(data.detail ?? "Credenciales inválidas", "error");
        return;
      }

      setUser(data.sub ?? usernameVal, data.role ?? "vendedor");
      addToast("Bienvenido", "success");
      // Hard navigation: el cliente del App Router cachea /login y a veces
      // no invalida cuando la cookie httponly acaba de setearse en el mismo
      // ciclo. window.location fuerza un fresh request donde el middleware
      // ve la cookie y enruta a la home autenticada sin necesidad de refresh.
      window.location.assign("/");
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
            name="username"
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
            name="password"
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
