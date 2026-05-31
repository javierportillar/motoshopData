import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://motoshop-cloud-api.onrender.com";

function decodeToken(token: string): Record<string, unknown> {
  try {
    const b64 = token.split(".")[1] ?? "";
    return JSON.parse(Buffer.from(b64, "base64").toString("utf-8"));
  } catch {
    return {};
  }
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { username, password } = body;

  if (!username || !password) {
    return NextResponse.json(
      { detail: "Usuario y contraseña requeridos" },
      { status: 400 },
    );
  }

  try {
    const resp = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!resp.ok) {
      const error = await resp.json().catch(() => ({ detail: "Credenciales inválidas" }));
      return NextResponse.json(error, { status: resp.status });
    }

    const data = await resp.json();
    const { access_token, refresh_token } = data;

    const payload = decodeToken(access_token);
    const sub = (payload.sub as string) ?? username;
    const role = (payload.role as string) ?? "vendedor";

    const res = NextResponse.json({
      user: username,
      sub,
      role,
      message: "Login exitoso",
    });

    res.cookies.set("motoshop_token", access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 15 * 60,
    });

    if (refresh_token) {
      res.cookies.set("motoshop_refresh", refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 7 * 24 * 60 * 60,
      });
    }

    return res;
  } catch {
    return NextResponse.json(
      { detail: "No se pudo conectar con el servidor" },
      { status: 502 },
    );
  }
}
